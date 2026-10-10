# Measured results

This document gives the numbers that the authors measured. It also states what the numbers do not show.

## Method

- Computer: one Mac with Apple silicon (arm64).
- Browser: BrowserOS Neo 0.0.68, which is based on Chrome 155.
- Decision model: Cloudflare Workers AI over the REST API. Each table names the model.
- Test page: `tests/site/index.html`, served on `127.0.0.1`. It has a name field, a size list, a Save button, and a Submit order button.
- Other page: `https://example.com`.
- Check of the result: the authors read the page state through a separate CDP session, not from the agent itself.
  For the latest runs, they also read the page text at the final decision.

**The authors measured no baseline. This project makes no claim that it is faster than another tool.**
Each test used few runs on two pages. Treat the numbers as an indication, not as a benchmark.

## Results with `clef` (the supported model)

| Test | Result |
| --- | --- |
| Form task: type a name, choose a size, click Save. 9 runs on the test page | 9 of 9 ended with `done`. |
| Cost and size of one form task (6 runs in one batch) | 4 decisions, 8,242 input tokens, $0.00198. |
| Time of one form task (same 6 runs) | 3.5 to 5.5 s in total. The mean time of one decision was 561 to 1,087 ms. |
| Final page text of one form task | It contained `saved:Grace Hopper:large`. |
| Link task on `example.com` with a finish condition | `done` after 1 step. 3,619 input tokens. |
| Task that cannot be done ("Click the Download invoice button") | `blocked` after 0 steps, as expected. |
| Replay of 8 saved page states | 8 of 8 correct. Median time 535 ms. |

The replay used 6 states where an action or `DONE` is right, and 2 states where `BLOCKED` is right.

## Real-world test: the daily Substack routine

The authors tested the tool on a real signed-in Substack account in Neo. They followed the mechanical steps of a daily
routine for a newsletter: open the Notes composer, type a Note, and prepare replies to other writers' Notes.

**The tests posted nothing.** Each test stopped before the Post button. A harness blocked any publishing click, whatever the
tool did. After the tests, the authors read the replies of the test Note through the Substack API. The list was empty.
The model was `clef`.

| Test | Result |
| --- | --- |
| Open the Notes composer | `done` after 1 step. |
| Type a draft into the Note composer | `done` after 2 steps. The editor held the text. The Post button was enabled. |
| Open a reply box and type the exact text, 5 runs, the saved draft cleared before each run | 5 of 5 typed the exact text. Each run took 2 steps. |
| The same, with the goal "Type a short reply draft" | 0 of 3. The model wrote its own reply each time. |
| Prepare 3 replies at the same time, one on each of 3 writers' Notes | 3 of 3 `done` in 12.0 s of wall time. Each tab showed the correct parent Note and the exact text. |
| Goal that ends with "click Post" | `needs_approval` with the label `Post`. The program did the two steps before it and did not click Post. |

Each task used 3 to 5 decisions and 7,394 to 13,286 input tokens. That is $0.0018 to $0.0032 for each task.

### Defects that the test found

1. **The page was not ready.** The reply box was disabled for a short time after load. The engine skips disabled
   controls, so it saw no reply box. Clef chose "none", and the task ended with `blocked` after 0 steps. The program now
   waits until the page stops changing before the first observation. See
   [Configuration](configuration.md#page-settle-wait).
2. **The gate did not know "Post".** The button that publishes a Note or a reply was not on the list of risky terms.
   The word `post` is now risky at the start of a label. The label `New post` is not risky, because it only opens
   the Note composer.
3. **The model wrote its own text.** With a vague goal, the text model wrote a reply that nobody asked for. Give the
   exact text in quotation marks. See [Usage](usage.md#quote-the-exact-text-to-type).
4. **Substack keeps unsent text.** After a task, the reply box showed the text of the earlier task. The authors had
   first counted these restored drafts as typed text, and the result was wrong. They then removed their own drafts
   before each run and counted again. See [Safety](safety.md#known-gaps).

### Cost of the settle wait

The wait adds time before the first observation. The table shows the median of 5 runs of the step that opens the tab and
waits. The runs used a stub decision function, so they cost no Clef tokens.

| Page | Wait off (`0`) | Wait on (`500`) |
| --- | --- | --- |
| Local test page | 210 ms | 728 ms |
| `https://example.com` | 255 ms | 736 ms |
| A Substack Note | 1,732 ms | 3,433 ms |

Set `CLEF_BROWSE_SETTLE_MS=0` for static pages when the extra half second matters.

## Results that do not depend on the model

The authors measured these numbers with `clef-flash`. The browser steps are the same for `clef`.

| Measurement | Result |
| --- | --- |
| Open a tab, attach, and navigate | 226 to 229 ms for the local page. 524 ms for `example.com`. |
| Read the page and do the action, inside a task on the local page | 61 to 131 ms. |
| Input tokens in one Clef request | 1,071 to 2,643, with 1 to 29 elements offered. |

## Results with `clef-flash` (removed)

The authors measured these numbers before they removed `clef-flash`. They show how the program behaves. They do not
describe `clef`.

| Test | Result |
| --- | --- |
| Time of one Clef request, 24 requests | Minimum 527 ms. Median 704 ms. 90th percentile 885 ms. Maximum 1,352 ms. |
| Risky "Submit order" click without approval | `needs_approval` after 0 steps. The page did not change. |
| The same click with approval | The program did the click one time. The page showed `submitted`. |
| Two tasks at the same time | Both ended with `done`. Each task used its own tab. Both tabs closed. |
| Form task with the Name field empty, 8 runs | 8 of 8 `done`. The median time was 5.7 s, with the text provider call. |
| Form task on the shipped test page, 6 runs | 0 of 6. All six ended with `blocked`. |
| One task from a new process, `example.com` | `done` in 3.99 s in total. A new process sets up its connection first. |

## Why `clef-flash` is not supported

On the shipped test page, the Name field starts with the value `Ada`. The goal was "Type the name Grace Hopper into the
name field, choose size large, and click Save."

1. `clef-flash` typed the name. This was correct.
2. `clef-flash` chose the size Large. This was correct.
3. At the third decision, the page showed Name `Grace Hopper`, Size `Large`, and the Save button.
4. `clef-flash` gave `BLOCKED` a probability of 0.34 and `CLICK` a probability of 0.29. The task ended.

Clef gives the same answer for the same request. A second run does not help. The authors changed the wording of the
rules in 5 ways. The difference between the two probabilities stayed between 0.02 and 0.06 in both directions. So a
prompt change was not a fix.

The authors replayed 8 saved page states. Each state has a known correct operation.

| Model | Correct | Median time | Confidence of the correct answers |
| --- | --- | --- | --- |
| `clef-flash` | 7 of 8. It was wrong on the Save click. | 786 ms | 0.10 to 0.85 |
| `clef` | 8 of 8 | 535 ms | 0.22 to 0.94 |

`clef-flash` with a second request to `clef` for low-confidence answers also worked. In 3 runs, all ended with
`done`. Three of the four decisions in each run used both models.

Each combined run used 14,389 input tokens and cost $0.00179. `clef` alone used 8,242 input tokens and cost $0.00198.
The combination cost about 10% less. It was also slower: 6.3 to 8.5 s, against 3.5 to 5.5 s for `clef` alone.

It also needed more code. The authors removed both `clef-flash` and the second request.

`clef` costs about 6.3 times more for each token than `clef-flash`. The prices are $0.24 and $0.038 for each
1 million input tokens.

## Text provider comparison

The authors compared four models on one saved `TYPE_TEXT` request. They made 12 calls to each model. The goal gave no
value, so a model that returns no text can be correct.

| Model | Valid answers | Median time |
| --- | --- | --- |
| `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | 8 of 12 | 573 ms |
| `@cf/zai-org/glm-4.7-flash` | 4 of 12 | 18.5 s |
| `@cf/mistralai/mistral-small-3.1-24b-instruct` | 0 of 12 | Not recorded |
| A fourth model | The test did not finish. | Not recorded |

The model `@cf/meta/llama-3.1-8b-instruct` returned HTTP 410 and was not compared.

## What the numbers do not show

- No comparison with another tool.
- No test on a computer other than one Mac.
- No test on a large page, on a page with a login, or on a page with a frame.
- No test of the Neo replay. See [Safety](safety.md#known-gaps).
- No test of a call from inside an OMP session. The authors drove the same MCP server over stdio.
- No post, restack, like, or follow ran on a real account. The tests did not check the quality of a real reply.
- The tool returns the status and the final page address. It does not return the text of the page. A caller that must
  read Notes needs a separate reader.
