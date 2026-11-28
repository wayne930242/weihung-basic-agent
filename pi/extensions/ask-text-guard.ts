import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const backReference = /上面|上述|以上|如上|above|as explained/i;

interface Question {
  question: string;
  options: { label: string; description: string }[];
}

function refersBack({ question, options }: Question): boolean {
  return backReference.test(question) || options.some(({ label, description }) =>
    backReference.test(label) || backReference.test(description));
}

export default function askTextGuard(pi: ExtensionAPI): void {
  let hasVisibleText = false;

  pi.on("message_end", ({ message }) => {
    if (message.role === "assistant") {
      hasVisibleText = message.content.some((part) => part.type === "text" && part.text.trim().length > 0);
    }
  });

  pi.on("tool_call", (event) => {
    if (event.toolName !== "ask_user_question" || hasVisibleText) return;
    // Pi validates the custom tool's input before dispatching tool_call.
    const questions = event.input.questions as Question[];
    if (!questions.some(refersBack)) return;
    return {
      block: true,
      reason: "This question refers to an explanation the user cannot see. Write the explanation as visible text first, then call ask_user_question again in that message.",
    };
  });
}
