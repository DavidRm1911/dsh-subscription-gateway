"""ClaudeCodeProvider: talks to Claude by shelling out to the `claude` CLI
in headless mode (`claude -p`), reusing your existing Claude Code login —
no API key, no credential file read or extracted.

`--strict-mcp-config` is required, not optional: without it, the subprocess
inherits MCP servers configured in your ambient ~/.claude.json, which can
leak unrelated tools/context into responses meant to be pure completions.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from dsh_gateway.base import ModelCapabilities, ModelMessage, ModelProvider, ModelResponse


class ClaudeCodeProvider(ModelProvider):
    name = "claude"
    capabilities = ModelCapabilities(streaming=False, tools=True, vision=True, reasoning=True)

    def __init__(
        self,
        *,
        model: str | None = None,
        effort: str | None = None,
        binary: str | None = None,
        timeout: int = 120,
    ) -> None:
        self._model = model
        self._effort = effort
        self._timeout = timeout
        self._binary = binary or shutil.which("claude")
        if self._binary is None:
            raise RuntimeError(
                "The `claude` CLI was not found on PATH. Install Claude Code "
                "and run `claude login` before using this provider."
            )

    def complete(self, messages: list[ModelMessage], *, system: str | None = None) -> ModelResponse:
        prompt = self._render_transcript(messages)
        cmd = [
            self._binary,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--tools",
            "",
            "--strict-mcp-config",
        ]
        if system:
            cmd += ["--system-prompt", system]
        if self._model:
            cmd += ["--model", self._model]
        if self._effort:
            cmd += ["--effort", self._effort]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"claude CLI exited {proc.returncode}: {proc.stderr.strip()}")

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"claude CLI returned non-JSON output: {proc.stdout[:500]!r}") from e

        if data.get("is_error"):
            raise RuntimeError(f"claude CLI reported an error: {data.get('result')}")

        model_label = self._model or "claude (cli default)"
        if self._effort:
            model_label += f" [{self._effort}]"

        usage = data.get("usage", {})
        return ModelResponse(
            text=data.get("result", ""),
            model=model_label,
            stop_reason=data.get("stop_reason"),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cost_usd=data.get("total_cost_usd"),
            raw=data,
        )

    @staticmethod
    def _render_transcript(messages: list[ModelMessage]) -> str:
        if len(messages) == 1:
            return messages[0].content
        lines = [f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}" for m in messages]
        return "\n\n".join(lines)
