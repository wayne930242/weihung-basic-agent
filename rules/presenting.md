# Presenting to the user

The user does not read code diffs; describe a change instead.

When an answer has several parts, compares options, or needs the user's confirmation, write one HTML page at `/tmp/<task>-<topic>.html` and open it with `show_doc`; the chat then gives the conclusion in a line or two.
The page opens in the user's default browser with the `pi-herdr-doc-review` page kit injected, so write bare semantic HTML: no `<style>`, no `<script>`, no CSS framework. The kit styles headings, tables, code, and `details` in light and dark mode, and gives `<pi-callout>`, `<pi-grid>` of `<pi-card>`, `<pi-badge>`, `<pi-options>` of `<pi-option>`, and `<pi-form>`; `show_doc`'s description lists their attributes.
Put the conclusion first.

Decisions the user must make go on a comparison page: one section per decision, its options side by side in `<pi-options>` with what each costs and changes (`pros`, `cons`), the recommended one marked `recommended`, and the evidence that tells them apart (screenshots, contact sheets, audio players, numbers), copied next to the page, since the page loads nothing from above its directory or from other sites.
End the page with one `<pi-form>` holding a `<pi-question>` per decision, the recommended `<pi-choice>` marked; the user's answers reach you as a message when they send it. A single short question with no page behind it goes through `ask_user_question` instead.

Adapted from HumanLayer's [show-me](https://github.com/humanlayer/skills/tree/main/plugins/show-me) (MIT, © 2026 HumanLayer).
