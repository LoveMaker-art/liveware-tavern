# Security Policy

## Supported Versions

Security fixes are applied to the latest published release. Users should update through the verified release bootstrap before reporting an issue that may already be resolved.

## Reporting a Vulnerability

Do not open a public issue for vulnerabilities involving authentication, arbitrary file access, command execution, secret exposure, cross-user data access, or updater integrity.

Use GitHub's private vulnerability reporting for this repository. Include:

- the affected Tavern version;
- deployment mode: standalone, Hermes, or ClawChat;
- minimal reproduction steps;
- the expected and observed behavior;
- relevant logs with all keys, tokens, user IDs, URLs, and personal data removed.

Please allow time for the report to be reproduced and fixed before public disclosure.

## Secrets and User Data

- Never commit model keys, proxy credentials, SSH material, ClawChat databases, user profiles, story data, character cards, worldbooks, generated audio, or uploaded assets.
- Keep runtime state in `TAVERN_STATE_DIR`, outside the source checkout.
- Treat imported cards and worldbooks as untrusted content. Tavern does not execute embedded scripts from imported cards.
- Review reverse-proxy authentication and network exposure before making a standalone instance publicly reachable.

The project's data and trust boundaries are documented in [docs/architecture.md](docs/architecture.md) and [docs/configuration.md](docs/configuration.md).
