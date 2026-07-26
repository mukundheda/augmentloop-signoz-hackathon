# D5: Rebuild the README as one tight single-scroll pitch (issue #59)

The last lane-D ticket that is not externally blocked. The current `README.md`
reads as a status page: it opens with "Team AugmentLoop's entry for..." and a
**Status:** line, and ends with an internal submission checklist. Every section
in it is individually true and most were written tonight - the problem is
shape, not accuracy.

Ticket #59's framing, verbatim: *"We are not at risk of being out-built; we are
at risk of being out-presented."* A rival entry lands its whole thesis in
ninety-two README lines.

## Hard constraints

1. **Nothing may claim something the code does not do.** This is the ticket's
   own acceptance criterion and the project's entire position. Every figure
   must be current and checkable.
2. **The AI-use disclosure must be retained.** It is a hackathon rule. It may
   be tightened, not dropped or softened.
3. **The `casting.yaml` reproducibility instructions must be retained** -
   also a hackathon rule (judges may re-run Foundry).
4. **The CI badge stays.**
5. **No client names, no API keys, no tunnel URLs, no personal emails.** This
   repo goes public at submission.
6. **"agents propose, humans decide."** Never describe anything as auto-heal.
7. Plain, concrete prose. No marketing gloss, no exclamation marks. Hyphens or
   colons, never em dashes.

## The figures, verified - use these, do not re-derive them

Current committed recording, `python -m toyworld` output as of 2026-07-25:

| | |
|---|---|
| Decisions | 180 |
| Correct | 127 |
| Reality verdicts | 60 |
| Total cost | $0.377553 |
| **Cost per correct decision** | **$0.002973** |

Per model: `claude-sonnet-4.6` 53/60 ($0.278031), `claude-haiku-4.5` 42/60
($0.096187), `gemini-2.5-flash-lite` 32/60 ($0.003335).

Per model per decision type:

| model | eta_estimate | next_hop | route_choice |
|---|---|---|---|
| `claude-sonnet-4.6` | 20/20 | 19/20 | 14/20 |
| `claude-haiku-4.5` | 17/20 | 16/20 | 9/20 |
| `gemini-2.5-flash-lite` | **0/20** | **20/20** | 12/20 |

Grade sources in this run: 180 `math`, 60 `reality`, **0 `ai_judge`**.

If any figure you write disagrees with `docs/visuals/run-data.js`, stop and say
so rather than picking one.

## Task 1: rebuild `README.md`

Target shape, in order:

1. **A hook.** One or two sentences that say what this is and why it matters,
   before any status, team, or hackathon boilerplate. A judge should know what
   Gradebook does before they know who built it.
2. **The killer visual, near the top.** Embed one of the three committed
   screenshots in `docs/visuals/`. Recommend `genome-strip.png`: it renders the
   thesis directly - every decision is a glyph, hue is where the grade's
   authority came from, and the run contains zero `ai_judge` grades. Caption it
   with what the reader is looking at. Use a repo-relative path so it renders
   on GitHub.
3. **The five-second table** - grade source against whether it counts in the
   headline. It is already written and correct; keep it near the top.
4. **The zero-key command.** `pip install -e reference-library -e toy-world`
   then `python -m toyworld`. State that it needs no API key and is
   deterministic.
5. **The per-decision-type finding**, tightened. The current paragraph at
   `README.md:38` is accurate but long - it is one 120-word block. Cut it to
   its point: one model is simultaneously the best choice for `next_hop`
   (20/20, beating sonnet's 19/20, at ~1/83rd the cost) and unusable for
   `eta_estimate` (0/20), which is why routing is per decision type. Keep the
   sample-size caveat. Keep the "`python -m toyworld` prints these same
   numbers" line - it is verified true.
6. **How it is built** - the four craft points. Already correct; keep, tighten
   if it helps.
7. **Reproducibility** (`casting.yaml`), **AI disclosure**, **team**, and the
   issue-first workflow note. These are the base of the scroll, not the top.

**Remove:**

- The `**Status:** ... This README gets a full rewrite before submission` line.
  This IS that rewrite; leaving it is self-contradicting.
- The internal submission checklist at the bottom. It is a project-management
  artifact, not something a judge should read, and an unticked box reads as an
  admission of incompleteness.

**Do not turn it into a dashboard tour.** The ticket is explicit about that.

**Length:** aim for something a judge scrolls once. If it runs past roughly 120
lines, cut prose rather than dropping a required section.

## Verification

- Every figure recomputed against `docs/visuals/run-data.js` and stated in your
  report with the computation.
- Confirm the embedded image path resolves from the repo root as GitHub renders
  it (the file exists at that exact relative path, correct case).
- Confirm no removed section was one of the four required keeps (disclosure,
  casting.yaml, CI badge, and nothing-untrue).
- Read the result once, start to finish, as a judge who has never seen this
  repo. Note in your report anything a first-time reader would misunderstand.

## After implementation

**`README.md` is a shared file owned by Mukund, and issue #59 states he signs
off on this one before merge.** Open the PR; do not merge it. Say clearly in
the PR body that it awaits his sign-off, and summarise what was removed so he
can object to a specific line rather than re-reading the whole diff.
