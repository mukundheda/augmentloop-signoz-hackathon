/**
 * Canonical serialization and digests.
 *
 * Two identifiers in this protocol are digests over serialized JSON, and both
 * are computed independently by the Python reference implementation. If the two
 * languages disagree by a single byte the identifiers diverge and the protocol
 * silently stops being language neutral, so the exact form is pinned here and
 * documented rather than left to each language's default JSON writer.
 *
 * CANONICAL FORM (the Python side must match this byte for byte):
 *
 *   Equivalent to Python's
 *       json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
 *   with exactly ONE deliberate deviation, for numbers.
 *
 *   1. Objects: keys sorted ascending by Unicode code point, no whitespace,
 *      "key":value pairs joined by ",".
 *   2. Arrays: order preserved, elements joined by ",".
 *   3. Strings: double quoted. Escape \" and \\, the control characters as
 *      \b \f \n \r \t, any other character below 0x20 as \u00xx, and every
 *      character at or above 0x7f as \uxxxx (lowercase hex, surrogate pairs
 *      written as two escapes). This is Python's ensure_ascii=True behaviour.
 *   4. true / false / null are written as those literals.
 *   5. NUMBERS (the deviation): JSON's grammar allows several spellings of the
 *      same value and Python and JavaScript pick different ones (Python writes
 *      3e-06 where JavaScript writes 0.000003), so neither language's default
 *      is usable. The rule instead is:
 *        - a value that is an exact integer is written as its decimal digits
 *          with no decimal point and no exponent, e.g. 2.0 -> "2";
 *        - otherwise it is written with exactly 6 decimal places, then trailing
 *          zeros and any trailing "." are removed, e.g. 0.000003 -> "0.000003".
 *      Six places is enough for per-million-token USD rates and removes the
 *      exponent question entirely. Values outside +/-1e15, NaN and Infinity are
 *      rejected rather than serialized, because their spellings are not stable.
 *   6. undefined is not serializable. An absent field must be omitted by the
 *      caller or passed as null, so that "missing" and "null" cannot silently
 *      collapse into each other.
 */

import { createHash } from "node:crypto";

export class CanonicalizationError extends Error {}

const CONTROL_ESCAPES: Record<string, string> = {
  "\b": "\\b",
  "\f": "\\f",
  "\n": "\\n",
  "\r": "\\r",
  "\t": "\\t",
  '"': '\\"',
  "\\": "\\\\",
};

function canonicalString(value: string): string {
  let out = '"';
  for (const char of splitUtf16(value)) {
    const escape = CONTROL_ESCAPES[char];
    if (escape !== undefined) {
      out += escape;
      continue;
    }
    const code = char.charCodeAt(0);
    if (code < 0x20 || code >= 0x7f) {
      out += "\\u" + code.toString(16).padStart(4, "0");
      continue;
    }
    out += char;
  }
  return out + '"';
}

/** Iterate UTF-16 code units, not code points: astral characters must become a
 * surrogate PAIR of escapes, which is what Python's ensure_ascii emits. */
function splitUtf16(value: string): string[] {
  const units: string[] = [];
  for (let i = 0; i < value.length; i += 1) units.push(value.charAt(i));
  return units;
}

export function canonicalNumber(value: number): string {
  if (!Number.isFinite(value)) {
    throw new CanonicalizationError(`non-finite number is not canonicalizable: ${value}`);
  }
  if (Math.abs(value) >= 1e15) {
    throw new CanonicalizationError(`number out of canonical range (|n| < 1e15): ${value}`);
  }
  if (Number.isInteger(value)) return String(value === 0 ? 0 : value);
  const fixed = value.toFixed(6);
  const trimmed = fixed.replace(/0+$/, "").replace(/\.$/, "");
  return trimmed === "-0" ? "0" : trimmed;
}

export function canonicalize(value: unknown): string {
  if (value === null) return "null";
  switch (typeof value) {
    case "boolean":
      return value ? "true" : "false";
    case "number":
      return canonicalNumber(value);
    case "string":
      return canonicalString(value);
    case "object":
      break;
    default:
      throw new CanonicalizationError(`value of type ${typeof value} is not canonicalizable`);
  }
  if (Array.isArray(value)) {
    return "[" + value.map((item) => canonicalize(item)).join(",") + "]";
  }
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record)
    .filter((key) => record[key] !== undefined)
    .sort(compareByCodePoint);
  const parts = keys.map((key) => canonicalString(key) + ":" + canonicalize(record[key]));
  return "{" + parts.join(",") + "}";
}

/** Array.prototype.sort compares UTF-16 code units; Python sorts code points.
 * They differ only for astral characters, so compare code points explicitly. */
function compareByCodePoint(a: string, b: string): number {
  const left = [...a];
  const right = [...b];
  const shared = Math.min(left.length, right.length);
  for (let i = 0; i < shared; i += 1) {
    const diff = (left[i] as string).codePointAt(0)! - (right[i] as string).codePointAt(0)!;
    if (diff !== 0) return diff;
  }
  return left.length - right.length;
}

export function sha256Hex(text: string): string {
  return createHash("sha256").update(Buffer.from(text, "utf8")).digest("hex");
}

/** sha256 over the canonical serialization of a value. */
export function canonicalDigest(value: unknown): string {
  return sha256Hex(canonicalize(value));
}
