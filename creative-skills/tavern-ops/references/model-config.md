# Tavern Model Configuration

Use this reference when the user wants to use their own model key, switch providers, test a model, or return to the default tavern model.

Commands:

```sh
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py model list
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py model add <name> --base <url> --model <id> --key <key>
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py model use <name>
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py model test [<name>]
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py model rm <name>
```

## Clawling API (default provider)

When the tavern is running with the Clawling provider (extracted from Hermes `config.yaml`), the model list differs from standard DeepSeek/OpenAI-compatible providers. Query the live API to get the current model list:

```sh
curl -s <base_url>/models -H "Authorization: Bearer <key>"
```

Known models (as of 2026-07-03):

- `deepseek-v4-pro`
- `deepseek-v4-flash`
- `glm-5.2`
- `step-3.7-flash`
- `kimi-k2.6`

If generation returns 403 Forbidden, check `/api/health` — if the model field is `deepseek-chat` (or any model not in the Clawling list), the model name mismatch is the cause. Fix by setting `TAVERN_MODEL` to a valid Clawling model, or changing the default in `actor.py`.

## Provider examples

- DeepSeek: `https://api.deepseek.com/v1`, `deepseek-chat` or `deepseek-reasoner`
- Kimi: `https://api.moonshot.cn/v1`
- Qwen Bailian: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- OpenRouter: `https://openrouter.ai/api/v1`
- OpenAI: `https://api.openai.com/v1`
- Gemini OpenAI-compatible layer: `https://generativelanguage.googleapis.com/v1beta/openai`
- Ollama: `http://127.0.0.1:11434/v1`

Safety rules:

- Never repeat the full key back to the user. Report provider/name and at most the last 4 characters.
- Current CLI accepts `--key`; be aware this can expose the key in shell history/process listings. Prefer improving the CLI to accept stdin or a private prompt before asking users for production keys.
- Model configurations are stored under `/opt/data/tavern-state` and should remain server-side only.
- Default/builtin model should not be deleted. Use `model use 内置模型` to return to it.
