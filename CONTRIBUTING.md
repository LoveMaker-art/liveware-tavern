# Contributing to Nora's Tavern

Thank you for helping improve Nora's Tavern. This project treats the web application, Hermes integration, updater, and user state as separate ownership boundaries. Changes should preserve those boundaries.

## Before You Start

1. Search existing issues and releases for related work.
2. Open an issue before a large feature, state migration, or API contract change.
3. Never commit user worlds, character cards, conversations, credentials, ClawChat data, generated audio, update backups, or local state.

## Local Development

```bash
git clone https://github.com/LoveMaker-art/noras-tavern.git
cd noras-tavern
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Use an isolated state directory:

```bash
export TAVERN_STATE_DIR="$PWD/.local-state"
export TAVERN_MODEL_BASE="https://your-provider.example/v1"
export TAVERN_MODEL_KEY="replace-with-your-key"
export TAVERN_MODEL="your-model-id"
python3 app/backend/server.py --port 8799
```

## Tests

Run the relevant focused tests while developing, then run the full checks before opening a pull request:

```bash
PYTHONPATH=app/backend python3 -m unittest discover -s tests -v
node --test tests/frontend_security.test.js
python3 scripts/build_release.py
```

## Pull Requests

- Keep each pull request focused on one coherent change.
- Explain user-visible behavior, data migration, compatibility, and rollback impact.
- Add or update tests for changed runtime behavior.
- Include desktop and mobile screenshots for user-interface changes.
- Update both `README.md` and `README.zh-CN.md` when public behavior or installation changes.
- Do not manually edit generated release artifacts unless the release process requires it.

## Compatibility Boundaries

- `app/` contains the canonical application source.
- `skills/` contains the Hermes Custom Tap and shared operational CLI.
- `integrations/hermes/` contains optional instance templates.
- User state belongs under `TAVERN_STATE_DIR` and must remain outside managed release files.
- Updater manifests must be changed together with the files they manage.

By contributing, you agree that your work is distributed under the repository's [AGPL-3.0-only license](LICENSE).
