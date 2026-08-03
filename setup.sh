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

# Where your Earth Engine service account key lives. Override before sourcing
# if yours is somewhere else:
#     EE_KEY_FILE=~/keys/other-key.json source setup.sh
: "${EE_KEY_FILE:=$HOME/ee-backend/sitescanner-504112-bf0c51189278.json}"

# Your Google Cloud project ID — must be the project the key belongs to, and
# the one registered with Earth Engine.
: "${EE_PROJECT:=sitescanner-504112}"

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
if [ ! -f "$EE_KEY_FILE" ]; then
  echo "✗ No service account key at: $EE_KEY_FILE"
  echo "  Find yours with:  ls ~/ee-backend/*.json"
  echo "  Then re-run:      EE_KEY_FILE=/full/path/to/key.json source setup.sh"
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
