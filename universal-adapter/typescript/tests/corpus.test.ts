/**
 * The parity test that matters: the SHARED fixture corpus.
 *
 * Python and TypeScript must accept and reject the same files. Neither
 * implementation authors the corpus, so this test is driven entirely by
 * universal-adapter/fixtures/index.json and adds no opinions of its own. If the
 * corpus is missing it skips with a clear message rather than failing, so the
 * suite is green whether or not the corpus has landed yet.
 */

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { validate, normalizeRecordKind, formatErrors } from "../src/validation.ts";

const FIXTURES_DIR = resolve(import.meta.dirname, "..", "..", "fixtures");
const INDEX_PATH = join(FIXTURES_DIR, "index.json");

interface CorpusCase {
  file: string;
  schema: string;
  expect: "valid" | "invalid" | "not_validated";
  container?: "single" | "array";
  role?: string;
  note?: string;
}

describe("shared fixture corpus", () => {
  if (!existsSync(INDEX_PATH)) {
    test("corpus is absent, so parity cannot be checked here", { skip: `no ${INDEX_PATH}` }, () => {});
  } else {
    const index = JSON.parse(readFileSync(INDEX_PATH, "utf8")) as { cases: CorpusCase[] };
    const cases = index.cases ?? [];

    test("the corpus index lists cases", () => {
      assert.ok(cases.length > 0, "fixtures/index.json lists no cases");
    });

    for (const testCase of cases) {
      const title = `${testCase.file} expects ${testCase.expect}`;
      test(title, () => {
        const path = join(FIXTURES_DIR, testCase.file);
        assert.ok(existsSync(path), `fixture file is missing: ${path}`);
        const parsed: unknown = JSON.parse(readFileSync(path, "utf8"));

        if (testCase.expect === "not_validated") {
          // Raw harness-shaped input. Validating it against a protocol schema
          // would be a category error, so the only assertion is that it parses.
          assert.ok(parsed !== undefined);
          return;
        }

        const kind = normalizeRecordKind(testCase.schema);
        assert.ok(kind, `unrecognized schema name in the corpus index: ${testCase.schema}`);

        const records =
          testCase.container === "array"
            ? (assert.ok(Array.isArray(parsed), `case declares container "array" but the file is not an array`),
              parsed as unknown[])
            : [parsed];

        records.forEach((record, position) => {
          const errors = validate(kind, record);
          const where = testCase.container === "array" ? ` (element ${position})` : "";
          if (testCase.expect === "valid") {
            assert.equal(
              errors.length,
              0,
              `expected valid${where} but got:\n${formatErrors(errors)}\nnote: ${testCase.note ?? ""}`,
            );
          } else {
            assert.ok(
              errors.length > 0,
              `expected invalid${where} but the record was accepted\nnote: ${testCase.note ?? ""}`,
            );
          }
        });
      });
    }
  }
});
