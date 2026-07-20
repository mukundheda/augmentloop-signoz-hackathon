# AugmentLoop x Agents of SigNoz - hackathon build

Team repo for the Agents of SigNoz hackathon (July 20-26 2026), Track 01: AI & Agent Observability. Four humans (Mukund, Vedant, Rutik, Anish) plus their agent sessions work here concurrently.

## Hard rules (hackathon submission requirements)

- `casting.yaml` + `casting.yaml.lock` at the repo root MUST stay current with the actual SigNoz deployment. Judges may re-run Foundry against them. If you change the deployment, re-cast and commit both files in the same PR.
- This repo goes PUBLIC at submission. Never commit client names, client data, API keys, tokens, tunnel URLs, or personal emails. Secrets go in `.env` (gitignored); use placeholders in committed examples.
- AI use is disclosed in README.md. Keep commits honest; the history is the disclosure audit trail.
- SigNoz's stance, which we honor in all copy and design: "agents propose, humans decide." Any write action is human-approved. Never describe anything as "auto-heal".

## Agent skills

The pipeline skills live in `.claude/skills/` (committed, shared by the whole team). The flow for any non-trivial change:

1. `/grill-with-docs` - sharpen the idea, one question at a time (updates CONTEXT.md and ADRs as decisions land)
2. `/to-spec` - publish the spec as a GitHub issue
3. `/to-tickets` - break it into vertical-slice tickets with blocking edges, assign owners
4. `/implement` - one ticket per FRESH session, TDD at the seams the spec agreed, then `/spec-review` before commit
5. Bugs found along the way become issues; `/triage` moves them to ready-for-agent with a brief

Ask `/ask-matt` (read its "This repo's adaptations" section first) when unsure which skill fits.

### Issue tracker

Issues live in this repo's GitHub Issues, driven via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles map 1:1 to labels here (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` (glossary) at the root, ADRs in `docs/adr/`. Created lazily by `/domain-modeling`; consumer rules in `docs/agents/domain.md`.

## Team conventions

- Edit your own module; shared files (this file, README, casting.yaml, CI) are owned by Mukund - ask before touching.
- One ticket = one branch = one PR. Reference the issue number in the branch name and PR title.
- Merge small and often. Long-lived branches die in hackathons.
- A ticket is done when `/spec-review` passes both axes and the full test suite is green.

## SigNoz references

- Foundry casting: github.com/SigNoz/foundry (docs/concepts/, docs/reference/casting-file.md)
- SigNoz MCP server: 28 read + 13 write tools (alerts, dashboards, views, notification channels); auth via `SIGNOZ-API-KEY` header at `http://localhost:8000/mcp`
- SigNoz Claude Code plugin (optional, per person): `/plugin marketplace add SigNoz/agent-skills` then `/plugin install signoz@signoz-skills`
- LLM instrumentation docs: signoz.io/docs/llm/ (OpenAI, Gemini, LiteLLM, Traceloop, Langtrace)
