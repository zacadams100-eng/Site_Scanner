#!/usr/bin/env bash
#
# Contour — from a fresh Cloud Shell to a running backend, in one command.
#
# Cloud Shell keeps your home directory but throws away environment variables
# and venv activation every time the session reconnects. That makes the same
# five lines a chore several times a day. This script is those five lines,
# made repeatable and safe to re-run.
#
#   ./setup.sh                 set everything up, then run the real backend
#   ./setup.sh --mock          same, but run mock_ee_backend (no credentials)
#   ./setup.sh --smoke         run the Earth Engine smoke test instead
#   ./setup.sh --check         verify credentials and dependencies, run nothing
#   source ./setup.sh          configure THIS shell and stop — for a second tab
#
# Sourcing is the one to use in the tab you run curl or pytest from: it leaves
# the venv active and the environment variables exported in your own shell.
#
# Options:
#   --key FILE       service account JSON (default: auto-detected)
#   --project ID     EE project (default: from the key's project_id)
#   --port N         port to serve on (default: 8000)
#   --no-run         set up, print next steps, start nothing
#   -h, --help       this text
#
# Everything is idempotent: the venv is created once, dependencies are
# installed only when requirements.txt has actually changed.

# Sourced or executed? Sourced means we must never call exit, and must never
# leave `set -e` behind — a stray failure would close the user's shell.
if (return 0 2>/dev/null); then
    _contour_sourced=1
else
    _contour_sourced=0
fi

_contour_say()  { printf '  %s\n' "$*"; }
_contour_warn() { printf '  ! %s\n' "$*" >&2; }
_contour_err()  { printf '\n  error: %s\n' "$*" >&2; }

# sha256 of a file, whichever tool this machine has.
_contour_sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | cut -d' ' -f1
    else
        echo "no-hash-tool"   # forces a reinstall each run; correct, just slower
    fi
}

# Is this file a Google service account key? Cheap check before parsing.
_contour_is_key() {
    grep -qs '"type"[[:space:]]*:[[:space:]]*"service_account"' "$1"
}

# Reads one top-level string field out of a JSON file. Empty if absent.
_contour_key_field() {
    python3 -c '
import json, sys
try:
    with open(sys.argv[1]) as f:
        print(json.load(f).get(sys.argv[2], ""))
except Exception:
    sys.exit(1)
' "$1" "$2" 2>/dev/null
}

_contour_setup() {
    local key_file="${CONTOUR_KEY_FILE:-}"
    local project="${EE_PROJECT:-}"
    local port="${CONTOUR_PORT:-8000}"
    local mode="run"        # run | mock | smoke | check | none

    while [ $# -gt 0 ]; do
        case "$1" in
            --key)      key_file="$2"; shift 2 ;;
            --key=*)    key_file="${1#*=}"; shift ;;
            --project)  project="$2"; shift 2 ;;
            --project=*) project="${1#*=}"; shift ;;
            --port)     port="$2"; shift 2 ;;
            --port=*)   port="${1#*=}"; shift ;;
            --mock)     mode="mock"; shift ;;
            --smoke)    mode="smoke"; shift ;;
            --check)    mode="check"; shift ;;
            --no-run)   mode="none"; shift ;;
            -h|--help)
                # The header comment block, up to the first non-comment line.
                awk 'NR==1{next} /^#/{sub(/^# ?/, ""); print; next} {exit}' "$_contour_script"
                _contour_mode="none"; return 0 ;;
            *)
                _contour_err "unknown option: $1  (try --help)"
                return 2 ;;
        esac
    done

    # ---------------------------------------------------------------------
    # 1. Where we are. Derived from this script's own location, so it works
    #    whether the checkout is ~/ee-backend, ~/Site_Scanner or anywhere else.
    # ---------------------------------------------------------------------
    cd "$_contour_root" || { _contour_err "cannot cd to $_contour_root"; return 1; }
    if [ ! -f app.py ]; then
        _contour_err "app.py is not next to setup.sh — is this the right checkout?"
        return 1
    fi
    printf '\nContour backend setup\n'
    _contour_say "directory        $_contour_root"

    # ---------------------------------------------------------------------
    # 2. Virtualenv. Created on first run, reused afterwards.
    # ---------------------------------------------------------------------
    if [ ! -d venv ]; then
        _contour_say "venv             creating (first run — this takes a minute)"
        if ! python3 -m venv venv; then
            _contour_err "python3 -m venv failed. On Debian/Ubuntu: sudo apt install python3-venv"
            return 1
        fi
    fi
    # shellcheck disable=SC1091
    . venv/bin/activate || { _contour_err "could not activate venv"; return 1; }
    _contour_say "venv             active ($(python -V 2>&1))"

    # ---------------------------------------------------------------------
    # 3. Dependencies. Reinstalled only when requirements.txt changed, so the
    #    common case is a no-op rather than a 30-second pip run.
    # ---------------------------------------------------------------------
    local want have stamp="venv/.requirements.sha256"
    want="$(_contour_sha256 requirements.txt)"
    have="$(cat "$stamp" 2>/dev/null)"
    if [ "$want" != "$have" ]; then
        _contour_say "dependencies     installing from requirements.txt"
        if ! python -m pip install -q --disable-pip-version-check -r requirements.txt; then
            _contour_err "pip install failed — see the output above"
            return 1
        fi
        printf '%s\n' "$want" > "$stamp"
    else
        _contour_say "dependencies     up to date"
    fi

    # The mock backend and the smoke test need nothing further.
    if [ "$mode" = "mock" ]; then
        _contour_mode="mock"; _contour_port="$port"; return 0
    fi

    # ---------------------------------------------------------------------
    # 4. Credentials. The part Cloud Shell keeps forgetting.
    # ---------------------------------------------------------------------
    if [ -z "$key_file" ] && [ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] \
       && [ -f "${GOOGLE_APPLICATION_CREDENTIALS}" ]; then
        key_file="$GOOGLE_APPLICATION_CREDENTIALS"
    fi

    if [ -z "$key_file" ]; then
        # Any service account key sitting next to the app, then one in $HOME.
        # Filenames are generated by the Cloud console and differ per key, so
        # they're identified by content, not by name.
        local found=() f
        for f in ./*.json "$HOME"/*.json "$HOME"/ee-backend/*.json; do
            [ -f "$f" ] || continue
            _contour_is_key "$f" && found+=("$f")
        done
        # De-duplicate (./x.json and $HOME/x.json can be the same file).
        local uniq=() seen g real
        for f in "${found[@]}"; do
            real="$(cd "$(dirname "$f")" && pwd)/$(basename "$f")"
            seen=0
            for g in "${uniq[@]}"; do [ "$g" = "$real" ] && seen=1; done
            [ "$seen" = 0 ] && uniq+=("$real")
        done
        if [ "${#uniq[@]}" -eq 1 ]; then
            key_file="${uniq[0]}"
        elif [ "${#uniq[@]}" -gt 1 ]; then
            _contour_err "found more than one service account key — pass --key FILE:"
            for f in "${uniq[@]}"; do printf '      %s\n' "$f" >&2; done
            return 1
        fi
    fi

    if [ -z "$key_file" ]; then
        _contour_err "no service account key found."
        _contour_say "Put the JSON key next to app.py, or pass --key /path/to/key.json"
        _contour_say "Download it from: Cloud console -> IAM -> Service Accounts -> Keys"
        return 1
    fi
    if [ ! -f "$key_file" ]; then
        _contour_err "key file does not exist: $key_file"
        return 1
    fi

    local email key_project
    email="$(_contour_key_field "$key_file" client_email)" || {
        _contour_err "$key_file is not valid JSON — re-download the key"
        return 1
    }
    if [ -z "$email" ]; then
        _contour_err "$key_file has no client_email — that isn't a service account key"
        return 1
    fi
    key_project="$(_contour_key_field "$key_file" project_id)"

    # app.py wants the key's *contents*, not its path. This is the export that
    # is easiest to get subtly wrong by hand.
    GOOGLE_APPLICATION_CREDENTIALS_JSON="$(cat "$key_file")"
    export GOOGLE_APPLICATION_CREDENTIALS_JSON

    [ -z "$project" ] && project="$key_project"
    if [ -z "$project" ]; then
        _contour_err "no EE project — pass --project ID or set EE_PROJECT"
        return 1
    fi
    export EE_PROJECT="$project"

    _contour_say "key              $key_file"
    _contour_say "service account  $email"
    _contour_say "EE_PROJECT       $EE_PROJECT"
    if [ -n "$key_project" ] && [ "$key_project" != "$project" ]; then
        _contour_warn "key project is $key_project but EE_PROJECT is $project — deliberate?"
    fi

    # A key is a live credential. If it's inside a git checkout and not
    # ignored, one `git add .` publishes it.
    if git -C "$_contour_root" rev-parse --git-dir >/dev/null 2>&1; then
        if git -C "$_contour_root" ls-files --error-unmatch "$key_file" >/dev/null 2>&1; then
            _contour_warn "this key is TRACKED BY GIT. Remove it from the index and rotate it."
        elif [ "${key_file#"$_contour_root"}" != "$key_file" ] || [ "${key_file#./}" != "$key_file" ]; then
            git -C "$_contour_root" check-ignore -q "$key_file" 2>/dev/null || \
                _contour_warn "key is inside the repo but not gitignored — add it to .gitignore"
        fi
    fi

    _contour_mode="$mode"
    _contour_port="$port"
    return 0
}

# Resolve this script's own path, sourced or executed.
if [ -n "${BASH_SOURCE[0]:-}" ]; then
    _contour_script="${BASH_SOURCE[0]}"
else
    _contour_script="$0"
fi
_contour_root="$(cd "$(dirname "$_contour_script")" && pwd)"
_contour_script="$_contour_root/$(basename "$_contour_script")"

_contour_mode=""
_contour_port=8000
_contour_setup "$@"
_contour_status=$?

if [ "$_contour_status" -ne 0 ]; then
    printf '\n  Setup did not complete. Nothing was started.\n\n' >&2
elif [ "$_contour_sourced" = 1 ]; then
    # Sourced: the point was to configure this shell, so stop here whatever
    # --mock/--smoke said, and say what the shell is now good for.
    if [ -n "$_contour_mode" ]; then
        printf '\n  This shell is ready. venv active, credentials exported.\n\n'
        printf '    curl -X POST http://localhost:%s/api/tile/ndvi \\\n' "$_contour_port"
        printf "      -H 'Content-Type: application/json' -d '{\"year\": 2024}'\n\n"
        printf '    pytest                      # no credentials needed\n'
        printf '    python scripts/ee_smoke_test.py\n'
        printf '    ./setup.sh                  # start the server (in another tab)\n\n'
    fi
else
    case "$_contour_mode" in
        run)
            printf '\n  Starting the real Earth Engine backend on port %s. Ctrl-C to stop.\n\n' "$_contour_port"
            exec uvicorn app:app --reload --port "$_contour_port"
            ;;
        mock)
            printf '\n  Starting the MOCK backend on port %s — no credentials, no Earth Engine.\n' "$_contour_port"
            printf '  Responses carry X-Contour-Mock: true.\n\n'
            exec uvicorn mock_ee_backend:app --reload --port "$_contour_port"
            ;;
        smoke)
            printf '\n  Running the Earth Engine smoke test.\n'
            exec python scripts/ee_smoke_test.py
            ;;
        check)
            printf '\n  Environment is configured. Nothing was started (--check).\n'
            printf '  This checks the key is well-formed and readable, not that Earth\n'
            printf '  Engine accepts it — ./setup.sh --smoke is what proves that.\n\n'
            ;;
        none|"")
            : ;;
    esac
fi

# Sourcing leaves these behind otherwise, cluttering the user's shell.
if [ "$_contour_sourced" = 1 ]; then
    unset -f _contour_setup _contour_say _contour_warn _contour_err \
             _contour_sha256 _contour_is_key _contour_key_field 2>/dev/null
    unset _contour_script _contour_root _contour_mode _contour_port _contour_sourced
    unset _contour_status
else
    # Without this the script's exit status is that of the `if` above, so a
    # failed setup would look like a success to anything checking $?.
    exit "$_contour_status"
fi
