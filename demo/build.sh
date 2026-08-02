#!/bin/sh
# Assemble the self-contained demo. No bundler, no dependencies — the output is
# one HTML file that runs from a file:// URL with no server and no network.
#
# catalog.data.js is generated from the real catalog.py so the demo cannot
# drift from the product:
#   python3 -c "..."   # see demo/README.md
set -e
cd "$(dirname "$0")"
{
  cat demo-head.html
  cat demo-body.html
  echo '<script>'
  cat catalog.data.js; echo
  cat demo-engine.js demo-ui.js demo-render.js demo-wire.js
  echo '</script>'
} > site-scanner-demo.html
echo "built site-scanner-demo.html ($(wc -c < site-scanner-demo.html) bytes)"
