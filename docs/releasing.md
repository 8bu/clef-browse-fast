# Releasing

This project uses [Conventional Commits](https://www.conventionalcommits.org/) and
[release-please](https://github.com/googleapis/release-please). The commit messages set the next version and write the
changelog.

## Commit messages

Write each commit message as `<type>: <subject>`. Write the subject in lowercase, in the imperative mood, without a period.

| Type | Use for | Effect on the version |
| --- | --- | --- |
| `feat` | A new capability | Minor |
| `fix` | A bug fix | Patch |
| `perf` | A speed improvement | Patch |
| `refactor` | A change with no new behavior | Patch |
| `docs` | A change to documents only | None |
| `test`, `chore`, `style`, `ci`, `build` | Maintenance | None, and hidden from the changelog |

To mark a breaking change, write `!` after the type, for example `feat!: remove the CLI flag`.
Add a line that starts with `BREAKING CHANGE:` in the message body. While the version is below 1.0.0, a breaking change
raises the minor number.

## The start version

The start version is `0.0.0`. The file `.release-please-manifest.json` stores the current version. No tag exists
until the first release.

## How a release works

1. A change lands on `main`. The workflow `release.yml` runs.
2. The workflow opens or updates one pull request with the title `chore(main): release X.Y.Z`.
3. The pull request changes the version in `pyproject.toml` and `uv.lock`. It also adds the new entries to
   `CHANGELOG.md`.
4. A maintainer reviews the pull request and merges it.
5. The merge creates the tag `vX.Y.Z` and a GitHub release with the changelog entries.
6. The workflow builds the wheel and the source archive. It attaches both files to the GitHub release.

The workflow never publishes by itself. Without a merge of the release pull request, no tag and no release exist.

The workflow does not publish to PyPI.

## Check a change before the merge

- The workflow `ci.yml` runs the linter, the tests, and the build on each push and each pull request.
- The workflow `pr-title.yml` checks that a pull request title follows the commit format. Use the squash merge, so that
  the title becomes the commit message.
- A pull request that the release workflow opens does not start `ci.yml`. This is a GitHub rule for pull requests that
  the built-in token creates. Run the checks on `main` before you merge the release pull request.

## Set up a new repository

- Open Settings, then Actions, then General. Enable "Allow GitHub Actions to create and approve pull requests".
- Keep the settings in `release-please-config.json` and `.release-please-manifest.json`.
- Do not edit `CHANGELOG.md` by hand. The next release overwrites the entries that it generates.
