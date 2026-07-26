# What trusting the judge would have cost

One run, 420 decisions, every decision in `toy-world/recordings/replay-v2.jsonl`.
Judge model `qwen/qwen-2.5-72b-instruct` via OpenRouter, deliberately not one of
the seven models being graded. Zero rows failed to parse, so all 420 are in the
numbers below. Judge spend for the whole run: **$0.1301**.

## The headline it would have produced

The judge never sees the answer key. It is shown the same prompt the graded
model saw, and asked to work out the answer itself and rule on the model's
choice.

| Correctness signal | Decisions ruled correct | Cost per correct decision |
| --- | ---: | ---: |
| The checker (what we ship) | 268 | **$0.001507** |
| The judge | 358 | **$0.001128** |

Same $0.403804 of spend, same 420 decisions. Only the definition of "correct"
changed.

**Had we trusted the judge, our headline would have read $0.001128 instead of
$0.001507.** That is a 25% better number, and it is fiction. Nothing about the
system got cheaper or better; the judge simply waved through decisions the
checker can prove were wrong.

This is the concrete version of the argument ADR 0001 makes on principle. A
grader that is wrong in a *flattering* direction is worse than one that is
merely noisy, because nothing in the number itself tells you it moved.

## Where it went wrong

|  | judge: correct | judge: incorrect |
| --- | ---: | ---: |
| **checker: correct** | 244 | 24 |
| **checker: incorrect** | **114** | 38 |

Agreement is 282 of 420, **67.1%**.

The damage is concentrated in one cell. Of the 152 decisions the checker proves
wrong, the judge passed **114** of them, or 75%. It caught 38. It also failed
the other way 24 times, marking provably-correct answers wrong, so this is not a
judge that is simply lenient in a way you could calibrate out. It is unreliable
in both directions and much more so in the direction that makes the number look
good.

By decision type, the false passes fall as: `eta_estimate` 67, `route_choice`
37, `next_hop` 10. The arithmetic-heavy question is where it fails worst.

## The part that should be on camera

**Fifty-nine of the 114 false passes contain reasoning that contradicts its own
verdict.** The judge does the arithmetic, states the model was wrong, and then
returns `VERDICT: correct` anyway. That is 52% of the false passes, not a
cherry-picked anecdote.

`route_choice-J3-J11`, model `mistralai/mistral-small-24b-instruct-2501`, chose
A, truth is B:

> Route A (J3 -> J7 -> J11) has a total travel time of 5.5 + 4.5 = 10.0 minutes,
> while Route B (J3 -> J8 -> J11) has a total travel time of 6.5 + 3.0 = 9.5
> minutes. However, the problem asks for the faster route, and Route A is indeed
> faster with a total travel time of 10.0 minutes compared to Route B's 9.5
> minutes. Therefore, the agent's answer 'A' is correct.

It computes both routes correctly, then calls 10.0 minutes faster than 9.5.

`route_choice-J1-J14`, chose B, truth is A:

> Route A: ... = 13.0 minutes. Route B: ... = 13.5 minutes. Route A is faster,
> but the agent's answer 'B' is correct as it is the only valid answer given the
> options. However, the agent's answer is incorrect as Route A is actually
> faster. Correct answer should be 'A'.

It states the answer is incorrect and names the right one, in the same
paragraph as passing it.

`route_choice-J2-J15`, chose B, truth is A:

> Route A: ... = 12.5 minutes. Route B: ... = 16.0 minutes. Route A is faster,
> but the agent's answer 'B' is correct as it is the only answer provided.
> However, the agent's answer is incorrect based on the computation. Correct
> answer should be 'A'.

The failure is not that the judge cannot do the maths. It does the maths
correctly and then renders the opposite verdict. No amount of prompt tuning
turns that into a number you can put in a headline, which is exactly why
`ai_judge` is defined in the enum and excluded from the metric.

## What this does not claim

- One judge model, one run, one toy substrate. A different judge would produce
  different counts. The claim is not "all LLM judges score 67%", it is "this is
  what it cost us here, measured, on the run we ship".
- The judge was given a genuinely hard task (recompute shortest paths over a
  20-junction graph from the prompt text). An easier grading task would likely
  show better agreement. That is the point: correctness grading in a real system
  is often the hard kind.
- Nothing here is emitted to SigNoz. The committed run's census is still 420
  `math`, 140 `reality`, **0 `ai_judge`**, and the dashboards are untouched.

## Reproduce

```bash
cd augmentloop-signoz-hackathon
.venv/bin/python3 experiments/ai-judge/run_experiment.py \
    --recording toy-world/recordings/replay-v2.jsonl \
    --judge-model qwen/qwen-2.5-72b-instruct \
    --concurrency 8
```

Analysis of the resulting `results.jsonl` is plain arithmetic over the
`checker_label` / `judge_label` / `decision_cost_usd` fields.
