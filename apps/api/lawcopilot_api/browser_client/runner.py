from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from typing import Any
from urllib.parse import urlparse

from ..config import resolve_repo_path


def _worker_entry_candidates() -> list[Path]:
    env_path = str(os.getenv("LAWCOPILOT_BROWSER_WORKER_ENTRY") or "").strip()
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path).expanduser())
    for relative in (
        "apps/browser-worker/dist/cli.js",
        "apps/browser-worker/dist/index.js",
        "apps/browser-worker/src/cli.mjs",
        "apps/browser-worker/src/index.mjs",
        "apps/browser-worker/src/cli.js",
        "apps/browser-worker/src/index.js",
    ):
        candidates.append(resolve_repo_path(relative))
    return candidates


class BrowserWorkerClient:
    def __init__(
        self,
        *,
        enabled: bool = True,
        command: str = "",
        profile_dir: str | None = None,
        artifacts_dir: str | None = None,
        downloads_dir: str | None = None,
        allowed_domains: tuple[str, ...] = (),
        timeout_seconds: int = 45,
    ) -> None:
        self.enabled = bool(enabled)
        self.timeout_seconds = max(10, int(timeout_seconds or 45))
        self.profile_dir = str(profile_dir or resolve_repo_path("artifacts/browser/profile"))
        self.artifacts_dir = str(artifacts_dir or resolve_repo_path("artifacts/browser/artifacts"))
        self.downloads_dir = str(downloads_dir or resolve_repo_path("artifacts/browser/downloads"))
        self.allowed_domains = tuple(str(item or "").strip().lower() for item in allowed_domains if str(item or "").strip())
        self.command_env = self._build_command_env()
        self.command_parts = self._resolve_command_parts(command)
        self.install_command_parts = self._resolve_install_command_parts()
        self._install_attempted = False

    def _build_command_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if str(os.getenv("LAWCOPILOT_BROWSER_WORKER_RUN_AS_NODE") or "").strip().lower() == "true":
            env["ELECTRON_RUN_AS_NODE"] = "1"
        return env

    def _resolve_command_parts(self, command: str) -> list[str]:
        explicit = shlex.split(str(command or "").strip())
        if explicit:
            if len(explicit) == 1:
                entry_path = next((candidate for candidate in _worker_entry_candidates() if candidate.exists()), None)
                if entry_path:
                    return [explicit[0], str(entry_path)]
            return explicit
        node_binary = shutil.which("node")
        entry_path = next((candidate for candidate in _worker_entry_candidates() if candidate.exists()), None)
        if not node_binary or not entry_path:
            return []
        return [node_binary, str(entry_path)]

    def _resolve_install_command_parts(self) -> list[str]:
        install_entry = str(os.getenv("LAWCOPILOT_BROWSER_WORKER_INSTALL_ENTRY") or "").strip()
        explicit = shlex.split(str(os.getenv("LAWCOPILOT_BROWSER_WORKER_INSTALL_COMMAND") or "").strip())
        if explicit:
            return explicit
        if install_entry and self.command_parts:
            return [self.command_parts[0], install_entry]
        return []

    @property
    def available(self) -> bool:
        return self.enabled and bool(self.command_parts)

    def extract(self, url: str, *, include_screenshot: bool = True, preferred_mode: str = "browser") -> dict[str, Any]:
        if not self.available:
            return {"ok": False, "error": "browser_worker_unavailable"}
        parsed = urlparse(str(url or "").strip())
        effective_allowed_domains = list(self.allowed_domains)
        if not effective_allowed_domains and parsed.hostname:
            effective_allowed_domains = [str(parsed.hostname).strip().lower()]
        actions: list[dict[str, Any]] = [
            {
                "type": "extract",
                "url": url,
                "includeLinks": True,
            }
        ]
        if include_screenshot:
            actions.append(
                {
                    "type": "screenshot",
                    "url": url,
                    "fullPage": True,
                    "fileName": "page-snapshot.png",
                }
            )
        payload = {
            "requestId": f"extract-{abs(hash((url, preferred_mode))) % 1_000_000_000}",
            "profileDir": self.profile_dir,
            "artifactsDir": self.artifacts_dir,
            "downloadsDir": self.downloads_dir,
            "allowedDomains": effective_allowed_domains,
            "actions": actions,
            "headless": True,
        }
        try:
            completed = subprocess.run(
                self.command_parts,
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                check=False,
                timeout=self.timeout_seconds,
                env=self.command_env,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "browser_worker_timeout"}
        except OSError as exc:
            return {"ok": False, "error": f"browser_worker_exec_error:{exc}"}
        raw = (completed.stdout or "").strip() or (completed.stderr or "").strip()
        if completed.returncode != 0:
            if self._should_install_browser(raw) and self._install_browser_binaries():
                return self.extract(url, include_screenshot=include_screenshot, preferred_mode=preferred_mode)
            return {"ok": False, "error": raw or f"browser_worker_failed:{completed.returncode}"}
        try:
            decoded = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "error": "browser_worker_invalid_json"}
        if not isinstance(decoded, dict):
            return {"ok": False, "error": "browser_worker_invalid_payload"}
        if not decoded.get("ok"):
            if self._should_install_browser(decoded) and self._install_browser_binaries():
                return self.extract(url, include_screenshot=include_screenshot, preferred_mode=preferred_mode)
            return {"ok": False, "error": decoded.get("warnings") or decoded.get("results") or raw}
        return self._normalize_extract_response(url, decoded, preferred_mode=preferred_mode)

    def _should_install_browser(self, error_payload: Any) -> bool:
        if self._install_attempted or not self.install_command_parts:
            return False
        text = json.dumps(error_payload, ensure_ascii=False) if isinstance(error_payload, (dict, list)) else str(error_payload or "")
        lowered = text.lower()
        return (
            "please run the following command" in lowered
            or "browser executable is missing" in lowered
            or "executable doesn't exist" in lowered
            or "failed to launch browser process" in lowered
        )

    def _install_browser_binaries(self) -> bool:
        self._install_attempted = True
        try:
            completed = subprocess.run(
                [*self.install_command_parts, "install", "chromium"],
                text=True,
                capture_output=True,
                check=False,
                timeout=max(self.timeout_seconds, 900),
                env=self.command_env,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return completed.returncode == 0

    def _normalize_extract_response(self, url: str, decoded: dict[str, Any], *, preferred_mode: str) -> dict[str, Any]:
        results = list(decoded.get("results") or [])
        extract_result = next((item for item in results if str(item.get("action") or "") == "extract"), {})
        screenshot_result = next((item for item in results if str(item.get("action") or "") == "screenshot"), {})
        data = dict(extract_result.get("data") or {})
        artifact_paths: list[str] = []
        for item in (extract_result, screenshot_result):
            for path in list(item.get("artifactPaths") or []):
                value = str(path or "").strip()
                if value and value not in artifact_paths:
                    artifact_paths.append(value)
        visible_text = str(data.get("text") or "").strip()
        final_url = str(extract_result.get("url") or data.get("url") or url).strip()
        links = []
        for item in list(data.get("links") or []):
            if not isinstance(item, dict):
                continue
            href = str(item.get("href") or "").strip()
            if href:
                links.append(href)
        social_links = [link for link in links if any(host in (urlparse(link).netloc or "").lower() for host in ("x.com", "twitter.com", "linkedin.com", "instagram.com", "facebook.com", "youtube.com", "github.com"))][:10]
        contact_hints: list[str] = []
        lowered_text = visible_text.lower()
        if re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", visible_text, re.IGNORECASE):
            contact_hints.append("e-posta")
        if re.search(r"\+\d[\d\s().-]{6,}", visible_text):
            contact_hints.append("telefon")
        if "iletişim" in lowered_text or "contact" in lowered_text:
            contact_hints.append("iletişim sayfası")
        artifacts = []
        for path in artifact_paths:
            suffix = Path(path).suffix.lower()
            artifact_type = "screenshot" if suffix == ".png" else "dom_extract"
            artifacts.append(
                {
                    "artifact_type": artifact_type,
                    "path": path,
                    "url": final_url,
                }
            )
        payload = {
            "url": url,
            "final_url": final_url,
            "reachable": True,
            "render_mode": preferred_mode,
            "title": str(data.get("title") or "").strip(),
            "headings": [],
            "visible_text": visible_text,
            "links": links[:40],
            "social_links": social_links,
            "contact_hints": list(dict.fromkeys(contact_hints)),
            "likely_spa": preferred_mode == "browser",
            "issues": list(decoded.get("warnings") or []),
            "artifacts": artifacts,
            "summary": "Tarayıcı worker ile render edilen sayfa özeti çıkarıldı.",
        }
        return {
            "ok": True,
            "payload": payload,
            "results": results,
            "warnings": list(decoded.get("warnings") or []),
        }


def create_browser_worker_client(
    *,
    enabled: bool = True,
    command: str = "",
    profile_dir: str | None = None,
    artifacts_dir: str | None = None,
    downloads_dir: str | None = None,
    allowed_domains: tuple[str, ...] = (),
    timeout_seconds: int = 45,
) -> BrowserWorkerClient:
    return BrowserWorkerClient(
        enabled=enabled,
        command=command,
        profile_dir=profile_dir,
        artifacts_dir=artifacts_dir,
        downloads_dir=downloads_dir,
        allowed_domains=allowed_domains,
        timeout_seconds=timeout_seconds,
    )
