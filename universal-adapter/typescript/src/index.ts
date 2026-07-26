/**
 * Package entry point: the TypeScript reference implementation of the Universal
 * Agent Evidence Protocol.
 *
 * Zero runtime npm dependencies, Node built-ins only, run directly by Node 22+.
 * That is not minimalism for its own sake: the project's claim is that this
 * contract is language neutral and checkable with nothing installed, and a
 * dependency tree would quietly undermine the claim it exists to demonstrate.
 *
 * The layering mirrors the protocol's own separation of concerns:
 *   models      the four record shapes
 *   validation  is this record legal, and if not, where and why
 *   identity    which decision is this, and have we seen it before
 *   evaluation  was it correct, and on whose authority
 *   costing     what did it cost, charged once, with coverage reported
 *   emission    the standard OpenTelemetry event that carries the verdict out
 */

export * from "./models.ts";
export * from "./validation.ts";
export * from "./identity.ts";
export * from "./evaluation.ts";
export * from "./costing.ts";
export * from "./emission.ts";
export { canonicalize, canonicalNumber, canonicalDigest, sha256Hex, CanonicalizationError } from "./canonical.ts";
