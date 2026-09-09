#!/usr/bin/env bash
# Stop having to remember `source setup.sh`.
#
#     ./scripts/install_shell_hook.sh
#
# Environment variables live in one shell and die with it. That is not a bug in
# setup.sh — it is what environment variables are — but it means every new
# Cloud Shell tab, every reconnect and every VM recycle starts with no
# credentials, and the failure shows up later as an unexplained 500 rather than
# as "you forgot to run something". That is the thing that keeps breaking.
#
# This appends a guarded block to ~/.bashrc that sources setup.sh in every new
# shell. It is idempotent: run it twice and nothing is added twice.
#
# Cloud Shell keeps your home directory but resets the machine, so ~/.bashrc
# survives and this keeps working across recycles. The venv lives inside the
# repo, which is in home, so that survives too.
#
#     --remove   take the block out again

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="${BASHRC:-$HOME/.bashrc}"
BEGIN="# >>> site_scanner environment >>>"
END="# <<< site_scanner environment <<<"

if [ "${1:-}" = "--remove" ]; then
  if [ -f "$RC" ] && grep -qF "$BEGIN" "$RC"; then
    # A temp file rather than `sed -i`, so an interrupted run cannot leave a
    # half-written .bashrc — which would lock you out of a working shell.
    tmp="$(mktemp)"
    awk -v b="$BEGIN" -v e="$END" '
      $0 == b { skip = 1 } !skip { print } $0 == e { skip = 0 }' "$RC" > "$tmp"
    mv "$tmp" "$RC"
    echo "✓ Removed from $RC"
  else
    echo "Nothing to remove — no block in $RC"
  fi
  exit 0
fi

if [ -f "$RC" ] && grep -qF "$BEGIN" "$RC"; then
  echo "Already installed in $RC — nothing to do."
  echo "Open a new tab, or run:  source $RC"
  exit 0
fi

cat >> "$RC" <<EOF

$BEGIN
# Loads the Earth Engine service account key and project into every new shell,
# so no terminal ever starts without them. Added by
# scripts/install_shell_hook.sh; remove with:
#     $REPO/scripts/install_shell_hook.sh --remove
#
# Quiet on success and quiet when the repo has gone, because a login shell that
# prints a paragraph — or an error — every time is one you stop reading.
#
# The venv check is not belt-and-braces: setup.sh builds the venv and pip
# installs on its first run, which takes about a minute. Doing that from
# .bashrc with the output suppressed would look exactly like a hung terminal.
if [ -f "$REPO/setup.sh" ] && [ -d "$REPO/venv" ]; then
  source "$REPO/setup.sh" > /dev/null 2>&1 || true
elif [ -f "$REPO/setup.sh" ]; then
  echo "site_scanner: run 'source $REPO/setup.sh' once to build the venv."
fi
$END
EOF

echo "✓ Added to $RC"
echo
echo "Every new shell will now have GOOGLE_APPLICATION_CREDENTIALS_JSON and"
echo "EE_PROJECT set, with the venv active."
echo
echo "This shell does not have them yet — environment variables do not travel"
echo "backwards. Either open a new tab, or:"
echo
echo "    source $REPO/setup.sh"
echo
echo "Then check it end to end:"
echo
echo "    $REPO/scripts/live_tile_check.sh"
