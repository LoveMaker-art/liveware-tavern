# Model Configuration

Always inspect the live model registry. Do not rely on a static list in a Skill.

```sh
CLI=/opt/data/skills/creative/tavern/scripts/tavern_cli.py
python3 "$CLI" model list --json
python3 "$CLI" model test [name] --json
python3 "$CLI" model add <name> --base <url> --model <id> --key <key> --json
python3 "$CLI" model use <name> --json
python3 "$CLI" model rm <name> --json
```

`model add` must test the candidate before saving and selecting it. Report only
the provider/configuration name, model ID, latency, and masked key. Never echo a
full key or put it in documentation.

Frontend selection does not create server credentials. If generation fails,
compare selected configuration, model ID, base URL, key availability, and the
upstream error before changing anything. The built-in configuration must remain
available as the fallback choice.
