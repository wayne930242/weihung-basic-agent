# Presenting to the user

The user does not read code diffs; describe a change instead.

When an answer has several parts, compares options, or needs the user's confirmation, write one Markdown page at `/tmp/<task>-<topic>.md` and open it with `show_doc` and `view: "page"`; the chat then gives the conclusion in a line or two.
The page renders in the user's default browser with a built-in style, so write plain Markdown and no CSS or scripts. Use what `show_doc`'s description lists: GitHub alerts for callouts, `mermaid` blocks for diagrams, `diff` blocks for code changes, and `cards`, `options`, and `form` blocks of YAML. Draw a diagram instead of describing a flow in prose.
Put the conclusion first.

Decisions the user must make go on a comparison page: one section per decision, its options side by side in an `options` block with what each costs and changes (`pros`, `cons`), the recommended one marked, and the evidence that tells them apart (screenshots, contact sheets, numbers), copied next to the page, since the page loads nothing from above its directory or from other sites.
End the page with one `form` block holding a question per decision, the recommended choice marked; the user's answers reach you as a message when they send it, and comments they leave in the page's feedback panel arrive the same way. A single short question with no page behind it goes through `ask_user_question` instead.

Adapted from HumanLayer's [show-me](https://github.com/humanlayer/skills/tree/main/plugins/show-me) (MIT, © 2026 HumanLayer).
