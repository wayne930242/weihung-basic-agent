---
name: briefing-gpt-agents
description: "Use when writing a subagent brief, follow-up, or resume message for a GPT model (openai or openai-codex, such as astra, sol, luna, codex), or when a GPT worker stopped early, did one batch of many, or reported partial progress as its final result."
---

# Briefing GPT agents

GPT-5.x models end long agentic tasks early unless the prompt tells them to persist; OpenAI reports this as promptable. Astra workers here ended after about 25 of 577 ledger rows in three runs in a row, until the brief carried the block below.

## Steps

1. **Open the brief with the persistence block**, verbatim, then the task:

   ```
   <solution_persistence>
   You are an agent - please keep going until the task is completely resolved, before ending your turn and yielding back to the caller. Only terminate your turn when you are sure that the problem is solved.
   - Persist until the task is fully handled end-to-end within the current turn: do not stop at analysis, partial fixes, or the first batch; carry the work through implementation, verification, and a clear report of outcomes.
   - Bias to action: inside the authorizations below, proceed on reasonable assumptions instead of asking.
   - Ending your turn ends the job: a final report before the stop condition holds is a failure.
   </solution_persistence>
   ```

2. **State one checkable stop condition** (the anchor), such as `pending is 0 or 200 entries written` or `npm test -- foo green on the final commit`. Name the only early exits: a decision outside the stated authorizations (`caller_ping`, then stop), or a blocker that no rule covers.
3. **For volume work, give the loop and its state.** Example: "Take 25 rows, act, verify, update the ledger, take the next 25." The ledger or todo is the state. A tight context compresses notes and keeps looping; it is not a reason to stop.
4. **Ask for no progress updates or upfront plan messages during the run.** OpenAI's Codex guide finds that requested preambles and status updates make the model stop abruptly. The only report is the final one.
5. **Make scope explicit**: allowed files or systems, and "do not expand the problem surface". GPT-5.2 follows instructions closely, and it widens scope when the brief leaves it open.
6. **Remove contradictions** before sending, such as "be brief" beside "be thorough" with no condition between them. GPT-5.x obeys both and stalls between them. State which one wins in which case.

## When a GPT worker returns early

Resume the same session (`subagent_resume`) instead of spawning a fresh one. The message repeats the persistence block, the stop condition, the remaining count, and the answer to any question it asked.

---

Derived from OpenAI Cookbook `examples/gpt-5/gpt-5_prompting_guide.ipynb` (persistence), `gpt-5-1_prompting_guide.ipynb` (`<solution_persistence>`, contradiction metaprompt), `gpt-5-2_prompting_guide.ipynb` (scope discipline), and `codex_prompting_guide.ipynb` (Autonomy and Persistence; preambles cause early stops). Repository: openai/openai-cookbook, revision `dfd760b`.
