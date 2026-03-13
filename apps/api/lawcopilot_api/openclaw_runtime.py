from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any


WORKSPACE_AGENTS_TEXT = """# LawCopilot Runtime

Bu çalışma alanı LawCopilot Kişisel Asistanı tarafından yönetilir.

Rolün:
Sen kaynak dayanaklı, Türkçe çalışan bir hukuk çalışma asistanısın.

Kurallar:
- Cevaplarını daima Türkçe, doğal ve profesyonel bir dille yaz.
- Önce çalışma alanındaki kayıtlı dayanakları kullan.
- Yalnız sistemde kurulu küratörlü yetenekleri kullan; yeni skill arama veya kurma denemesi yapma.
- Dayanak pasajlardan yararlanman istenmişse köşeli parantezli atıf etiketlerini koru ([1], [2] vb.).
- Dış iletişim gerektiren çıktıları taslak olarak üret; otomatik gönderim yapma.
"""


@dataclass(frozen=True)
class OpenClawResult:
    ok: bool
    text: str = ""
    provider: str = "openai-codex"
    model: str = ""
    error: str | None = None
    raw: dict[str, Any] | None = None


class OpenClawRuntime:
    def __init__(
        self,
        *,
        state_dir: Path,
        image: str,
        timeout_seconds: int = 75,
        provider_type: str = "",
        provider_configured: bool = False,
    ) -> None:
        self.state_dir = state_dir
        self.image = image
        self.timeout_seconds = max(15, int(timeout_seconds or 75))
        self.provider_type = provider_type or ""
        self.provider_configured = provider_configured
        self._docker_binary = shutil.which("docker")
        self.workspace_contract: Any | None = None

    @property
    def enabled(self) -> bool:
        return (
            self.provider_type == "openai-codex"
            and self.provider_configured
            and bool(self._docker_binary)
            and self.state_dir.exists()
        )

    def complete(self, prompt: str) -> OpenClawResult:
        if not self.enabled:
            return OpenClawResult(ok=False, error="openclaw_runtime_not_enabled")
        if not prompt.strip():
            return OpenClawResult(ok=False, error="empty_prompt")

        try:
            self._ensure_workspace()
            completed = subprocess.run(
                [
                    self._docker_binary or "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{self.state_dir}:/home/node/.openclaw",
                    self.image,
                    "openclaw",
                    "agent",
                    "--agent",
                    "main",
                    "--message",
                    prompt,
                    "--json",
                    "--local",
                    "--timeout",
                    str(self.timeout_seconds),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds + 15,
            )
        except subprocess.TimeoutExpired:
            return OpenClawResult(ok=False, error="openclaw_runtime_timeout")
        except OSError as exc:
            return OpenClawResult(ok=False, error=f"openclaw_runtime_exec_error:{exc}")

        raw_output = "\n".join(part for part in [completed.stdout, completed.stderr] if part).strip()
        if completed.returncode != 0:
            return OpenClawResult(ok=False, error=raw_output or "openclaw_runtime_failed")

        payload = self._parse_json_output(completed.stdout)
        if not payload:
            return OpenClawResult(ok=False, error="openclaw_runtime_invalid_json")

        text = self._extract_text(payload)
        agent_meta = payload.get("meta", {}).get("agentMeta") or {}
        model = str(agent_meta.get("model") or payload.get("meta", {}).get("model") or payload.get("model") or "")
        provider = str(agent_meta.get("provider") or payload.get("meta", {}).get("provider") or "openai-codex")
        if not text:
            return OpenClawResult(ok=False, error="openclaw_runtime_empty_text", raw=payload, model=model, provider=provider)
        lowered = text.lower()
        if "rate limit" in lowered or "too many requests" in lowered:
            return OpenClawResult(ok=False, error=text, raw=payload, model=model, provider=provider)
        return OpenClawResult(ok=True, text=text.strip(), raw=payload, model=model, provider=provider)

    def _ensure_workspace(self) -> None:
        if self.workspace_contract and hasattr(self.workspace_contract, "sync"):
            self.workspace_contract.sync()
            return
        workspace_dir = self.state_dir / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        agents_path = workspace_dir / "AGENTS.md"
        current = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
        if current.strip() != WORKSPACE_AGENTS_TEXT.strip():
            agents_path.write_text(WORKSPACE_AGENTS_TEXT, encoding="utf-8")

    @staticmethod
    def _parse_json_output(stdout: str) -> dict[str, Any] | None:
        cleaned = (stdout or "").strip()
        if not cleaned:
            return None
        try:
            value = json.loads(cleaned)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict):
            return value

        lines = [line.rstrip() for line in cleaned.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            if not line.lstrip().startswith("{"):
                continue
            candidate = "\n".join(lines[index:])
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = cleaned[start : end + 1]
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                return None
            if isinstance(value, dict):
                return value
        return None

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        candidates = [
            ((payload.get("payloads") or [{}])[0] or {}).get("text") if isinstance(payload.get("payloads"), list) and payload.get("payloads") else None,
            payload.get("payload", {}).get("text"),
            payload.get("text"),
            payload.get("message"),
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate
        return ""


def create_openclaw_runtime(settings: Any) -> OpenClawRuntime:
    state_dir = Path(settings.openclaw_state_dir).expanduser() if settings.openclaw_state_dir else Path()
    return OpenClawRuntime(
        state_dir=state_dir,
        image=settings.openclaw_image,
        timeout_seconds=settings.openclaw_timeout_seconds,
        provider_type=settings.provider_type,
        provider_configured=settings.provider_configured,
    )
