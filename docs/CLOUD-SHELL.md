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
cd ~/Site_Scanner && git fetch origin claude/sitescanner-handoff-fx0yid \
  && git checkout claude/sitescanner-handoff-fx0yid && git pull
```

`git fetch` before `git checkout` matters on a machine that has not seen this
branch: without it the checkout fails with "pathspec did not match", which
reads like the branch does not exist rather than like the clone has not heard
of it yet.

The first line clones only if the folder is missing — Cloud Shell keeps home
between sessions, but it is reclaimed after long inactivity, and a clone that
is already there must not be clobbered.

**Success looks like** `Already up to date.` or a list of changed files.

Once, on a fresh machine:

```bash
pip install -r requirements.txt
```

You only need this again if something says `No module named requests`.

## Running the site

Cloud Shell previews **port 8080**, and Vite serves 5173 by default, so the
port is passed explicitly. `--host` is required too: without it Vite binds to
localhost only and the preview button returns a blank page rather than an
error.

Two processes. Open a second tab with the `+` button for the frontend.

**Tab 1 — the API:**

```bash
cd ~/Site_Scanner
pip install -r requirements.txt          # first time on a fresh machine only
python3 -m uvicorn mock_ee_backend:app --port 8000
```

**Tab 2 — the site:**

```bash
cd ~/Site_Scanner/web
npm install                              # first time, and after a git pull that changed package.json
npm run dev -- --port 8080 --host
```

Then click **Web Preview → Preview on port 8080** (the eye icon, top right).

- `/` is the marketing site
- `/app` is the scanner library, and the three instruments are behind it

`npm run dev` regenerates the hero field sheet, the asset manifest and the
sitemap before it starts, so a fresh clone with no `public/hero/` still works.

### Which backend you are running

`mock_ee_backend` serves **generated data** and stamps every response
`X-Contour-Mock: true`. The interface says so, and every scanner check reports
"no signal" because nothing may be claimed from generated numbers. That is
correct behaviour, not a broken install.

For real observations you need Earth Engine credentials and the real app:

```bash
export GOOGLE_APPLICATION_CREDENTIALS_JSON="$(cat service-account-key.json)"
export EE_PROJECT="your-gcp-project-id"
python3 -m uvicorn app:app --port 8000
```

Confirm which one answered:

```bash
curl -sD- localhost:8000/api/catalog -o /dev/null | grep -i contour-mock
```

Absent or `false` is the real backend. `true` is the mock.

### Stopping

`Ctrl-C` in each tab. If a port is still held:

```bash
fuser -k 8000/tcp; fuser -k 8080/tcp
```

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
