# Usage

This document shows how to start a task and how to read the result.

## Terms

- **Task:** one goal that you give to clef-browse-fast.
- **Step:** one action in the browser, for example one click.
- **Decision:** one answer from Clef about the next action. A step needs one decision.
- **Neo:** the BrowserOS Neo browser.

## Command line

Check the setup first:

```bash
uv run clef-browse check
```

The command prints a JSON object with three values. Each value is `true` or `false`.

| Value | Meaning when `true` |
| --- | --- |
| `neo_mcp` | The command reached the Neo MCP server. |
| `neo_cdp` | The command reached the Neo CDP endpoint, and it is Chrome. |
| `clef_env` | The Cloudflare account ID and token are set. The command does not call Cloudflare. |

The exit code is `0` when all three values are `true`. Otherwise it is `1`.

Run a task:

```bash
uv run clef-browse run --url <start URL> --goal "<what to do>" [options]
```

| Option | Meaning |
| --- | --- |
| `--url` | Required. The page that the task opens first. |
| `--goal` | Required. The task in plain English. |
| `--allow-risky-actions` | Approve risky actions. Use it only after the user approves. |
| `--max-steps N` | Stop after N steps. The default is 60. |
| `--timeout-s N` | Stop after N seconds. The default is 180. |
| `--json` | Print the full result as one line of JSON. |

Without `--json`, the command prints `Status:`, `Outcome:`, and, if needed, `Approval required:` and `Error:`.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | The status is `done`. |
| `2` | The status is `needs_approval`. |
| `1` | Any other status. |

## MCP server

The server `clef-browse-mcp` talks to an MCP client over stdio. It exposes one tool, `browser_task`.

| Argument | Type | Required | Meaning |
| --- | --- | --- | --- |
| `url` | string | yes | The page that the task opens first. |
| `goal` | string | yes | The task in plain English. |
| `allow_risky_actions` | boolean | no | Approve risky actions. The default is `false`. |
| `max_steps` | integer | no | Overrides `CLEF_BROWSE_MAX_STEPS` for this task. |
| `timeout_s` | number | no | Overrides `CLEF_BROWSE_TIMEOUT_S` for this task. |

The tool returns the result as JSON text. The MCP field `isError` is `true` only when the status is `error`.

### Register the server in OMP

Add this entry to `~/.omp/agent/mcp.json`. Set `cwd` to the folder of this project. The server reads `.env` from `cwd`.

```json
"clef-browse": {
  "type": "stdio",
  "command": "uv",
  "args": ["run", "clef-browse-mcp"],
  "cwd": "/path/to/clef-browse-fast",
  "timeout": 300000
}
```

An OMP session reads its tool list when it starts. Start a new session after you add the entry.

## The result

Both the command line and the MCP tool return the same object.

| Field | Meaning |
| --- | --- |
| `status` | `done`, `blocked`, `needs_approval`, `limit`, or `error`. See the next table. |
| `outcome` | Equal to `status` when the status is `done` or `blocked`. Otherwise `null`. |
| `error` | A short message, or `null`. |
| `risky` | `{label, reason}` when the status is `needs_approval`. Otherwise `null`. |
| `steps` | The number of steps that the browser completed. |
| `model_calls` | The number of Clef requests. |
| `input_tokens`, `output_tokens` | The token counts that Clef reported. |
| `cost_usd` | The Clef cost of the task. See [Configuration](configuration.md#cost). |
| `timing_ms` | `total`, `attach`, `decide_total`, `browser_total`, and `decide_mean`, in milliseconds. `attach` includes the page settle wait. |
| `tab` | `{page_id, url, target_id}` of the tab that the task used. |
| `page` | `{url, title}` of the page when the task ended. |

### Status values

| Status | Meaning | What to do |
| --- | --- | --- |
| `done` | Clef decided that the page shows the goal. | Read the result. |
| `blocked` | Clef decided that no offered action can make progress. | Rewrite the goal. See below. |
| `needs_approval` | The next action is risky. The tool did not do it. | Ask the user. Then run again with approval. |
| `limit` | The task reached a step, time, or model-call limit. | Raise the limit or split the task. |
| `error` | A fault stopped the task. | Read `error`. See [Troubleshooting](troubleshooting.md). |

## Approve a risky action

1. Run the task without approval.
2. If the status is `needs_approval`, read `risky.label` and `risky.reason`.
3. Show the label to the user and ask for approval.
4. Run the task again with `--allow-risky-actions` or `allow_risky_actions: true`.

Approval covers each risky action one time in a task. If the same risky action comes up again, the status is
`needs_approval` again. The next run starts a new tab. It does not continue the old task.

## Write goals that finish

Clef marks a task `done` only when "every requirement is visibly satisfied". These rules follow from that.

### Give a finish condition that the page shows

The task "Click the 'Learn more' link" ended with `blocked`. The click worked, but the new page did not show
that it was the target of the link. The task "Click the 'Learn more' link. You are done when the page heading says
'Example Domains'." ended with `done` after 1 step.

### Quote the exact text to type

For a text field, a small text model writes the text from your goal. If the goal does not give the text, the model
writes its own. It can write content that you did not intend.

The authors tested this on a reply box. The goal "Type a short reply draft" made the model write its own reply in
3 of 3 runs. All 3 runs gave the same text:

> That's really interesting, what was the batch import feature like to implement?

In an earlier test, a vague goal made a model write a flattering claim about a feature.

A goal that quoted the text typed the exact text in 5 of 5 runs. The goal was:
`Type exactly this text into the reply box: "lol same, my cat does the exact opposite"`.
Always put the text in quotation marks, and say "exactly".

### Name each field and control

Use the label that the page shows. Write "choose size large, and click Save" and not "finish the form".

### Keep one task small

Give one task for one goal. Run two tasks for two goals. Tasks can run at the same time. Each task uses its own tab.

## Example: a form

The test page `tests/site/index.html` has a name field, a size list, a Save button, and a Submit order button.

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory tests/site &

uv run clef-browse run --url http://127.0.0.1:8765/ --json \
  --goal "Type the name Grace Hopper into the name field, choose size large, and click Save. You are done when the page shows saved:Grace Hopper:large."
```

The task ends with `done` after 3 steps. The word "Submit" in the label of the second button makes it risky.
A goal that clicks it ends with `needs_approval` until you approve.
