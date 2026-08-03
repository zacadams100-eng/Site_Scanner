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

# The Google Cloud project the key belongs to, which must also be the one
# registered with Earth Engine. Cloud Shell already knows this, so ask gcloud
# rather than storing it.
if [ -z "$EE_PROJECT" ] && command -v gcloud >/dev/null 2>&1; then
  EE_PROJECT="$(gcloud config get-value project 2>/dev/null)"
  [ "$EE_PROJECT" = "(unset)" ] && EE_PROJECT=""
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

if [ -z "$EE_PROJECT" ]; then
  echo "✗ Could not work out your Google Cloud project ID."
  echo "  In Cloud Shell:  gcloud config set project YOUR-PROJECT-ID"
  echo "  Or set it here:  EE_PROJECT=your-project-id source ./setup.sh"
  return 1
fi

export GOOGLE_APPLICATION_CREDENTIALS_JSON="$(cat "$EE_KEY_FILE")"
export EE_PROJECT

echo "✓ Environment ready"
echo "  project:  $EE_PROJECT"
echo "  key file: $EE_KEY_FILE"
echo "  python:   $(which python3)"
echo
echo "Next:  python3 scripts/check_real_ndvi.py 2024"
