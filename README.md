# dsh-subscription-gateway

Use your existing **Claude Code**, **Antigravity** (Gemini), or local **Ollama** login inside [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) — no API key, no per-token billing.

## Why

DSH's built-in "Custom provider" screen expects an HTTP endpoint speaking the `openai-completions` protocol, plus a real API key. If you already pay for Claude Pro/Max or have Antigravity access, you don't have — and shouldn't need — a separate metered API key just to use those models inside DSH.

This is a small local HTTP server that speaks that protocol for real, but serves requests by shelling out to the CLIs you're already logged into (`claude`, `agy`) or to a local Ollama model. Nothing you type goes anywhere except where those CLIs would normally send it.

## Install & run

```bash
pip install dsh-subscription-gateway   # or: uv tool install dsh-subscription-gateway
dsh-subscription-gateway
```

Requires at least one of:
- [`claude`](https://claude.com/claude-code) CLI, logged in (`claude login`)
- `agy` (Antigravity) CLI, logged in
- [Ollama](https://ollama.com), with a model pulled (default: `qwen3.5:9b`)

Any of these being missing just means its model ids won't resolve — the other two still work.

## Connect it to DSH

In DSH: **Settings → Models → Add custom provider**

| Field | Value |
|---|---|
| Base URL | `http://localhost:8899/v1` |
| API protocol | `openai-completions` |
| API key | any non-empty text — not checked |
| Models | click "Fetch available models", or add manually (see below) |

## Available model ids

- `claude`, `claude-haiku`, `claude-sonnet`, `claude-opus`, `claude-fable` — each combinable with a reasoning-effort suffix: `-low`, `-medium`, `-high`, `-xhigh`, `-max` (e.g. `claude-opus-max`)
- `gemini`, `gemini-flash-low/medium/high`, `gemini-flash36-low/medium/high`, `gemini-pro-low/high`
- `qwen-local` (local Ollama, `$0` per call)

`GET /v1/models` lists the full set at runtime.

## Security notes

- Runs on `127.0.0.1` only — not exposed to your network by default.
- Each request shells out to a CLI subprocess (`claude -p` / `agy -p`) or calls Ollama's local HTTP API. No credentials are read from disk or transmitted anywhere by this gateway itself.
- The Claude provider passes `--strict-mcp-config`, so it never inherits MCP servers or tools from your ambient Claude Code configuration — each request is a clean completion.

## What this is not

Not a DSH plugin in the native `dsh.bundle`/`cordis` sense — it's a standalone process DSH talks to over HTTP through its existing Custom Provider mechanism. No streaming token-by-token (the underlying CLIs don't expose that in headless mode); responses arrive as a single chunk framed as SSE for client compatibility.

## License

MIT — see [LICENSE](LICENSE).
