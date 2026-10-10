# Configuration

This document lists every setting, its default, and the cost of a task.

## How settings load

1. A variable that is already in the environment keeps its value. No file overrides it.
2. The program reads the file `.env` in the current working directory.
3. The program reads the settings file of the user. The path is `~/.config/clef-browse/.env`.
   The guided setup writes this file. Set `XDG_CONFIG_HOME` or `CLEF_BROWSE_CONFIG` to use another path.

Never commit `.env`. It holds secrets. The file `.gitignore` lists it.

## Manual setup

Use this method if you do not want the guided setup.

1. Create the settings file. Make the folder and the file private.

   ```bash
   mkdir -p -m 700 ~/.config/clef-browse
   install -m 600 /dev/null ~/.config/clef-browse/.env
   ```

2. Open the file in an editor. Add these two lines with your values. The next section lists more settings.

   ```text
   CLOUDFLARE_ACCOUNT_ID=<your account ID>
   CLOUDFLARE_AUTH_TOKEN=<your token>
   ```

3. Run `clef-browse check`. All three values must be `true`.
4. Add the MCP server to your client. See [Usage](usage.md#register-the-server-in-omp).

From a clone, you can also copy `.env.example` to `.env` in the folder of the clone.

## Settings

### Cloudflare (required)

| Variable | Default | Meaning |
| --- | --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | none | The ID of your Cloudflare account. |
| `CLOUDFLARE_AUTH_TOKEN` | none | An API token with the Workers AI Read and Edit permissions. |

If one of these is missing, the task ends with `error` before it opens a tab.

### Decision model

| Variable | Default | Meaning |
| --- | --- | --- |
| `CLEF_MODEL` | `clef` | The decision model. The only accepted value is `clef`. |

Any other value makes the task end with `error` and the message `Unsupported CLEF_MODEL`. The task fails before it
opens a tab. The model `clef-flash` is not supported. See
[Measured results](benchmarks.md#why-clef-flash-is-not-supported) for the reason.

The old variable `CLEF_ESCALATION_MODEL` is no longer supported. If you set it to a non-empty value, the task ends
with `error` before it opens a tab. An empty value is accepted.

### Text provider

Clef picks which field to type into. A separate text model writes the text. The program calls this model only when a
task types text.

| Variable | Default | Meaning |
| --- | --- | --- |
| `TEXT_MODEL_API_KEY` | none | The key for the text provider. Required when a task types text. |
| `TEXT_MODEL_BASE_URL` | `https://api.deepseek.com/v1` | The base URL of an OpenAI-compatible API. |
| `TEXT_MODEL` | `deepseek-chat` | The model name. |
| `TEXT_MODEL_REASONING` | unset | Set to `none` to send `reasoning: {enabled: false}` in the request. |

The authors tested only the Cloudflare option below. They did not test the default values.

To use the Cloudflare OpenAI-compatible endpoint with the same token, set:

```
TEXT_MODEL_API_KEY=<your Cloudflare token>
TEXT_MODEL_BASE_URL=https://api.cloudflare.com/client/v4/accounts/<account ID>/ai/v1
TEXT_MODEL=@cf/meta/llama-3.3-70b-instruct-fp8-fast
```

Model availability changes. The model `@cf/meta/llama-3.1-8b-instruct` returned HTTP 410 when the authors tried it.
Cloudflare lists its deprecation date as 2026-05-30. If you get HTTP 410, choose a different model.

### Neo

| Variable | Default | Meaning |
| --- | --- | --- |
| `BROWSEROS_NEO_MCP_URL` | `http://127.0.0.1:9010/mcp` | The Neo MCP endpoint. |
| `BROWSEROS_NEO_CDP_URL` | `http://127.0.0.1:9111` | The Neo Chrome DevTools Protocol (CDP) endpoint. |

The program connects only to these two addresses. It never starts a browser.

### Limits

| Variable | Default | Meaning |
| --- | --- | --- |
| `CLEF_BROWSE_MAX_STEPS` | `60` | The maximum number of steps in one task. |
| `CLEF_BROWSE_TIMEOUT_S` | `180` | The maximum run time of one task, in seconds. |
| `CLEF_BROWSE_MAX_MODEL_CALLS` | `120` | The maximum number of Clef requests in one task. |
| `CLEF_BROWSE_SETTLE_MS` | `500` | After the page loads, wait until the page has not changed for this time, in milliseconds. `0` turns the wait off. |

A task that reaches a limit ends with the status `limit`. The command line and the MCP tool can lower or raise the
step and time limits for one task. See [Usage](usage.md).

### Page settle wait

Many pages keep changing after the load event. A control can be disabled or in a different place for a short time.
The engine skips disabled controls. So the program waits until the page has not changed for `CLEF_BROWSE_SETTLE_MS`
before the first observation. The wait stops after 3 seconds at the latest.

The wait adds at least that time to each task. Lower the value for static pages. Raise it for slow apps.
The wait cannot see a page that is silent for longer than the value and then changes.

### Fixed values

These values are in the code. They have no setting.

| Value | Setting in code |
| --- | --- |
| Clef request timeout | 20 seconds |
| Clef retries | 3 attempts. Retry on HTTP 429, 500, 502, 503, 504, 529, and on connection errors. Wait 0.5 s, then 1 s. |
| Maximum observation size | 48,000 characters. The program removes elements from the end of a large page. |

## Cost

Clef charges for input tokens only. Output tokens are free. Cloudflare lists the price of `clef` as
$0.24 for each 1 million input tokens. The price is on the
[Cloudflare pricing page](https://developers.cloudflare.com/workers-ai/platform/pricing/). Check that page for the
current price.

The field `cost_usd` in the result is the input tokens of the task multiplied by this price. It does not include the
text provider.

Example tasks in [Measured results](benchmarks.md) used 3,619 to 8,242 input tokens. At the `clef` price, that costs
$0.0009 to $0.0020 for each task.

Cloudflare gives each account a free allowance of 10,000 neurons each day. The price of `clef` is 21,818 neurons for
each 1 million input tokens. So the free allowance covers about 458,000 input tokens each day. The pricing page is
the source for both numbers.

## Token permissions

Create the token in the Cloudflare dashboard. Give it the Workers AI Read and Edit permissions for one account.
Set an expiry date. Revoke the token if it leaks.
