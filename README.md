# clef-browse-fast

clef-browse-fast runs a browser task that you write in plain English. It uses your running
BrowserOS Neo browser. It does not start a browser of its own.

Two parts do the work:

- The engine is [`browser-use/jev-ultrafast`](https://github.com/browser-use/jev-ultrafast). It reads the page and does the actions.
- The decision model is [Cloudflare Clef](https://developers.cloudflare.com/workers-ai/models/clef/). It picks the next action.

You can start a task from the command line. You can also start it from an MCP client, for example OMP.

**Status:** pre-release. The authors tested it on macOS (arm64), Python 3.14, and Neo 0.0.68. They did not test other systems.

## What it does

- Opens one new tab in Neo for each task.
- Reads the page as text. It sends no screenshots.
- Asks Clef for the next action, one request for each step.
- Does the action in the tab and repeats until the goal is complete.
- Closes the tab when the task ends.

## What it does not do

- It does not start Chrome, a headless browser, or a temporary profile.
- It does not read, copy, or export cookies.
- It does not touch a tab that it did not open.
- It does not run text from the model as JavaScript, as a selector, or as a shell command.
- It does not click a risky control without your approval. See [Safety](docs/safety.md).

## Requirements

- Python 3.12 or later.
- [`uv`](https://docs.astral.sh/uv/).
- BrowserOS Neo, running on the same computer.
- A Cloudflare account and an API token with the Workers AI Read and Edit permissions.
- A text provider, only if your tasks type text into fields. See [Configuration](docs/configuration.md).

## Quick start

1. Install the dependencies.

   ```bash
   uv sync
   ```

2. Create the settings file and fill in the values.

   ```bash
   cp .env.example .env
   ```

   Never commit `.env`. It holds your API token. The `.gitignore` file already lists it.

3. Check the setup. The command prints three true or false values and no secrets.

   ```bash
   uv run clef-browse check
   ```

   All three values must be `true`: `neo_mcp`, `neo_cdp`, and `clef_env`.

4. Run a task.

   ```bash
   uv run clef-browse run --url https://example.com \
     --goal "Click the 'Learn more' link. You are done when the page heading says 'Example Domains'." --json
   ```

The command prints a JSON result. The `status` field is `done` when the task is complete.

### Install without a clone

```bash
uv tool install git+https://github.com/8bu/clef-browse-fast
```

This installs the commands `clef-browse` and `clef-browse-mcp`. Run `clef-browse check` in a folder that holds your `.env` file.
The commands read `.env` from the current folder. You can also set the same variables in your shell.
After the first release, add `@vX.Y.Z` to the URL to install one version. The repository does not publish to PyPI.

## Write goals that finish

Clef decides that a task is complete only when the page shows proof. Follow these two rules:

- **Give a finish condition that the page shows.** Write "You are done when the page heading says 'Example Domains'."
- **Quote the exact text to type.** Write `Type exactly this text: "lol same"`. A vague goal makes the text model write its own text.

See [Usage](docs/usage.md) for the reasons and for more examples.

The MCP server sends these rules to the calling agent in the tool description. The folder `skills/clef-browse-fast` has the same rules as an agent skill.

## Documentation

| Document | Content |
| --- | --- |
| [Usage](docs/usage.md) | The command line, the MCP tool, the result fields, and goal writing. |
| [Configuration](docs/configuration.md) | All settings, defaults, and the cost of a task. |
| [Architecture](docs/architecture.md) | The parts, the data flow, and the reasons for each design choice. |
| [Safety](docs/safety.md) | The approval gate, what leaves your computer, and the known gaps. |
| [Measured results](docs/benchmarks.md) | Timings, costs, and the test method. |
| [Troubleshooting](docs/troubleshooting.md) | Each error message and its fix. |
| [Contributing](CONTRIBUTING.md) | How to set up, test, and send a change. |
| [Security policy](SECURITY.md) | How to report a vulnerability. |
| [Changelog](CHANGELOG.md) | The changes in each version. |
| [Releasing](docs/releasing.md) | The commit format and the release steps. |

## Known limits

- Neo replay: nobody has checked whether the Neo replay shows the actions. Neo opens the tab, but the actions go through CDP.
- The tool was not called from inside an OMP session. The same server was tested over stdio.
- The approval gate checks labels. A risky control with a neutral label passes the gate.
- Some sites keep unsent text. A task that stops before the send button can leave a draft in the box.
- A task that ends with a hard kill can leave its tab open in Neo.

The full list is in [Safety](docs/safety.md) and [Measured results](docs/benchmarks.md).

## Development

```bash
uv run ruff check .
uv run pytest
uv build
```

The tests never call a paid API. See [Contributing](CONTRIBUTING.md).

## License and credits

The project license is MIT. See [LICENSE](LICENSE).

The folder `src/jev_ultrafast/` is a modified copy of `browser-use/jev-ultrafast`. It is also under the MIT license.
The upstream license is in `src/jev_ultrafast/LICENSE.upstream`. The local changes are in `src/jev_ultrafast/PATCHES.md`.
The upstream commit is `1231850a0bf1a0c0341fe408ef1668dbbfdfac46`.
