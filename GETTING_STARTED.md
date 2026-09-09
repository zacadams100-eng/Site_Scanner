# Getting Site Scanner running

For someone who has just been given access. About ten minutes, most of it
waiting for `pip`.

Site Scanner draws real satellite-derived layers for a piece of land — NDVI
(vegetation) and ESA WorldCover (land cover) — by asking Google Earth Engine
for them server-side. The browser never downloads satellite data; it receives a
tile URL and a set of statistics.

## What you need first

**A Google Earth Engine service account key**, as a `.json` file. Ask for one —
do not create your own, and do not use a personal Google login. Two things
about it:

- **It is a credential.** Anyone holding it can spend money against the project
  it belongs to. Keep it out of the repository — `.gitignore` is set up to
  refuse the obvious filenames, but that is a safety net, not permission to be
  casual.
- **It states which project it can use**, in its `project_id` field. That is
  the only thing that decides which project this talks to.

Put it in `~/ee-backend/`:

```bash
mkdir -p ~/ee-backend
# then move the .json file into it
ls ~/ee-backend/*.json     # should list exactly one file
```

## Four commands

```bash
git clone https://github.com/zacadams100-eng/Site_Scanner.git
cd Site_Scanner
source ./setup.sh                 # note: source, not ./setup.sh
./scripts/live_tile_check.sh --keep
```

`source` matters. A script run normally cannot change the environment of the
shell you are sitting in, so the credentials would vanish the moment it
finished.

`setup.sh` builds a virtual environment on its first run — about a minute — and
is instant after that.

### What success looks like

```
✓ Environment ready
  project:  <the project your key belongs to>   (from the key file)

✓ A real tile URL came back.

    https://earthengine.googleapis.com/v1/projects/.../tiles/{z}/{x}/{y}
```

The backend is now running on port 8000, and it serves the page as well as the
data:

    http://localhost:8000/app

In Cloud Shell there is no localhost to open, so use **Web Preview** (the `<>`
icon, top right of the terminal) → *Change port* → **8000** → *Preview*. It
gives you an authenticated HTTPS URL; append `/app` to it.

One port on purpose. The page works out its backend from its own origin, so
serving it separately from the API means it quietly falls back to simulated
figures — the one failure this project must never make silently.

The badge in the corner should read **Live Earth Engine**.

If it reads **Simulated — backend unreachable**, the page is working but the
backend is not; the badge exists so that a screenshot can never quietly show
made-up data as though it were real. **Never demo anything that does not say
Live.**

### The React app

`web/` is the fuller frontend — same backend, on port 5173:

```bash
cd web && npm install && npm run dev
```

It needs an `npm install` first, and Cloud Shell's preview domain trips Vite's
host check, so `/app` is the quicker route to something on screen today.

## Never having to think about it again

```bash
./scripts/install_shell_hook.sh
```

Environment variables live in one shell and die with it, so every new tab
otherwise starts with no credentials — which shows up later as an unexplained
500 rather than as "you forgot to run something". This adds a guarded block to
`~/.bashrc` so every shell has them. `--remove` takes it out again.

## When it does not work

`live_tile_check.sh` is built to tell you *which* of the three things failed,
because the failure modes look identical from the browser.

| Exit | Means | Do this |
| --- | --- | --- |
| `3` | Never got as far as asking | Credentials are not loaded, or the server did not start. The output says which. |
| `4` | Asked, and the answer was not usable | The server and the route are fine. Read the detail — it came from Earth Engine. |
| `0` | A real tile URL came back | Nothing. It works. |

Two specific ones worth knowing:

**"Caller does not have required permission to use project X."** The key belongs
to one project and something is asking for a different one. `setup.sh` reads
the project out of the key file precisely so these cannot disagree — if you see
this, check whether `EE_PROJECT` is set in your shell from somewhere else:

```bash
echo "$EE_PROJECT"
python3 -c 'import json;print(json.load(open("'"$EE_KEY_FILE"'"))["project_id"])'
```

Those two must match. If they do not, unset `EE_PROJECT` and re-`source`.

**Everything fails and you cannot tell why.** Take Earth Engine out of the
picture entirely:

```bash
./scripts/live_tile_check.sh --mock
```

That runs the same check against `mock_ee_backend.py`, which needs no
credentials. If it passes, the server, the route, the request shape and the
JSON contract are all fine and the problem is Earth Engine and nothing else.
If it fails, the problem is local and has nothing to do with your key.

## Two habits this project runs on

**A failure never becomes an empty result.** If Earth Engine cannot be reached,
the page says so rather than showing zero. "We looked and there is nothing
there" and "we could not look" are different facts, and the second must never
be presented as the first — it is the one that gets a decision made on bad
information.

**Nothing is verified because it worked once.** Real services fail
intermittently: in testing, one provider answered one query in six over ten
minutes while reporting free capacity. If something matters, check it, and
check it more than once.
