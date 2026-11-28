import assert from "node:assert/strict";
import { test } from "node:test";
import manifest from "../package.json" with { type: "json" };

// Load through the package manifest: an unregistered guard cannot block the dialog.
const path = manifest.pi.extensions.find((entry) => entry.endsWith("/ask-text-guard.ts"));
const guard = path && (await import(new URL(`../${path}`, import.meta.url))).default;

function harness() {
  const handlers = new Map();
  guard?.({ on: (event, handler) => handlers.set(event, handler) });
  return (blocks, questions, toolName = "ask_user_question") => {
    const input = { questions };
    const call = { type: "toolCall", name: toolName, id: "c1", arguments: input };
    handlers.get("message_end")?.({ message: { role: "assistant", content: [...blocks, call] } });
    return handlers.get("tool_call")?.({ toolName, toolCallId: call.id, input });
  };
}

const standalone = {
  header: "部署",
  question: "部署到哪個環境？",
  options: [{ label: "測試區", description: "只讓測試者看到。" }, { label: "正式區", description: "對外開放。" }],
};
const thinking = { type: "thinking", thinking: "測試區只供內部使用。" };
const text = (value) => ({ type: "text", text: value });

for (const [field, phrase] of [
  ["question", "上面是我理解的，對嗎？"], ["question", "是否同意上述說明？"],
  ["label", "同意以上安排"], ["label", "如上"],
  ["description", "Use the choice ABOVE."], ["description", "Proceed as explained."],
]) {
  test(`blocks ${field} referring to unseen text: ${phrase}`, () => {
    const q = structuredClone(standalone);
    (field === "question" ? q : q.options[1])[field] = phrase;
    const result = harness()([thinking, text(" \n")], [standalone, q]);
    assert.equal(result?.block, true);
    assert.match(result.reason, /visible text/i);
  });
}

test("visible explanation permits the reference for this message only", () => {
  const send = harness();
  const questions = [{ ...standalone, question: "以上安排可以嗎？" }];
  assert.equal(send([thinking, text("我建議先部署到測試區。")], questions), undefined);
  assert.equal(send([thinking], questions)?.block, true);
});

test("standalone questions and unrelated tools pass without visible text", () => {
  const send = harness();
  assert.equal(send([], [standalone]), undefined);
  assert.equal(send([], [{ ...standalone, question: "As explained?" }], "another_tool"), undefined);
});
