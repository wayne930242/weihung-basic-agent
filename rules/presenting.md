# Presenting to the user

The user does not read code diffs; describe a change instead.

When an answer has several parts, compares options, or needs the user's confirmation, write one HTML page at `/tmp/<task>-<topic>.html` and open it with `show_doc`; the chat then gives the conclusion in a line or two.
The page renders in Chawan, about 80 columns wide, with no JavaScript, images, or remote files, so draw diagrams in `<pre>` and keep tables to four columns with `th { white-space: nowrap }`.
Put the conclusion first.
The page is for reading: ask the open questions with `ask_user_question` after opening it, each with your recommendation, never as a form on the page.

Decisions the user must make go on a comparison page: one section per decision, its options side by side with what each costs and changes, the recommended one marked, and the evidence that tells them apart (screenshots, contact sheets, audio players, numbers). Such a page opens in the user's Chrome (`open -a "Google Chrome" <file>`), not Chawan, so it may show images and audio; copy them next to the page. Then ask each decision with `ask_user_question`, at most four per round. A pick among many items (which takes to keep) may instead end with a button that copies the choices for the user to paste back.

Adapted from HumanLayer's [show-me](https://github.com/humanlayer/skills/tree/main/plugins/show-me) (MIT, © 2026 HumanLayer).
