# Security policy

## Supported versions

Only the latest release gets security fixes.

## Report a vulnerability

Do not open a public issue for a security problem.

1. Use the private vulnerability reporting feature of the service that hosts this repository.
2. If that feature is off, contact the maintainers by the method in the repository profile.
3. Describe the problem, the steps to repeat it, and the effect.
4. Remove your tokens and private data from the report.

The maintainers will confirm that they received your report and will tell you what they plan to do.

## What counts as a vulnerability

Examples:

- The program runs model output or page content as code, as a selector, or as a shell command.
- The program does a risky action without approval when the label matches the list of risky terms.
- The program closes, reads, or changes a tab that it did not open.
- The program reads, copies, or sends cookies or the browser profile.
- The program writes a secret to a log, to a result, or to an error message.

## Known limits that are not vulnerabilities

The [Safety](docs/safety.md#known-gaps) document lists known gaps. A risky control with a neutral label
that passes the gate is one of them. You are welcome to propose an improvement as a normal issue.

## If your token leaks

1. Revoke the token in the Cloudflare dashboard.
2. Create a new token with the Workers AI Read and Edit permissions.
3. Update `.env`.
