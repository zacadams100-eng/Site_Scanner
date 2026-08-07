# Consolidating the branches — prepared, not done

This needs a decision that is yours, so nothing here has been executed. It is
written so that saying yes costs one paste.

## The problem

`main` is the July prototype: five files, one of them a 43 KB single-page HTML
demo. Every piece of real work — the React app, the Earth Engine backend, the
ingest pipeline, the open-data integrations, 485 tests — lives on feature
branches. Anyone who clones this repository and reads `main` starts four
months behind, and a fresh session handed a stale branch name starts 39
commits behind. Both have now happened.

## Where things actually are

Measured 2026-08-07. "Ahead/behind" is relative to
`claude/site-scanner-priorities-lllrp6`, the current tip.

| Branch | Last commit | Behind tip | Unmerged | What it is |
| --- | --- | ---: | ---: | --- |
| `claude/site-scanner-priorities-lllrp6` | 2026-08-07 | — | — | **The tip.** Everything below, plus this session |
| `claude/handoff-md-review-e6zlvw` | 2026-08-05 | 9 | 0 | Fully merged into the tip |
| `claude/site-scanner-improvements-pfiz4b` | 2026-08-05 | 27 | 0 | Fully merged |
| `claude/accessible-gis-web-app-tktvmz` | 2026-08-05 | 47 | 0 | Fully merged |
| `claude/site-scanner-ui-redesign-bfxy2q` | 2026-08-03 | 59 | **5** | Has work nowhere else — see below |
| `claude/contour-mock-ee-backend-sl1a8p` | 2026-07-31 | 77 | 0 | Fully merged |
| `claude/contour-satellite-tool-9luoqd` | 2026-07-31 | 77 | **1** | `setup.sh`, which is on the tip by another route |
| `main` | 2026-07-31 | 83 | 0 | The prototype |

### The two branches with commits nowhere else

`claude/contour-satellite-tool-9luoqd` has one: *"Add setup.sh, so a Cloud
Shell reset costs one command."* `setup.sh` is present on the tip, so the file
arrived by another path and only this commit object is unreachable. Safe.

`claude/site-scanner-ui-redesign-bfxy2q` has five, and these are the ones to
look at before deleting anything:

```
60178a4 Make the app runnable with no backend, and buildable as one file
3148990 Add a gallery home screen, and make a saved site a real project
d56ecba Add CI: lint, typecheck, build and both test suites
4acbb16 Repalette to the logo, and give the interface a real layer ramp
7a6002b Vendor the ui-ux-pro-max design skill
```

Two of those describe things the tip has by other means — CI exists in
`.github/workflows/ci.yml`, and the palette was redone later and differently
(`BRAND.md`). **The gallery home screen appears to exist only here.** That is
a real feature and it is worth deciding deliberately whether it is wanted
before this branch is deleted. Everything else on the list is superseded.

Verify before acting — these counts were taken on 2026-08-07 and any push
changes them:

```bash
git log --oneline HEAD..origin/claude/site-scanner-ui-redesign-bfxy2q
git log --oneline HEAD..origin/claude/contour-satellite-tool-9luoqd
```

## The recommendation

Make `main` the tip, then delete the branches that are fully contained in it.

This is a fast-forward in spirit but not in fact — `main` is not an ancestor of
the working branch, because the working branch descends from a different root.
So it is a force update, and that is the part needing your say-so.

```bash
# 1. Confirm nothing on main is missing from the tip. Expect empty output.
git log --oneline claude/site-scanner-priorities-lllrp6..origin/main

# 2. Keep the prototype reachable by name, so nothing is actually lost.
git tag prototype-2026-07 origin/main
git push origin prototype-2026-07

# 3. Point main at the current work.
git push origin claude/site-scanner-priorities-lllrp6:main --force-with-lease

# 4. Delete only the branches with nothing unique on them.
git push origin --delete claude/handoff-md-review-e6zlvw
git push origin --delete claude/accessible-gis-web-app-tktvmz
git push origin --delete claude/site-scanner-improvements-pfiz4b
git push origin --delete claude/contour-mock-ee-backend-sl1a8p
git push origin --delete claude/contour-satellite-tool-9luoqd
```

Not in that list: `claude/site-scanner-ui-redesign-bfxy2q`. Leave it until
you have decided about the gallery home screen. It costs nothing to keep.

Step 2 is what makes step 3 safe: the prototype stays fetchable as a tag
forever, and `site-scanner.html` is in the tip's history anyway.

## The alternative, if a force push is unwelcome

Open a pull request from `claude/site-scanner-priorities-lllrp6` into `main`
and merge it. The diff is most of the repository, so the review is not a real
review — but the history is additive and nothing is rewritten. Slower, and
leaves a merge commit joining two unrelated roots, which some tools handle
badly.

I would take the force push with the tag. The prototype has no future work on
it, and a repository whose default branch is four months stale costs something
every time anyone touches it.

## Why this was not just done

A force push to `main` and three branch deletions are not reversible from
inside a session, and they are the kind of thing someone should choose rather
than discover. The recommendation is above; the commands are exact.
