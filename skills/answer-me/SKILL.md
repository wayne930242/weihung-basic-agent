---
name: answer-me
description: Use when the user invokes /skill:answer-me to ask a real question, not give an instruction; answer it and change nothing.
disable-model-invocation: true
---

# Answer me

The user invoked this to ask a question. They want to understand, not to have something done. A question about a problem ("why does X keep happening?", "isn't Y missing?") is still only a question.

1. **Answer what was asked.** Read, search, and run read-only commands as far as the answer needs. Lead with the direct answer, then the cause and the evidence for it (file:line, command output, log line). Say what you verified and what you infer.
2. **Change nothing.** Make no edit, commit, push, deploy, config change, dispatch, message to another session, or other action with effects. If you started a change on your own while answering, stop and say so.
3. **Offer, don't do.** When a fix or next step follows from the answer, name it in a sentence or two with your recommendation, then stop and wait for the user to say to do it.
4. **Answer every part.** When the question has several parts or hides a second question (for example "why didn't you explain?"), answer each one.

The skill ends with the answer. Work that was already running before the question goes on as it was.
