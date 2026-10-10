---
name: clef-browse-fast
description: Use for one small browser task in the running BrowserOS Neo browser, such as open a page, fill a field, or click a button. Not for reading page text or for long tasks.
---

# clef-browse-fast

Run one small task on one page with the `browser_task` tool.

## Write the goal

- Name each control with the label that the page shows.
- Put the exact text to type in quotation marks, and write "exactly". Without the text, the model writes its own text.
- End with a finish condition that the page shows. Example: "You are done when the heading says 'Welcome'."
- Keep one goal to one page. Use more calls for more pages.

## Handle the risky actions

- The tool stops with `needs_approval` before a risky click. Risky labels are delete, send, pay, confirm, publish, remove, sign out, submit, purchase, and Post.
- Show the user the `risky` label. Set `allow_risky_actions` to true only after the user approves that exact action.
- Never approve a public post, a payment, or a delete for the user.
- The check reads labels only. A risky control with a neutral label, such as a heart icon, passes.

## Read the result

- The result has `status`, the final URL, and the title. It has no page text. Use Neo's read tools for page text.
- `blocked` means that no offered action makes progress. Rewrite the goal. If the page loads slowly, raise `CLEF_BROWSE_SETTLE_MS`.
- `done` means that the model believes the goal is met. Check the result when the cost of an error is high.
- Some sites keep unsent text. A task that stops before the send button can leave a draft in the box.

## Run tasks in parallel

Each call opens its own tab. Parallel calls on different pages work. The authors measured 3 parallel tasks in 12 s of wall time.
