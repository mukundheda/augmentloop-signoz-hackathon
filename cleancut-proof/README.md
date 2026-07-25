# CleanCut real-substrate proof (T8)

Gradebook proven on a real, revenue-generating product. Two of CleanCut's AI
jobs have provable answers, so they get **math** grades (ADR 0001-clean):

- **Filler detection** - ground truth is a lexical scan against CleanCut's own
  `PURE_FILLERS` hesitation-sound list (um, uh, er...). Contextual fillers
  ("like", "actually") are deliberately excluded: they're judgment calls, and
  judgment calls don't feed the headline.
- **Quote extraction** - the pulled quote must be a verbatim substring of the
  transcript. Paraphrase = provably wrong.

Both run across the roster (Haiku / Sonnet / Gemini Flash via OpenRouter) with
a per-run budget cap, so the same job yields a **cost-per-correct by model**
comparison - the right-sizing story on real work.

CleanCut's **clip scoring** is the honest **reality** example: each historical
"publish / hold" decision (predicted viral_score vs the 0.45 gate) is graded
by what actually happened - the editor kept or discarded the clip - and the
late grade span-links back to the decision span. No invented engagement
numbers; unknown historical token counts mean *no* cost attribute, never a
fabricated one.

## Client-data rule (hard)

Nothing client-identifying enters this repo. Transcripts and the clips CSV are
**local inputs**; committed samples are synthetic. Capture screenshots/data
for the blog locally. This mirrors the team contract's public-repo rule.

## Run (capture, local-only inputs)

```bash
pip install -e reference-library -e cleancut-proof
set OPENROUTER_API_KEY=...            # required (roster calls)
set CLEANCUT_TRANSCRIPT=C:\local\real_transcript.txt   # optional, else synthetic sample
set CLEANCUT_CLIPS_CSV=C:\local\clips.csv              # optional, else synthetic sample
set PROOF_BUDGET_USD=0.50             # per-run cap (default)
python -m cleancutproof
```

Services in SigNoz: `cleancut-proof` (detections + historical clip decisions)
and `cleancut-outcomes` (late reality grades, span-linked back).

## Test (no key needed)

```bash
pip install -e "cleancut-proof[test]"
cd cleancut-proof && pytest
```
