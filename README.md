# AugmentLoop x Agents of SigNoz

Team AugmentLoop's entry for the [Agents of SigNoz](https://wemakedevs.org/hackathons/signoz) hackathon (WeMakeDevs x SigNoz, July 20-26 2026), Track 01: AI & Agent Observability.

**Status:** Building **Gradebook** - a report-card layer for AI decisions, shown on SigNoz. See `CONTEXT.md` for the glossary and issue #3 for the full spec. This README gets a full rewrite before submission.

## Team

- Mukund Heda ([@mukundheda](https://github.com/mukundheda)) - lead, integration
- Vedant - core engine
- Rutik ([@Rutik332](https://github.com/Rutik332)) - UI
- Anish - SigNoz configuration, content

## Reproducibility

SigNoz is deployed via [Foundry](https://github.com/SigNoz/foundry). The deployment is fully declared by `casting.yaml` (with `casting.yaml.lock` pinning exact versions), as required by the hackathon rules:

```bash
foundryctl cast -f casting.yaml
```

The MCP server molding is enabled; after casting, mint an API key in the SigNoz UI (Settings -> API Keys) and point an MCP client at `http://localhost:8000/mcp` with a `SIGNOZ-API-KEY` header.

## AI assistance disclosure

Per the hackathon rules, we disclose AI assistant use: this project is built with heavy use of Claude Code (Anthropic) and Gemini-based tooling across planning, implementation, testing, and documentation. All AI-generated work is reviewed by a team member before merging; the commit history is the audit trail. The agent workflow conventions the team follows live in `CLAUDE.md` and `.claude/skills/`.

## How we work (for judges and the curious)

Work flows issue-first: ideas are grilled into a spec, the spec is broken into vertical-slice tickets with explicit blocking edges (GitHub issue dependencies), and each ticket is implemented in an isolated agent session against pre-agreed test seams, then reviewed for both coding standards and spec fidelity before merge. The skills encoding this pipeline are committed in `.claude/skills/` (adapted from [mattpocock/skills](https://github.com/mattpocock/skills), MIT).

## Submission checklist

- [ ] `casting.yaml` + `casting.yaml.lock` current with the final deployment
- [ ] Blog post (Medium / Dev.to / Substack)
- [ ] Screencast
- [ ] This README rewritten for the final build (what it is, how to run it, architecture)
