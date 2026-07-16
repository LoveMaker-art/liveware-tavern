---
name: tavern-ops
description: Operate Tavern Liveware：模型、启动、健康检查与本地化。
version: 1.19.8
author: ClawChat Tavern
license: AGPL-3.0-only
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tavern, liveware, model, health, i18n, operations]
    category: creative
---

# Tavern Operations

## When to Use

Use this skill for model configuration, health checks, local app restart, provisioning, Liveware naming or localization checks, and operational diagnosis that does not require a code update.

Use tavern-updater for frontend/backend version changes, merge review, rollback, or release installation.

## Procedure

1. Inspect current health and configuration before changing anything.
2. For model changes, test the candidate before saving or selecting it.
3. Never display full credentials.
4. Restart through the maintained bringup script.
5. Verify local health, public health when available, process state, and the requested behavior.

Commands:

    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py model list
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py model test [name]
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py model add <name> --base <url> --model <id> --key <key>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py model use <name>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py model rm <name>
    sh /opt/data/skills/creative/tavern/scripts/bringup.sh
    curl -fsS http://127.0.0.1:8799/api/health

Load only the needed reference:

- references/model-config.md
- references/liveware-ops.md
- references/i18n.md

Before a state-changing operation, load the Tavern shared contract.

## Pitfalls

- Do not confuse frontend model selection with availability of a server-side key.
- Do not hardcode a user name or app title when runtime metadata should supply it.
- Do not restart the entire Hermes gateway for a Tavern-only failure unless evidence points to the gateway.
- Do not use this skill to overwrite frontend/backend code.

## Verification

Health must report ok, the selected model must pass a minimal generation test, and any localization or app metadata change must be checked in both supported interface languages.
