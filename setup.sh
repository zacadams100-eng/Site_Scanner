#!/usr/bin/env bash
# Sets up the Python environment and Earth Engine credentials for this repo.
#
#   source setup.sh
#
# It must be `source`d, not run with ./setup.sh — a script run normally can't
# change the environment of the shell you're sitting in, so the exports would
# vanish the moment it finished.
#
# There are no secrets in this file. It reads your service account key from a
# file on disk and puts the contents into an environment variable. The key file
# itself must never be committed.

# Where your Earth Engine service account key lives. Nothing is hardcoded —
# this repo is public, and while a filename is not a credential there is no
# reason to publish one. Override if your key is somewhere else:
#     EE_KEY_FILE=~/keys/other-key.json source setup.sh
if [ -z "$EE_KEY_FILE" ]; then
  # Take the first .json in ~/ee-backend. Globbing rather than naming means
  # this keeps working when you rotate the key and the filename changes.
  for _candidate in "$HOME"/ee-backend/*.json; do
    [ -f "$_candidate" ] && EE_KEY_FILE="$_candidate" && break
  done
fi

_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Python environment ----------------------------------------------------
# Cloud Shell resets installed packages between sessions but keeps your home
# directory, so a venv here survives; a bare `pip install` does not.
if [ ! -d "$_repo/venv" ]; then
  echo "Creating a Python virtual environment (first run only)…"
  python3 -m venv "$_repo/venv" || return 1
  # shellcheck disable=SC1091
  source "$_repo/venv/bin/activate"
  pip install --quiet --upgrade pip
  echo "Installing dependencies — this takes a minute…"
  pip install --quiet -r "$_repo/requirements.txt" || return 1
  echo "✓ Dependencies installed"
else
  # shellcheck disable=SC1091
  source "$_repo/venv/bin/activate"
fi

# --- Credentials -----------------------------------------------------------
if [ -z "$EE_KEY_FILE" ]; then
  echo "✗ No service account key found in ~/ee-backend/"
  echo "  Look for it with:  ls ~/ee-backend/*.json"
  echo "  Then re-run:       EE_KEY_FILE=/full/path/to/key.json source ./setup.sh"
  return 1
fi

if [ ! -f "$EE_KEY_FILE" ]; then
  echo "✗ No service account key at: $EE_KEY_FILE"
  echo "  Look for it with:  ls ~/ee-backend/*.json"
  echo "  Then re-run:       EE_KEY_FILE=/full/path/to/key.json source ./setup.sh"
  return 1
fi

# The project the key belongs to, read out of the key itself.
#
# This used to ask `gcloud config get-value project`, which is the wrong
# source: it returns whichever project the Cloud Shell tab happens to be
# pointed at, not the one the service account can actually use. When those
# differ — and they did — Earth Engine refuses with "Caller does not have
# required permission to use project X", which reads like a broken key rather
# than a mismatched pair.
#
# The key file states its own project. Nothing else needs to be consulted, and
# nothing that can drift is.
if [ -z "$EE_PROJECT" ]; then
  EE_PROJECT="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("project_id",""))' "$EE_KEY_FILE" 2>/dev/null)"
fi

if [ -z "$EE_PROJECT" ]; then
  echo "✗ The key file does not state a project_id, and none was given."
  echo "  Set it explicitly:  EE_PROJECT=your-project-id source ./setup.sh"
  return 1
fi

export GOOGLE_APPLICATION_CREDENTIALS_JSON="$(cat "$EE_KEY_FILE")"
export EE_PROJECT

echo "✓ Environment ready"
echo "  project:  $EE_PROJECT   (from the key file)"
echo "  key file: $EE_KEY_FILE"
echo "  python:   $(which python3)"
echo
echo "Next:  ./scripts/live_tile_check.sh          # the endpoint the page calls"
echo "       python3 scripts/check_real_ndvi.py 2024  # Earth Engine on its own"
echo
echo "Tired of typing 'source setup.sh'?  ./scripts/install_shell_hook.sh"
