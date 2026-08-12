# Design system

**Implemented**, in `web/src/index.css` and the components. `BRAND.md` holds the
brand argument; `DESIGN_SPEC.md` holds the original specification. This is the
working reference for what exists.

---

## The direction

**Field science × 1990s outdoor equipment × editorial.** The interface should
feel like a piece of field equipment, not a CRM.

The emotional territory — Oakley, The North Face, Patagonia, expedition manuals,
scientific notebooks, national park signage, old topographic maps — is a
reference, never a copy. What is borrowed is the *attitude*: technical,
confident, slightly eccentric, built to be used outdoors by someone who knows
what they are doing.

### Explicitly not

Generic SaaS gradients · purple AI aesthetics · rounded-card-everything ·
glassmorphism · dashboard templates · corporate blue GIS · AI slop · vast empty
whitespace · decorative components that carry no information.

---

## The test that decides it

> Remove the logo. Is it still recognisably this product?

The display face at size is the strongest carrier — `.lib-title` at
`clamp(38px, 6vw, 68px)`, uppercase, condensed, near-black on bone. If that
element survives the logo being removed, the identity is in the system rather
than in the mark.

---

## Colour

Tokens in `:root`. The system, not the values, is the thing to preserve:

| Role | Meaning |
| --- | --- |
| **Bone** | Ground. Paper, not white — a field notebook, not a screen |
| **Structure / forest** | Ink and elevation. Dark green, not black |
| **Signal orange** | **Rationed hard.** Attention, and only attention |
| **Khaki / clay / rule** | Annotation, marks, hairlines |

Signal orange is the one rule worth restating: it means *look here*. It appears
on the open-scanner action and on the partial-coverage badge, and if it starts
appearing on decoration it stops meaning anything.

### Per-scanner palettes

Each scanner carries its own, in the workspace and in the library, so an
instrument looks the same in the case as it does in the hand.

| Scanner | Reference |
| --- | --- |
| Land | A survey sheet — parchment, terrain green, survey yellow |
| Water | An Admiralty chart — ink on off-white, chart blue, orange kept for warning because that is what orange means at sea |
| Ecology | A herbarium sheet — moss and chlorophyll on cream, specimen-label red |
| Planning | A title plan — drawing-office ink on tracing paper, boundary-line red |

Keyed on canonical scanner ids with the retired ids as aliases, so a stored link
still gets the right instrument.

---

## Type

- **Display** — condensed, uppercase, tight. Headings, names, labels.
- **Prose** — readable at 12–15px for the sentences that carry meaning.
- **Mono** — measurements, coordinates, ids, counts. Anything a reader might
  compare vertically gets `font-variant-numeric: tabular-nums`.

The rule: **a number a reader might compare is monospaced and tabular.** A column
of proportional figures cannot be scanned.

---

## Motifs

Each earns its place by carrying information or by being genuinely structural.

- **Contour field** — texture behind a scanner plate, at 10% opacity. A pattern
  you notice is a pattern competing with the words.
- **Index numbers** — `01`, `02`. Catalogue language.
- **Technical margin** — one true statement per instrument ("Designations only ·
  no application history").
- **Four-step glyph scale** — `◉ ● ◐ ○` for flagged, clear, partial, not
  assessed. Learned once, then readable at a glance, and it survives greyscale
  and colour-blindness because the **shape** carries it.
- **Dashed underline** — a limit of the instrument, not a fault in the site.
  Used for uncertainty, coverage gaps and unread checks. Deliberately not
  alarming.
- **Hatching** — on the map, where a month's observation is too sparse to trust.

---

## The rules that are not aesthetic

1. **State is never carried by colour alone.** Every state has a glyph or a
   word. Colour-blindness and greyscale printing both have to work.
2. **A gap is dashed, not red.** It is a limit of the instrument. Red would say
   the site has a problem, which is a claim about the place rather than about
   the reading.
3. **Nothing is disabled-and-clickable.** A disabled control invites a click and
   then refuses, which reads as a fault. An unbuilt scanner is not a control at
   all, and words carry the reason.
4. **Wide content scrolls inside its own container.** The page body never
   scrolls horizontally. Checked at 1440×900 and 390×844.
5. **A label travels with its content.** Demo labelling is on the row, not in a
   legend, because a row gets copied out.

---

## Verifying a change

`tsc --noEmit` is **not** the build, and neither is green unit tests. Three real
regressions shipped past both in the taxonomy pass and were found by driving the
page — including every declared scanner rendering as a dark block with grey text
on it, caused by a CSS specificity loss that no test could have seen.

```bash
python3 -m uvicorn mock_ee_backend:app --port 8000
cd web && npm run dev -- --port 8080 --host
```

Then drive it at both viewports and check: console errors, horizontal overflow,
computed styles on anything whose selector you changed.
