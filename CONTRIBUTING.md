# Contributing

Thank you for your interest. This document explains how to set up the project and send a change.

## Set up

You need Python 3.12 or later and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env
```

You need real credentials in `.env` only to run a task against Neo. The tests do not need them.

## Check your change

Run these three commands before you send a change. All three must pass.

```bash
uv run ruff check .
uv run pytest
uv build
```

The line length is 120 characters. Ruff checks the rules `E`, `F`, and `I`.

## Tests

- A test never calls a paid API. Mock Clef and the text provider.
- The unit tests use a fake Neo MCP server in `tests/fake_neo.py`. Its output must match the real Neo format.
- The integration tests start a headless Chrome and a local page from `tests/site/`. A test skips itself if Chrome is not
  installed. The program code itself never starts a browser.
- Test behavior that a user can see. Do not test internal wiring or the wording of messages.
- If you fix a bug, add a test that fails without the fix.

## Rules for the code

- **Never retry a browser change.** A click, a key press, or a text entry must run at most one time.
  You may retry a request to Clef or to the text provider.
- **Model output is data.** Never run it as JavaScript, as a selector, as a coordinate, or as a shell command.
  The engine accepts only an index or an operation from the list that it offered.
- **Attach to Neo only.** Do not start a browser, a temporary profile, or a second Chrome. Do not export cookies.
- **Own your tabs.** Open a tab through the Neo MCP. Close only a tab that this session owns.
- **Keep secrets out.** Do not log a token or an account ID. Do not put one in an error message.
- **Keep a clear error.** Return an error that tells the user what to do. Do not hide a failure with a silent fallback.
- **Show your numbers.** Do not claim that something is faster or better without a measurement. Add the method and the
  result to [docs/benchmarks.md](docs/benchmarks.md).

## Change the engine

The folder `src/jev_ultrafast/` is a copy of an upstream project. Keep your change to this folder small.
Put new code in `src/clef_browse/`. Record each change to the engine in `src/jev_ultrafast/PATCHES.md`.

## Write documents

The documents use ASD-STE100 Simplified Technical English. Follow these rules:

- Write short sentences. Use at most 20 words in an instruction and 25 words in a description.
- Put one idea in each sentence and one topic in each paragraph.
- Use the active voice and the present tense.
- Use one word for one meaning.
- Use a list for steps and for sets of items.

Code, file paths, and quoted error messages stay as they are.

## Send a change

1. Make a branch.
2. Make your change in small steps. Add or update the tests.
3. Update the documents that the change affects. Add a line to [CHANGELOG.md](CHANGELOG.md).
4. Run the three checks.
5. Open a pull request. Say what changed, why, and how you tested it.

Never commit `.env` or a token. If you commit a secret by mistake, revoke it at once.

## Report a security problem

Do not open a public issue. Read [SECURITY.md](SECURITY.md).
