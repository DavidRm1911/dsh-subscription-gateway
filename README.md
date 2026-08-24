# dsh-subscription-gateway

If you already pay for Claude Pro/Max or have Antigravity access, [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) still wants a separate, metered API key before it'll let you use those models — its Custom Provider screen only speaks to real HTTP APIs, not to a CLI you're already logged into.

This is a tiny local server that closes that gap. It speaks the `openai-completions` protocol DSH expects, but instead of billing you per token it shells out to `claude -p` or `agy -p` — the same CLIs you already use, already logged in. Point DSH at it, and "claude-opus" or "gemini-flash-high" just show up as models you can pick, for free.

## Install

```bash
pip install dsh-subscription-gateway
dsh-subscription-gateway
```

You need at least one of these already set up:

- [Claude Code](https://claude.com/claude-code) CLI, logged in (`claude login`)
- `agy` (Antigravity), logged in
- [Ollama](https://ollama.com) with a model pulled — `qwen3.5:9b` by default

Missing one just means its models won't show up; the rest still work fine.

## Wiring it into DSH

Settings → Models → Add custom provider:

- **Base URL**: `http://localhost:8899/v1`
- **API protocol**: `openai-completions`
- **API key**: anything — it's not checked
- Click "Fetch available models," or add them by hand (list below)

## Models

- `claude`, `claude-haiku`, `claude-sonnet`, `claude-opus`, `claude-fable` — append `-low` / `-medium` / `-high` / `-xhigh` / `-max` for reasoning effort, e.g. `claude-opus-max`
- `gemini`, `gemini-flash-low/medium/high`, `gemini-flash36-low/medium/high`, `gemini-pro-low/high`
- `qwen-local` — whatever's running in Ollama, $0 either way

`GET /v1/models` always has the live list if this drifts.

## A couple of things worth knowing

It only binds to `127.0.0.1` — nothing external can reach it. Every request is a subprocess call or a local HTTP call to Ollama; no credentials get read off disk or sent anywhere by this code. The Claude provider always passes `--strict-mcp-config`, because without it the subprocess quietly inherits whatever MCP servers are configured in your regular Claude Code setup — that's a real bug I hit building this, not a theoretical one.

It's not a native DSH plugin — no `dsh.bundle`, doesn't touch `cordis`. It's just a process DSH talks to over HTTP, through the Custom Provider mechanism that already exists. And there's no real token-by-token streaming, because the underlying CLIs don't expose that in headless mode; you get the full response framed as one SSE chunk, which is enough for DSH's client to not choke on it.

## If you want the native version instead

[`dsh-llm-subscription`](https://github.com/DavidRm1911/dsh-llm-subscription) does the same thing as a real `dsh.bundle` plugin — Claude and Gemini show up natively in DSH's own model picker, with a working reasoning-effort selector, instead of living behind the Custom Provider screen. It's the better experience when it works, but it depends on DSH's internal `cordis` plugin API (developer preview, no stable contract). This gateway only talks to DSH's stable, documented Custom Provider mechanism, so it keeps working across DSH updates that might break the native one. Worth keeping both installed for that reason alone.

## License

MIT — see [LICENSE](LICENSE).
