# Safety

This document describes what the program protects, what it does not protect, and what you must decide.

## Read this first

The program acts in your Neo browser. Neo can hold your signed-in sessions. A task can act on those sessions.
A wrong decision by the model can change a real account.

- Use a goal that is narrow and clear.
- Read the result and check the page when the task changes data.
- Do not use the program for actions that you cannot undo, unless you check each step.

## What the program does to protect you

### Approval gate

The program stops before it does a risky action. The action is a click or an Enter key press.
It is risky when the label or the role of the element contains one of these terms:

`submit`, `purchase`, `delete`, `send`, `pay`, `confirm`, `publish`, `place order`, `remove`, `sign out`

The match is on whole words and ignores case. The word `payment` does not match `pay`.
The word `post` is risky only at the start of a label. The label `Post reply` is risky. The label `New post` is not,
because it only opens an editor.

When the gate stops a task:

- The status is `needs_approval`.
- The result names the label and the term in `risky`.
- The program did not do the action.

To approve, run the task again with `allow_risky_actions` set to true. Approval covers each risky action one time in a
task. A repeat of the same action stops the task again.

The list of terms is `RISKY_TERMS` in `src/clef_browse/neo.py`.

### Tab ownership

The program opens its own tab for each task. It closes only a tab that it opened and that Neo lists as owned by this
session. It checks the owner again before it closes the tab. It never touches your other tabs.

### No cookie export

The program does not read, copy, or send your cookies or your browser profile. It sends only the page data that is
listed in [Data that leaves your computer](#data-that-leaves-your-computer).

### Fixed set of actions

The engine builds a list of actions from the page. The model picks one item from the list. The program never runs
model output as JavaScript, as a selector, as a coordinate, or as a shell command.

### No repeat of a browser change

The program never retries a click, a key press, or a text entry. It retries only the requests to Clef and to the text
provider, because those requests change nothing.

### Limits

Each task has a limit for steps, time, and Clef requests. See [Configuration](configuration.md#limits).
A task that reaches a limit stops with the status `limit`.

### Secrets

The program reads secrets from the environment, from `.env` in the current folder, or from the settings file
`~/.config/clef-browse/.env`. It does not print them. Its own error messages do not contain them.
The `check` command shows only true or false values.

### What the guided setup changes

The command `clef-browse setup` can change three files. It asks before each change.

- The settings file `~/.config/clef-browse/.env`. The setup makes the folder private and the file readable only by you.
  The setup keeps every line that it does not set.
- The file `~/.omp/agent/mcp.json`. The setup first copies the file to `mcp.json.bak-<time>`. It changes only the
  entry `clef-browse`. It never overwrites a file that is not valid JSON.
- The skill file `~/.omp/agent/skills/clef-browse-fast/SKILL.md`.

The setup reads the token with a hidden prompt and never prints it. The last step opens a tab on `https://example.com`
in Neo and closes it. That step sends a real request to Cloudflare.

## Data that leaves your computer

| To | Data | When |
| --- | --- | --- |
| Cloudflare Workers AI | The page address and title, the visible page text, the labels and values of the offered elements, the goal, and the last 10 actions | Every step |
| The text provider | The goal, the label, role, and value of the field, the page title, the first 6,000 characters of the page text, and the last 6 actions | Only when a task types text |

The page text can contain private data. Form field values are included. Read the terms of Cloudflare and of your text
provider before you run a task on a private page.

## Known gaps

- **The gate checks labels.** A risky control with a neutral label, for example "Go", passes the gate.
- **The gate checks only clicks and Enter.** A form that the page submits in another way is not caught.
- **An Enter key press in a field.** The label of the field is checked, not the form. A field with a neutral label
  can submit a form without a stop.
- **Prompt injection.** The page text goes to the model as data. A hostile page can still change which offered element
  the model picks. It cannot make the program do an action that is not on the list.
- **A hard kill.** If you kill the process during a task, the tab stays open in Neo. Close it by hand.
- **Saved drafts.** Some sites keep unsent text. Substack saves the text of an unsent Note or reply in the browser
  storage and fills the box with it the next time. A task that types text and stops before the send button can
  leave that text behind. The text can come from a text model. Check the box before you send anything by hand.
- **The text provider.** The text model writes the text that the program types. A weak model can write a wrong value.
  The program accepts only a JSON object with a `text` value. If the answer is not valid, the program types nothing.

## Report a vulnerability

See [SECURITY.md](../SECURITY.md).
