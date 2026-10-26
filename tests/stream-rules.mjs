import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { audit, blocksBash, loadStreamRules, readLessons } from "../scripts/lesson-audit.mjs";

// STREAM_RULES_DIR proves another repository's `.pi/rules` with the same harness.
const { ttsr, rules } = await loadStreamRules(process.env.STREAM_RULES_DIR);

test("the repository ships stream rules", () => {
  assert.ok(rules.length > 0);
});

for (const { name, rule, warnings, blocks, allows } of rules) {
  test(`${name} loads in TTSR and proves itself on its fixtures`, () => {
    assert.deepEqual(warnings, [], "TTSR warnings");
    assert.ok(rule, "TTSR built no rule");
    assert.ok(blocks.length > 0, "needs a `blocks` fixture: the recorded mistake the rule must stop");
    assert.ok(allows.length > 0, "needs an `allows` fixture: a safe neighbor the rule must let through");
    for (const command of blocks) assert.ok(blocksBash(ttsr, rule, command), `should block: ${command}`);
    for (const command of allows) assert.ok(!blocksBash(ttsr, rule, command), `should allow: ${command}`);
  });
}

const ownRules = { skip: Boolean(process.env.STREAM_RULES_DIR) && "uses this repository's rules" };

test("the audit counts only `lesson` keys as enforcement and lists bare mentions separately", ownRules, () => {
  const memory = mkdtempSync(join(tmpdir(), "lesson-audit-"));
  mkdirSync(join(memory, "daily"));
  writeFileSync(join(memory, "MEMORY.md"), [
    "# Long-term memory",
    "- [failure] Piping a test through `| tail -1` inside an && chain hid a red suite",
    "- [failure] a pre-commit hook ran `git stash` on the shared stack",
    "- [insight] git stash is shared by every worktree",
    "- [correction] read the user's decision verbatim before relaying it",
  ].join("\n"));
  writeFileSync(join(memory, "daily", "2026-10-18.md"), "- 01:02 [failure] used git stash again\n- 01:03 plain log line\n");
  const lessons = readLessons(memory);
  assert.equal(lessons.length, 4);
  const { covered, mentions, prose } = audit(rules, lessons);
  assert.equal(covered.get("no-pipe-tail-in-chain").length, 1, "paired through its lesson key");
  assert.equal(covered.get("no-git-stash").length, 0, "quoting a command is not enforcement");
  assert.equal(mentions.get("no-git-stash").length, 1, "only the quoted command sits at a command position");
  assert.equal(prose.length, 3);
});
