"""OllamaProvider: talks to a local model over Ollama's HTTP API. Lazy by
design — never health-checks or starts the server at construction time,
only when a completion is actually requested.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request

from dsh_gateway.base import ModelCapabilities, ModelMessage, ModelProvider, ModelResponse

DEFAULT_MODEL = "qwen3.5:9b"
DEFAULT_HOST = "http://localhost:11434"


class OllamaProvider(ModelProvider):
    name = "qwen-local"
    capabilities = ModelCapabilities(streaming=False, tools=False, vision=False, reasoning=True)

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        host: str = DEFAULT_HOST,
        binary: str | None = None,
        timeout: int = 120,
    ) -> None:
        self._model = model
        self._host = host.rstrip("/")
        self._binary = binary or shutil.which("ollama")
        self._timeout = timeout

    def complete(self, messages: list[ModelMessage], *, system: str | None = None) -> ModelResponse:
        self._ensure_server()

        chat_messages = []
        if system:
            chat_messages.append({"role": "system", "content": system})
        chat_messages.extend({"role": m.role, "content": m.content} for m in messages)

        payload = json.dumps({"model": self._model, "messages": chat_messages, "stream": False}).encode()
        req = urllib.request.Request(
            f"{self._host}/api/chat", data=payload, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read())
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama request failed: {e}") from e

        if "error" in data:
            raise RuntimeError(f"Ollama reported an error: {data['error']}")

        message = data.get("message", {})
        return ModelResponse(
            text=message.get("content", ""),
            model=self._model,
            stop_reason=data.get("done_reason"),
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
            cost_usd=0.0,
            raw=data,
        )

    def _ensure_server(self) -> None:
        if self._is_up():
            return
        if self._binary is None:
            raise RuntimeError(
                "Ollama is not running and the `ollama` binary was not found on "
                "PATH to start it. Install Ollama or run `ollama serve` yourself."
            )
        subprocess.Popen(
            [self._binary, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
        )
        for _ in range(20):
            if self._is_up():
                return
            time.sleep(0.5)
        raise RuntimeError("Started `ollama serve` but it did not come up in time.")

    def _is_up(self) -> bool:
        try:
            urllib.request.urlopen(f"{self._host}/api/version", timeout=1)
            return True
        except urllib.error.URLError:
            return False
