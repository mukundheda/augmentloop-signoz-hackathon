# Conformance: the contract is language-agnostic, executably (ticket #44)

ADR 0002's moat is that Gradebook extends a **cross-language** OpenTelemetry
standard. That was only ever proven in one language (the Python reference
library). This directory makes it real two ways:

1. **A second-language emitter** (`ts-emitter/emit.ts`) — TypeScript, **zero npm
   dependencies** (Node built-ins only), POSTing the OTLP/HTTP JSON the
   collector already accepts. It emits one conforming `gen_ai.evaluation.result`
   event with the two mandatory extension attributes.
2. **A conformance checker** (`check_conformance.py`) — the real artifact. It
   validates *any* implementation's emitted event against the frozen field
   table in [`docs/conventions.md`](../docs/conventions.md) §9, and depends on
   nothing but the standard library, so it can judge an emitter it did not
   write. It turns "language-agnostic" from a claim into a pass/fail.

## Emit a conforming event from TypeScript

One command (Node 22+, which runs `.ts` directly; SigNoz stack up):

```bash
node conformance/ts-emitter/emit.ts
```

It POSTs the event to `$OTEL_EXPORTER_OTLP_ENDPOINT` (default
`http://localhost:4318`) — find it in SigNoz Traces under service `gradebook-ts`
— and prints the same event as language-neutral JSON on stdout.

## Check any implementation's event

One command:

```bash
python conformance/check_conformance.py conformance/samples/conforming.json
```

Exit `0` = conforms (warnings allowed), `1` = one or more errors. Pipe the
emitter straight into it to prove the loop across languages:

```bash
node conformance/ts-emitter/emit.ts --json | python conformance/check_conformance.py -
# -> CONFORMS

python conformance/check_conformance.py conformance/samples/malformed-missing-grade-source.json
# -> [error] augmentloop.grade.source is mandatory on every grade / NONCONFORMING (exit 1)
```

`samples/conforming.json` is the **actual** output of the TypeScript emitter, so
the checker is validating a real non-Python implementation, not a Python
round-trip.

## Test

```bash
pytest conformance/tests
```
