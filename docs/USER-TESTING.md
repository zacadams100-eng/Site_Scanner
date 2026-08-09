# Watching someone use it

Twenty minutes, one person, no preparation. Do this three times and you will
know more about this product than the last three weeks of building told you.

This document exists because everything in Site Scanner has been built from
inference about what a land agent wants. That inference has been good — but it
has never been checked, and the two highest-signal inputs this project has ever
had were both moments when reality contradicted the code: a screenshot that
showed the drawing tools sitting underneath the report sheet on a phone, and a
flat NDVI series that turned out to be a badly chosen test field rather than a
bug.

## Who

Three people, in this order of usefulness:

1. **A planning or development consultant.** The paying user.
2. **An ecologist or environmental consultant.** Closest to the BNG and habitat
   work, and the harshest about data provenance — which is the thing this
   product is unusually good at, so their reaction is the test of whether that
   effort was worth it.
3. **A land agent or rural surveyor.** The "is this site viable" question in
   its purest form.

A course mate on the same degree is worth something but is not a substitute:
they will forgive the interface in a way a working professional will not.

Failing all three, a friend who has **never seen a GIS tool**. That still tests
item 2 of the strategy — zero-training accessibility — which is the claim most
likely to be wrong.

## Rules

**Say almost nothing.** The single most common way a test like this is wasted
is the builder explaining. Every explanation you give is a piece of interface
you now cannot fix, because you have hidden the problem behind yourself.

Allowed: "What are you trying to do?" · "What did you expect to happen?" ·
"Say what you're thinking." Not allowed: "You need to click the…"

**Let them be stuck for a full minute.** It will feel unbearable. Where they
get stuck is the finding.

**Record the screen if they'll let you.** You will not remember it accurately —
nobody does.

## The session

Open https://site-scanner-pi.vercel.app and hand over the laptop.

### 1. First 60 seconds — say nothing at all (2 min)

> "This is a tool for looking at land. Have a go."

Watch only for: **do they draw a shape, and how long does it take?** Drawing is
the entire interaction. If it takes more than about thirty seconds to discover,
that is the most important bug in the product and everything else is noise.

Write down the number of seconds. It is the single most useful figure you will
collect.

### 2. A real site (6 min)

> "Find a piece of land you actually know — where you grew up, a site you've
> worked on — and tell me about it from what's on the screen."

This is the test that matters, because they can check the answer against
reality. Watch for:

- Do they trust the numbers? Do they say why or why not?
- **Do they notice the demo-data labels?** If they do not, the honesty
  architecture is not working and that is a serious finding. If they do and
  react badly, that is a different serious finding and you need to know which.
- Which tab do they go to first — Findings, Table, Charts? The app opens on
  Findings on the assumption that sentences beat a grid. Test it.

### 3. The question they arrived with (4 min)

> "What would you actually need to know about a site, that you haven't been
> able to find here?"

Write the answer down word for word. This is your roadmap, and it will
probably not match the 269-factor catalogue.

### 4. Sharing (3 min)

> "Send this to a colleague."

They should find Share. If they do, the link is the moat — watch whether they
believe it will work. If they instead screenshot it, that tells you the printed
report matters more than the URL.

### 5. Ask it a question (3 min)

> "There's a box that takes a plain-English question. Try it."

Natural-language querying is claimed as the highest-differentiation feature.
Nobody outside this project has ever used it. Find out whether it survives real
phrasing.

### 6. The closing question (2 min)

> "Would you use this? What would have to be true first?"

Then, only if they say yes:

> "Would you pay for it? What would you expect it to cost?"

Take the hesitation as the answer, not the words.

## What to write down

Immediately afterwards, before you do anything else — five minutes, in
`docs/user-tests/YYYY-MM-DD-role.md`:

```markdown
# <role>, <date>

Seconds to first drawn shape:
Got stuck at:
Noticed the demo-data labels:            yes / no
What they said they actually need:
Exact quote worth remembering:
The thing I wanted to explain but didn't:
```

That last line is the most valuable one in the file. Whatever you bit your
tongue about is a piece of interface that needs to do that explaining itself.

## What this will probably find

Written in advance, so it can be wrong on the record rather than confirmed in
hindsight:

1. **269 factors will overwhelm them.** The factor browser is a filing cabinet.
   Expect them to use a template or nothing at all.
2. **They will ask about something that is not in the catalogue**, and it will
   be something specific and boring — access rights, ransom strips, a covenant.
3. **They will not care about the timeline** as much as this project assumes.
   Fifteen years of monthly data is the architecture's proudest achievement and
   may be answering a question nobody asked.
4. **The demo-data labelling will either be invisible or a dealbreaker.** Both
   outcomes are actionable and it is important to know which.

If three sessions all contradict one of these, that is worth more than a
month of building.
