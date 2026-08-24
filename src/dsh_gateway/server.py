"""OpenAI-compatible HTTP gateway in front of subscription-backed model
providers (Claude Code CLI, Antigravity CLI, local Ollama) — built for
DeepSeek Harness's "Custom provider" settings screen, which expects an
openai-completions endpoint plus a real API key. These providers don't have
one; they shell out to CLIs that already reuse an existing login. This
server is the bridge: point DSH's Custom provider Base URL here, protocol
openai-completions, any text as the API key.

Not a general-purpose OpenAI server — just enough of the protocol
(POST /v1/chat/completions with streaming, GET /v1/models) for DSH's
custom-provider client.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dsh_gateway.base import ModelMessage, ModelProvider
from dsh_gateway.providers.antigravity import AntigravityProvider
from dsh_gateway.providers.claude_code import ClaudeCodeProvider
from dsh_gateway.providers.ollama import OllamaProvider

DEFAULT_PORT = 8899

_FINISH_REASON_MAP = {
    "end_turn": "stop",
    "stop": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "length": "length",
}


def _normalize_finish_reason(reason: str | None) -> str:
    return _FINISH_REASON_MAP.get(reason or "stop", "stop")


# Claude: --model + --effort are independent CLI flags. Any "claude*" id can
# carry an -<effort> suffix, parsed generically against this fixed set.
_CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")
_CLAUDE_BASE_MODELS = {
    "claude": None,
    "claude-haiku": "haiku",
    "claude-sonnet": "sonnet",
    "claude-opus": "opus",
    "claude-fable": "fable",
}

# Gemini: agy bakes the effort tier into the model *name* itself.
_GEMINI_MODELS = {
    "gemini": "Gemini 3.5 Flash (Medium)",
    "gemini-flash-low": "Gemini 3.5 Flash (Low)",
    "gemini-flash-medium": "Gemini 3.5 Flash (Medium)",
    "gemini-flash-high": "Gemini 3.5 Flash (High)",
    "gemini-flash36-low": "Gemini 3.6 Flash (Low)",
    "gemini-flash36-medium": "Gemini 3.6 Flash (Medium)",
    "gemini-flash36-high": "Gemini 3.6 Flash (High)",
    "gemini-pro-low": "Gemini 3.1 Pro (Low)",
    "gemini-pro-high": "Gemini 3.1 Pro (High)",
}


def build_providers() -> dict[str, ModelProvider]:
    """Best-effort: a missing CLI/runtime just means that provider's ids
    won't resolve later, not a crash at startup."""
    providers: dict[str, ModelProvider] = {}
    try:
        providers["claude"] = ClaudeCodeProvider()
    except RuntimeError as e:
        print(f"[warn] claude provider unavailable: {e}", file=sys.stderr)
    try:
        providers["gemini"] = AntigravityProvider()
    except RuntimeError as e:
        print(f"[warn] gemini provider unavailable: {e}", file=sys.stderr)
    providers["qwen-local"] = OllamaProvider()  # never touches the network at construction time
    return providers


def _resolve_claude(model_id: str) -> ModelProvider | None:
    effort = None
    base = model_id
    for e in _CLAUDE_EFFORTS:
        if model_id.endswith(f"-{e}"):
            effort, base = e, model_id[: -(len(e) + 1)]
            break
    if base not in _CLAUDE_BASE_MODELS:
        return None
    return ClaudeCodeProvider(model=_CLAUDE_BASE_MODELS[base], effort=effort)


def resolve_provider(providers: dict[str, ModelProvider], model_id: str) -> ModelProvider:
    if model_id in _GEMINI_MODELS:
        return AntigravityProvider(model=_GEMINI_MODELS[model_id])
    claude_provider = _resolve_claude(model_id)
    if claude_provider is not None:
        return claude_provider
    if model_id not in providers:
        raise KeyError(f"Unknown model '{model_id}'. Available: {', '.join(all_model_ids(providers))}")
    return providers[model_id]


def all_model_ids(providers: dict[str, ModelProvider]) -> list[str]:
    ids = set(providers) | set(_CLAUDE_BASE_MODELS) | set(_GEMINI_MODELS)
    ids |= {f"{base}-{e}" for base in _CLAUDE_BASE_MODELS for e in _CLAUDE_EFFORTS}
    return sorted(ids)


def _make_handler(providers: dict[str, ModelProvider]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            print(f"[gateway] {self.address_string()} - {fmt % args}")

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_sse_completion(self, completion_id: str, model: str, response) -> None:
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            created = int(time.time())

            def chunk(delta: dict, finish_reason: str | None) -> dict:
                return {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
                }

            events = [
                chunk({"role": "assistant", "content": response.text}, None),
                chunk({}, _normalize_finish_reason(response.stop_reason)),
            ]
            for event in events:
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Access-Control-Allow-Methods", "*")
            self.end_headers()

        def do_GET(self) -> None:
            if self.path.rstrip("/") == "/v1/models":
                data = [{"id": name, "object": "model", "owned_by": "dsh-gateway"} for name in all_model_ids(providers)]
                self._send_json(200, {"object": "list", "data": data})
                return
            self._send_json(404, {"error": {"message": "not found"}})

        def do_POST(self) -> None:
            if self.path.rstrip("/") != "/v1/chat/completions":
                self._send_json(404, {"error": {"message": "not found"}})
                return

            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                self._send_json(400, {"error": {"message": "invalid JSON body"}})
                return

            model_name = body.get("model")
            raw_messages = body.get("messages", [])
            system = next((m["content"] for m in raw_messages if m.get("role") == "system"), None)
            messages = [
                ModelMessage(role=m["role"], content=m["content"]) for m in raw_messages if m.get("role") != "system"
            ]

            try:
                provider = resolve_provider(providers, model_name)
                response = provider.complete(messages, system=system)
            except (KeyError, RuntimeError) as e:
                self._send_json(502, {"error": {"message": str(e)}})
                return

            completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

            if body.get("stream"):
                self._send_sse_completion(completion_id, response.model, response)
                return

            self._send_json(
                200,
                {
                    "id": completion_id,
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": response.model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": response.text},
                            "finish_reason": _normalize_finish_reason(response.stop_reason),
                        }
                    ],
                    "usage": {
                        "prompt_tokens": response.input_tokens or 0,
                        "completion_tokens": response.output_tokens or 0,
                        "total_tokens": (response.input_tokens or 0) + (response.output_tokens or 0),
                    },
                },
            )

    return Handler


def main() -> None:
    providers = build_providers()
    server = ThreadingHTTPServer(("127.0.0.1", DEFAULT_PORT), _make_handler(providers))
    print(f"dsh-subscription-gateway: http://127.0.0.1:{DEFAULT_PORT}/v1")
    print(f"models: {', '.join(all_model_ids(providers))}")
    print("Point DSH's Custom provider Base URL here, API protocol openai-completions, any API key text.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
