# Starting a Cloud Shell session

Cloud Shell is the best place to run anything that touches a live source. It
has ordinary outbound internet, which the development sandbox does not, and its
home directory survives between sessions.

Two things reset every time you open it, and both have cost real time:

- **The working directory goes back to `~`**, not the project. A relative path
  like `scripts/verify.py` then resolves to `/home/you/scripts/verify.py`,
  which does not exist, and the error says "No such file or directory" rather
  than "you are in the wrong folder".
- **The branch is whatever it was**, and `main` still holds only the original
  prototype — no `scripts/` directory at all. So the same "no such file" error
  has a second, completely different cause.

## The opener

Paste this at the start of every session. It is safe to run every time.

```bash
cd ~ && [ -d Site_Scanner ] || git clone https://github.com/zacadams100-eng/Site_Scanner.git
cd ~/Site_Scanner && git checkout claude/site-scanner-priorities-uk2q8r && git pull
```

The first line clones only if the folder is missing — Cloud Shell keeps home
between sessions, but it is reclaimed after long inactivity, and a clone that
is already there must not be clobbered.

**Success looks like** `Already up to date.` or a list of changed files.

Once, on a fresh machine:

```bash
pip install -r requirements.txt
```

You only need this again if something says `No module named requests`.

## Then

| To | Run | Takes |
| --- | --- | --- |
| Check every live source | `python3 scripts/verify.py` | ~1 min |
| Build the England baselines | `python3 scripts/build_baselines.py` | ~10 min |
| Check one source | `python3 scripts/check_open_data.py --source planning` | ~20 s |
| See where the catalogue stands | `python3 scripts/audit_catalogue.py \| head -3` | instant |
| Confirm a dataset attribute | `python3 scripts/discover_planning_datasets.py --attributes flood-risk-zone` | ~5 s |

Everything that writes a report says where it wrote it. Paste that file into a
coding session and the fixes can be made from it.

## If a command fails

Paste the error rather than retrying it. Three of the six bugs found on
2026-08-09 were first mistaken for something the user had done wrong:

- `check_open_data.py` crashed on its own first line with a `TypeError`, which
  looked like a broken integration and was a broken caller.
- The South Downs run reported "no postcode near this area", which looked like
  a badly chosen test location and was the app failing on every rural site.
- `discover_planning_datasets.py` said "no such dataset on the platform" when
  it simply could not reach the platform.

A failing command here is usually information, not user error.
