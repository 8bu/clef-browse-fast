# Troubleshooting

This document lists the problems that you can meet, the message for each problem, and the fix.

Start with the setup check:

```bash
uv run clef-browse check
```

## The setup check shows `false`

| Value | Likely cause | Fix |
| --- | --- | --- |
| `neo_mcp` | Neo is not running, or the MCP address is wrong. | Start Neo. Set `BROWSEROS_NEO_MCP_URL` if the address is not `http://127.0.0.1:9010/mcp`. |
| `neo_cdp` | Neo is not running, or the CDP address is wrong. The address must belong to a Chrome browser. | Start Neo. Set `BROWSEROS_NEO_CDP_URL` if the address is not `http://127.0.0.1:9111`. |
| `clef_env` | The account ID or the token is not set. | Set `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_AUTH_TOKEN` in `.env`. Run the command from the folder that holds `.env`. |

## The task ends with a status that is not `done`

### `blocked`

Clef decided that no offered action can make progress. Three causes are common:

- The goal has no finish condition that the page shows. Add one. See [Usage](usage.md#write-goals-that-finish).
- The goal asks for something that the page does not offer. Check that the page has the control that you name.
- The page was still loading, and the control you need was disabled or missing. Raise `CLEF_BROWSE_SETTLE_MS`.
  See [Configuration](configuration.md#page-settle-wait).

If the error text is `No suitable target was offered`, Clef had only one candidate and chose "none". Rewrite the
goal so that it names the control more clearly.

### `needs_approval`

The next action is risky. The program did not do it. See [Usage](usage.md#approve-a-risky-action).

### `limit`

The task reached a limit. The `error` field names the limit:

| Message | Setting |
| --- | --- |
| `Maximum steps reached` | `CLEF_BROWSE_MAX_STEPS` or `--max-steps` |
| `Run timed out` | `CLEF_BROWSE_TIMEOUT_S` or `--timeout-s` |
| `Maximum model calls reached` | `CLEF_BROWSE_MAX_MODEL_CALLS` |

Split a large goal into smaller tasks before you raise a limit.

## The task ends with `error`

The `error` field holds the message. This table lists the messages by group.

### Settings

| Message | Fix |
| --- | --- |
| `CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_AUTH_TOKEN are required` | Set both values. The task fails before it opens a tab. |
| `Unsupported CLEF_MODEL ... only 'clef' is supported` | Set `CLEF_MODEL=clef` or remove the line. |
| `CLEF_ESCALATION_MODEL is no longer supported ...` | Remove the value of `CLEF_ESCALATION_MODEL`. |

### Clef

| Message | Meaning and fix |
| --- | --- |
| `Clef returned HTTP 4xx` | Cloudflare refused the request. The likely cause is a wrong account ID, a wrong token, or a missing permission. Check the token has Workers AI Read and Edit. |
| `Clef unavailable (HTTP 5xx)` or `HTTP 429` | The program tried 3 times. Wait, then run the task again. |
| `Clef connection failed` | The program could not reach Cloudflare after 3 tries. Check your network. |
| `Clef returned invalid JSON` or `Invalid Clef choice response` | The answer did not have the expected form. Run the task again. If it repeats, open an issue. |

### Text provider

| Message | Fix |
| --- | --- |
| `TYPE_TEXT needs TEXT_MODEL_API_KEY ...` | Set `TEXT_MODEL_API_KEY`. See [Configuration](configuration.md#text-provider). |
| `Text helper returned no valid field value; nothing typed.` | The text model returned no `text` value. Put the value in the goal. If the error stays, use a stronger model. |
| `Model unavailable` | The text provider failed 3 times. Check the address, the key, and the model name. |
| HTTP 410 from the provider | Cloudflare removed the model. Choose another model. |

### Neo and CDP

| Message | Fix |
| --- | --- |
| `CDP endpoint is unreachable: ...` | Start Neo. Check `BROWSEROS_NEO_CDP_URL`. |
| `CDP endpoint did not identify as Chrome` | The address does not belong to Neo. Check `BROWSEROS_NEO_CDP_URL`. |
| `CDP websocket connection failed: ...` | Neo refused the websocket. Restart Neo and run the task again. |
| `CDP connection lost during ...` or `... timed out` | Neo closed the connection or did not answer. Run the task again. |
| `Neo MCP request failed: ...` | Start Neo. Check `BROWSEROS_NEO_MCP_URL`. |
| `Neo did not return a target id` | Neo opened the tab but gave no ID. The program closes that tab. Run the task again. |
| `Neo page N is not owned by this session` | The program refuses to use a tab that it did not open. This is a safety stop, not a fault. |
| `Dropdown execution was not confirmed; inspect before retrying.` | The program does not retry a change. Check the page by hand, then run the task again. |

## A tab stays open in Neo

If you kill the process during a task, the tab stays open. Close it by hand in Neo. The program never closes a tab that it
did not open.

## The same task gives a different result each time

Clef gives the same answer for the same request. The page can differ between runs, for example because of time,
an advertisement, or a saved value. A different page gives a different request. Make the goal and the finish
condition precise.

## Get help

Open an issue and include:

- The command and the goal, with private data removed.
- The `status`, `error`, `steps`, and `timing_ms` fields of the result.
- The versions of Python, Neo, and this program.

Do not post your token, your account ID, or private page text.
