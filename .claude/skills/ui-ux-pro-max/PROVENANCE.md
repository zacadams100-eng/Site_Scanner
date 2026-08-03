# ui-ux-pro-max — provenance

Vendored, not authored here.

- **Upstream:** https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
- **Version:** 2.11.0 (`skill.json` at the commit vendored)
- **Licence:** MIT (see upstream `LICENSE`)
- **Vendored:** August 2026

## What was copied

`src/ui-ux-pro-max/{data,scripts}` verbatim, minus `scripts/tests/`. `SKILL.md`
is generated from the upstream template pair
(`templates/base/skill-content.md` + `templates/base/quick-reference.md`) with
the `claude` platform frontmatter from `templates/platforms/claude.json` — the
same output `npx ui-ux-pro-max-cli init --ai claude` produces, done by hand so
the tree is reviewable in a diff.

## Using it

The scripts are standard-library Python 3, no network access:

```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "<query>" --design-system
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "<query>" --domain style
```

## How it was used here

For the August 2026 UI pass it supplied the layering and density reasoning —
the four-level elevation scale, the z-index-scale rule (which caught a real
stacking-context bug in the factor browser), the disabled/contrast floors and
the reduced-motion and focus checks.

Its `--design-system` colour and typography output was **not** taken: it
proposed an editorial black/pink landing-page system, and this product's
palette comes from the Site Scanner logo instead. That is the expected way to
use it — the reasoning transfers, the generated brand does not.

## Updating

Re-clone upstream and re-copy `data/` and `scripts/`; regenerate `SKILL.md`
from the templates. Nothing in this directory is modified locally, so there is
nothing to merge.
