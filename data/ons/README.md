# Stored ONS releases

Written by `python3 -m ons.job`, read by `ons_store.py`, refreshed monthly by
`.github/workflows/ons-refresh.yml`.

These files are committed on purpose. The app deploys as a static bundle plus
one serverless function with no database attached, so this directory is the
only storage that exists in that deployment. They are small — a few hundred KB
— and a diff shows exactly which local authorities moved between releases.

Empty until the job has run. That is the normal starting state: `ons_store`
registers a factor only when there is data behind it, so an empty directory
means those factors keep saying "generated" rather than promising a number
they cannot produce.
