# The right-sizing loop

The hero action of this build: **an agent reads what each model costs per correct
decision, proposes moving a decision type to a cheaper model, a human approves,
and the next run proves quality held while the bill fell.**

SigNoz's stance, which this loop exists to honor: *agents propose, humans decide.*
Nothing here auto-heals. The agent's reach stops at a proposal.

## Why a file, not a flag

The thing that changes when you approve a reroute is `toy-world/routing.json`:

```json
{
  "route_choice": "anthropic/claude-sonnet-4.6"
}
```

One line per decision type, naming the model that serves it. It is a committed
file rather than a command-line flag or an environment variable for three
reasons:

1. **A proposal becomes a diff you can read before you say yes.** "Nothing changes
   until a human approves" is only checkable if the change is visible.
2. **The before and after are reproducible from git**, not from someone's shell
   history.
3. **It keys on decision type, not on the whole program.** Right-sizing targets a
   *kind* of decision. The toy world has one (`route_choice`); a real substrate
   has several, and you would reroute filler-word detection without touching
   quote extraction.

An unpriceable or unknown model in this file fails loudly at load, before any
model call is placed or any span is emitted. A bad approval costs nothing.

## The four beats

### 1. Establish the baseline (human runs this)

```bash
cd toy-world
python -m toyworld --live --production
```

Runs only the model `routing.json` currently assigns. Prints cost per correct
decision and exports the spans and metrics to SigNoz. This is the "before".

### 2. The agent reads and proposes (read tools only)

In a Claude Code session **rooted in this repo** (the MCP server only loads when
the repo is the workspace root), ask the agent to look at cost per correct
decision by model and say whether the current routing is right-sized.

It uses the SigNoz MCP server's read tools - `signoz_query_metrics`,
`signoz_execute_builder_query`, `signoz_get_dashboard` against the
"Gradebook: Cost per Correct Decision" dashboard. Every read tool is
pre-approved in `.claude/settings.json`, so proposing is frictionless.

A proposal must state four things, or it is not actionable:

- which decision type
- from which model to which model
- the correct-rate for both, with the sample size
- the expected cost change

### 3. The human approves (or does not)

Approval is the human typing yes to a specific, named edit. Every SigNoz write
tool and any edit to `routing.json` is in the `ask` list, so the agent cannot
apply its own proposal even if it wanted to. That is the gate, and it is
configuration rather than good intentions.

### 4. Apply, then prove it (the same command as beat 1)

The approved edit lands in `routing.json`. Re-run:

```bash
python -m toyworld --live --production
```

Same junctions, same grader, same telemetry shape - only the routed model
changed. The claim is earned only if **correct-rate held and cost per correct
fell**. If correctness dropped, the honest move is to revert the routing and say
so: a right-sizing tool that only ever recommends "cheaper" is a cost tool
wearing a quality costume.

## SigNoz-side writes go through the same gate

Rerouting is the hero, but the same propose-approve-apply shape covers the
observability changes around it: adding a panel, creating a saved view scoped to
the rerouted decision type, adjusting an alert threshold after the cost base
moves. Those run through the MCP write tools, which are all in the `ask` list
for exactly the same reason.

## Honest limits

State these rather than hope nobody asks.

- **The toy world is three junctions.** A production run is 3 decisions on one
  model. "Quality held" over a sample that small is a demonstration of the
  mechanism, not a statistical result. The real substrate (CleanCut, ticket #11)
  is where the sample gets big enough to mean something.
- **Cheaper is not always right-sized.** The committed replay recording shows
  the opposite outcome - the cheaper models score *worse* there (4/6 and 1/3
  against 3/3). That is the honest case for why you measure per decision type
  instead of assuming, and it is worth showing rather than hiding.
- **The loop measures what it can check.** Every grade here is a math grade
  against the world's known fastest route. A decision with no machine-checkable
  right answer cannot be right-sized this way, and the layer says so instead of
  substituting an AI judge's opinion for a fact (ADR 0001).
