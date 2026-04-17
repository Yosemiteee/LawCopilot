from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import os
import shutil
from pathlib import Path
from typing import Any

from .assistant_core import DEFAULT_ASSISTANT_ROLE_SUMMARY, DEFAULT_ASSISTANT_TONE
from .assistant import build_assistant_agenda, build_assistant_calendar, build_assistant_home, build_assistant_inbox
from .assistant_context_policy import context_policy_dict
from .tools import create_tool_registry

CORE_FILES = (
    "AGENTS.md",
    "SOUL.md",
    "USER.md",
    "IDENTITY.md",
    "SYSTEM.md",
    "TOOLS.md",
    "HEARTBEAT.md",
    "MEMORY.md",
    "CONTEXT.md",
    "PROGRESS.md",
)
PREVIEW_FILES = CORE_FILES + ("BOOTSTRAP.md",)


@dataclass(frozen=True)
class CuratedSkill:
    slug: str
    title: str
    summary: str
    enabled: bool
    reason: str | None = None


def create_openclaw_workspace_contract(settings: Any, store: Any, events: Any | None = None) -> "OpenClawWorkspaceContract":
    state_dir = Path(settings.openclaw_state_dir).expanduser() if settings.openclaw_state_dir else None
    return OpenClawWorkspaceContract(
        settings=settings,
        store=store,
        events=events,
        state_dir=state_dir,
    )


class OpenClawWorkspaceContract:
    def __init__(
        self,
        *,
        settings: Any,
        store: Any,
        events: Any | None,
        state_dir: Path | None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.events = events
        self.state_dir = state_dir
        self.asset_root = Path(__file__).resolve().parent / "openclaw_assets" / "skills"

    @property
    def enabled(self) -> bool:
        return self.state_dir is not None and str(self.state_dir).strip() != ""

    def sync(self) -> dict[str, Any]:
        if not self.enabled:
            return self.status()

        workspace_dir = self._workspace_dir()
        self._ensure_dirs(workspace_dir)

        profile = self.store.get_user_profile(self.settings.office_id)
        runtime_profile = self.store.get_assistant_runtime_profile(self.settings.office_id)
        connected_accounts = self.store.list_connected_accounts(self.settings.office_id)
        workspace_root = self.store.get_active_workspace_root(self.settings.office_id)
        home = build_assistant_home(self.store, self.settings.office_id)
        agenda = build_assistant_agenda(self.store, self.settings.office_id)
        inbox = build_assistant_inbox(self.store, self.settings.office_id)
        calendar = build_assistant_calendar(self.store, self.settings.office_id, window_days=14)
        thread = self.store.get_assistant_thread(self.settings.office_id)
        messages = self.store.list_assistant_messages(self.settings.office_id, thread_id=int(thread["id"]), limit=8) if thread else []
        drafts = self.store.list_outbound_drafts(self.settings.office_id)
        recent_events = self.events.recent(12) if self.events else []

        bootstrap_required = self._bootstrap_required(profile, runtime_profile)
        curated_skills = self._sync_curated_skills(workspace_dir)
        tool_catalog = self._tool_catalog()

        files = {
            "AGENTS.md": self._build_agents_md(runtime_profile),
            "SOUL.md": self._build_soul_md(runtime_profile),
            "USER.md": self._build_user_md(profile),
            "IDENTITY.md": self._build_identity_md(runtime_profile),
            "SYSTEM.md": self._build_system_md(
                profile=profile,
                runtime_profile=runtime_profile,
                workspace_root=workspace_root,
                connected_accounts=connected_accounts,
                curated_skills=curated_skills,
                tool_catalog=tool_catalog,
                home=home,
                drafts=drafts,
                bootstrap_required=bootstrap_required,
            ),
            "TOOLS.md": self._build_tools_md(runtime_profile, workspace_root, connected_accounts, curated_skills, tool_catalog),
            "HEARTBEAT.md": self._build_heartbeat_md(profile, runtime_profile),
            "MEMORY.md": self._build_memory_md(
                workspace_root=workspace_root,
                home=home,
                agenda=agenda,
                inbox=inbox,
                calendar=calendar,
                connected_accounts=connected_accounts,
                messages=messages,
                drafts=drafts,
            ),
            "CONTEXT.md": self._build_context_md(
                profile=profile,
                runtime_profile=runtime_profile,
                workspace_root=workspace_root,
                connected_accounts=connected_accounts,
                home=home,
                messages=messages,
                drafts=drafts,
                tool_catalog=tool_catalog,
                curated_skills=curated_skills,
            ),
            "PROGRESS.md": self._build_progress_md(
                home=home,
                agenda=agenda,
                inbox=inbox,
                calendar=calendar,
                drafts=drafts,
                messages=messages,
                recent_events=recent_events,
            ),
        }
        for name, content in files.items():
            self._write_if_changed(workspace_dir / name, content)

        bootstrap_path = workspace_dir / "BOOTSTRAP.md"
        if bootstrap_required:
            self._write_if_changed(bootstrap_path, self._build_bootstrap_md(profile, runtime_profile))
        elif bootstrap_path.exists():
            bootstrap_path.unlink()

        daily_log_path = workspace_dir / "memory" / "daily-logs" / f"{date.today().isoformat()}.md"
        self._write_if_changed(
            daily_log_path,
            self._build_daily_log_md(
                workspace_root=workspace_root,
                home=home,
                agenda=agenda,
                connected_accounts=connected_accounts,
                messages=messages,
                recent_events=recent_events,
                profile=profile,
                runtime_profile=runtime_profile,
                drafts=drafts,
            ),
        )

        context_snapshot = self._build_context_snapshot(
            workspace_root=workspace_root,
            profile=profile,
            runtime_profile=runtime_profile,
            connected_accounts=connected_accounts,
            home=home,
            agenda=agenda,
            inbox=inbox,
            calendar=calendar,
            messages=messages,
            drafts=drafts,
            recent_events=recent_events,
            curated_skills=curated_skills,
            tool_catalog=tool_catalog,
            bootstrap_required=bootstrap_required,
        )
        capabilities_manifest = self._build_capabilities_manifest(
            workspace_root=workspace_root,
            connected_accounts=connected_accounts,
            curated_skills=curated_skills,
            tool_catalog=tool_catalog,
        )
        system_status = self._build_system_status(
            workspace_root=workspace_root,
            profile=profile,
            runtime_profile=runtime_profile,
            connected_accounts=connected_accounts,
            curated_skills=curated_skills,
            tool_catalog=tool_catalog,
            home=home,
            drafts=drafts,
            bootstrap_required=bootstrap_required,
        )
        structured_files = {
            self._structured_dir(workspace_dir) / "context-snapshot.json": json.dumps(context_snapshot, ensure_ascii=False, indent=2) + "\n",
            self._structured_dir(workspace_dir) / "capabilities.json": json.dumps(capabilities_manifest, ensure_ascii=False, indent=2) + "\n",
            self._structured_dir(workspace_dir) / "system-status.json": json.dumps(system_status, ensure_ascii=False, indent=2) + "\n",
        }
        for path, content in structured_files.items():
            self._write_if_changed(path, content)

        resources_manifest = self._build_resources_manifest(
            workspace_dir=workspace_dir,
            bootstrap_required=bootstrap_required,
        )
        self._write_if_changed(
            self._structured_dir(workspace_dir) / "resources.json",
            json.dumps(resources_manifest, ensure_ascii=False, indent=2) + "\n",
        )

        state = self._load_state()
        now = self._now()
        if bootstrap_required and not state.get("bootstrapSeededAt"):
            state["bootstrapSeededAt"] = now
        state.update(
            {
                "version": 2,
                "lastSyncAt": now,
                "bootstrapRequired": bootstrap_required,
                "curatedSkills": curated_skills,
                "curatedSkillCount": len([skill for skill in curated_skills if skill.get("enabled")]),
                "toolCount": len(tool_catalog),
                "toolNamespaceCount": len(capabilities_manifest.get("tool_namespaces") or []),
                "resourceCount": len(resources_manifest.get("resources") or []),
                "workspaceReady": self._workspace_ready(workspace_dir),
            }
        )
        self._write_if_changed(self._workspace_state_path(), json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        return self.status(include_previews=False)

    def status(self, *, include_previews: bool = False) -> dict[str, Any]:
        if not self.enabled:
            return {
                "enabled": False,
                "workspace_ready": False,
                "bootstrap_required": False,
                "last_sync_at": None,
                "workspace_path": None,
                "curated_skill_count": 0,
                "curated_skills": [],
                "tool_count": 0,
                "tool_namespace_count": 0,
                "resource_count": 0,
                "files": [],
                "daily_log_path": None,
                "progress_path": None,
                "system_path": None,
                "context_snapshot_path": None,
                "capability_manifest_path": None,
                "system_status_path": None,
                "resource_manifest_path": None,
            }

        workspace_dir = self._workspace_dir()
        state = self._load_state()
        curated_skills = state.get("curatedSkills")
        if not isinstance(curated_skills, list):
            curated_skills = self._read_curated_skill_manifest(workspace_dir)
        files: list[dict[str, Any]] = []
        if include_previews:
            for name in PREVIEW_FILES:
                path = workspace_dir / name
                files.append(
                    {
                        "name": name,
                        "path": str(path),
                        "exists": path.exists(),
                        "preview": path.read_text(encoding="utf-8") if path.exists() else "",
                    }
                )
        return {
            "enabled": True,
            "workspace_ready": self._workspace_ready(workspace_dir),
            "bootstrap_required": bool(state.get("bootstrapRequired")) or (workspace_dir / "BOOTSTRAP.md").exists(),
            "last_sync_at": state.get("lastSyncAt"),
            "workspace_path": str(workspace_dir),
            "curated_skill_count": len([skill for skill in curated_skills if isinstance(skill, dict) and skill.get("enabled")]),
            "curated_skills": curated_skills,
            "tool_count": int(state.get("toolCount") or 0),
            "tool_namespace_count": int(state.get("toolNamespaceCount") or 0),
            "resource_count": int(state.get("resourceCount") or 0),
            "files": files,
            "daily_log_path": str(self._latest_daily_log_path(workspace_dir)),
            "progress_path": str(workspace_dir / "PROGRESS.md"),
            "system_path": str(workspace_dir / "SYSTEM.md"),
            "context_snapshot_path": str(self._structured_dir(workspace_dir) / "context-snapshot.json"),
            "capability_manifest_path": str(self._structured_dir(workspace_dir) / "capabilities.json"),
            "system_status_path": str(self._structured_dir(workspace_dir) / "system-status.json"),
            "resource_manifest_path": str(self._structured_dir(workspace_dir) / "resources.json"),
        }

    def _workspace_dir(self) -> Path:
        return (self.state_dir or Path()) / "workspace"

    def _workspace_state_path(self) -> Path:
        return self._workspace_dir() / ".openclaw" / "workspace-state.json"

    @staticmethod
    def _structured_dir(workspace_dir: Path) -> Path:
        return workspace_dir / ".openclaw"

    def _load_state(self) -> dict[str, Any]:
        path = self._workspace_state_path()
        if not path.exists():
            return {"version": 2}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"version": 2}

    def _ensure_dirs(self, workspace_dir: Path) -> None:
        self._structured_dir(workspace_dir).mkdir(parents=True, exist_ok=True)
        (workspace_dir / "memory" / "daily-logs").mkdir(parents=True, exist_ok=True)
        (workspace_dir / "skills").mkdir(parents=True, exist_ok=True)

    def _write_if_changed(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if current == content:
            return
        path.write_text(content, encoding="utf-8")

    def _bootstrap_required(self, profile: dict[str, Any], runtime_profile: dict[str, Any]) -> bool:
        user_ready = bool(str(profile.get("display_name") or "").strip() or str(profile.get("assistant_notes") or "").strip())
        return not user_ready

    def _curated_skills(self) -> list[CuratedSkill]:
        tavily_enabled = bool(os.getenv("TAVILY_API_KEY", "").strip())
        google_bridge_enabled = bool(self.settings.google_enabled or self.settings.google_configured)
        return [
            CuratedSkill(
                slug="proactive-tasks",
                title="Proaktif Görevler",
                summary="Yaklaşan işler, hazırlık gerektiren tarihler ve takip maddeleri için rehber davranışlar sağlar.",
                enabled=True,
            ),
            CuratedSkill(
                slug="tavily-search",
                title="Tavily Arama",
                summary="Güncel dış bilgi aramasını yalnız güvenli yapılandırma mevcutsa açar.",
                enabled=tavily_enabled,
                reason=None if tavily_enabled else "TAVILY_API_KEY tanımlı olmadığı için devre dışı.",
            ),
            CuratedSkill(
                slug="gog-bridge",
                title="GOG Google Köprüsü",
                summary="Gmail, Takvim ve Drive yansımalarını LawCopilot çalışma alanına bağlayan Google yardımcı skill'i.",
                enabled=google_bridge_enabled,
                reason=None if google_bridge_enabled else "Google entegrasyonu etkin olmadığı için devre dışı.",
            ),
        ]

    def _sync_curated_skills(self, workspace_dir: Path) -> list[dict[str, Any]]:
        skills_dir = workspace_dir / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        curated = self._curated_skills()
        manifest: list[dict[str, Any]] = []
        keep = {"manifest.json"}
        for skill in curated:
            manifest.append(
                {
                    "slug": skill.slug,
                    "title": skill.title,
                    "summary": skill.summary,
                    "enabled": skill.enabled,
                    "reason": skill.reason,
                }
            )
            source_dir = self.asset_root / skill.slug
            target_dir = skills_dir / skill.slug
            if skill.enabled and source_dir.exists():
                shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
                keep.add(skill.slug)
            elif target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)

        for child in skills_dir.iterdir():
            if child.name in keep:
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink()

        self._write_if_changed(skills_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        return manifest

    def _read_curated_skill_manifest(self, workspace_dir: Path) -> list[dict[str, Any]]:
        manifest_path = workspace_dir / "skills" / "manifest.json"
        if not manifest_path.exists():
            return []
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        return value if isinstance(value, list) else []

    def _workspace_ready(self, workspace_dir: Path) -> bool:
        if not workspace_dir.exists():
            return False
        required_paths = [workspace_dir / name for name in CORE_FILES]
        required_paths.append(workspace_dir / "skills" / "manifest.json")
        required_paths.append(workspace_dir / "memory" / "daily-logs")
        required_paths.append(self._structured_dir(workspace_dir) / "context-snapshot.json")
        required_paths.append(self._structured_dir(workspace_dir) / "capabilities.json")
        required_paths.append(self._structured_dir(workspace_dir) / "system-status.json")
        required_paths.append(self._structured_dir(workspace_dir) / "resources.json")
        return all(path.exists() for path in required_paths)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _tool_catalog(self) -> list[dict[str, Any]]:
        registry = create_tool_registry(settings=self.settings, store=self.store, events=self.events, web_intel=None)
        return sorted(
            [
                {
                    **tool,
                    "namespace": str(tool.get("name") or "").split(".", 1)[0] if "." in str(tool.get("name") or "") else str(tool.get("name") or ""),
                }
                for tool in registry.list_tools()
            ],
            key=lambda item: str(item.get("name") or ""),
        )

    @staticmethod
    def _tool_namespaces(tool_catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets: dict[str, list[dict[str, Any]]] = {}
        for item in tool_catalog:
            namespace = str(item.get("namespace") or item.get("name") or "general").strip() or "general"
            buckets.setdefault(namespace, []).append(item)
        summary_map = {
            "assistant": "Ajanda, iletişim ve günlük ofis bağlamı araçları.",
            "web": "Dış web araştırması ve sayfa inceleme araçları.",
            "travel": "Seyahat araştırması, rota ve rezervasyon bağlamı araçları.",
            "weather": "Hava durumu ve dış ortam bağlamı araçları.",
            "places": "Yakın çevre, mekân ve harita bağlamı araçları.",
            "matter": "Dosya bazlı belge ve dayanak araçları.",
            "workspace": "Çalışma alanı belge havuzu araçları.",
            "social": "Sosyal sinyal ve dış risk izleme araçları.",
        }
        namespaces: list[dict[str, Any]] = []
        for namespace, items in sorted(buckets.items()):
            namespaces.append(
                {
                    "name": namespace,
                    "summary": summary_map.get(namespace, "Genel amaçlı araç kümesi."),
                    "tool_count": len(items),
                    "tools": [str(item.get("name") or "") for item in items],
                }
            )
        return namespaces

    @staticmethod
    def _connected_account_items(connected_accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for account in connected_accounts:
            items.append(
                {
                    "provider": str(account.get("provider") or "").strip(),
                    "status": str(account.get("status") or "").strip(),
                    "label": str(account.get("account_label") or account.get("provider") or "").strip(),
                    "scopes": [str(scope).strip() for scope in list(account.get("scopes") or []) if str(scope).strip()],
                }
            )
        return items

    def _build_context_snapshot(
        self,
        *,
        workspace_root: dict[str, Any] | None,
        profile: dict[str, Any],
        runtime_profile: dict[str, Any],
        connected_accounts: list[dict[str, Any]],
        home: dict[str, Any],
        agenda: list[dict[str, Any]],
        inbox: list[dict[str, Any]],
        calendar: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        drafts: list[dict[str, Any]],
        recent_events: list[dict[str, Any]],
        curated_skills: list[dict[str, Any]],
        tool_catalog: list[dict[str, Any]],
        bootstrap_required: bool,
    ) -> dict[str, Any]:
        pending_drafts = [item for item in drafts if str(item.get("approval_status") or "") != "approved"]
        return {
            "version": 1,
            "generated_at": self._now(),
            "agentic_contract": {
                "primary_files": list(CORE_FILES),
                "dynamic_files": ["MEMORY.md", "PROGRESS.md", "memory/daily-logs/<today>.md"],
                "continuity_model": "identity_and_user_static_plus_memory_and_progress_dynamic",
                "skill_policy": "curated_only",
                "local_source_priority": True,
                "canonical_status_file": ".openclaw/system-status.json",
            },
            "cache_hints": {
                "strategy": "static_prefix_first_dynamic_tail",
                "static_sections": ["assistant_profile", "user_profile", "workspace", "capabilities"],
                "dynamic_sections": ["home", "agenda", "inbox", "calendar", "recent_messages", "recent_events", "drafts"],
            },
            "context_policy": context_policy_dict(),
            "workspace": {
                "display_name": workspace_root.get("display_name") if workspace_root else None,
                "root_path": workspace_root.get("root_path") if workspace_root else None,
                "bootstrap_required": bootstrap_required,
            },
            "profiles": {
                "user": {
                    "display_name": profile.get("display_name"),
                    "favorite_color": profile.get("favorite_color"),
                    "communication_style": profile.get("communication_style"),
                    "assistant_notes": profile.get("assistant_notes"),
                    "important_dates": list(profile.get("important_dates") or [])[:6],
                },
                "assistant": {
                    "assistant_name": runtime_profile.get("assistant_name"),
                    "role_summary": runtime_profile.get("role_summary"),
                    "tone": runtime_profile.get("tone"),
                    "soul_notes": runtime_profile.get("soul_notes"),
                    "tools_notes": runtime_profile.get("tools_notes"),
                    "heartbeat_extra_checks": list(runtime_profile.get("heartbeat_extra_checks") or [])[:10],
                },
            },
            "state": {
                "today_summary": home.get("today_summary") or "",
                "priority_items": [
                    {
                        "title": item.get("title"),
                        "details": item.get("details"),
                        "priority": item.get("priority"),
                    }
                    for item in list(home.get("priority_items") or [])[:6]
                ],
                "counts": {
                    "agenda": len(agenda),
                    "inbox": len(inbox),
                    "calendar": len(calendar),
                    "pending_drafts": len(pending_drafts),
                },
                "connected_accounts": self._connected_account_items(connected_accounts),
                "recent_messages": [
                    {
                        "role": str(item.get("role") or ""),
                        "content": self._compact_text(item.get("content") or "", max_len=220),
                    }
                    for item in messages[-6:]
                ],
                "pending_drafts": [
                    {
                        "channel": item.get("channel"),
                        "title": item.get("title") or item.get("subject") or item.get("draft_type"),
                        "approval_status": item.get("approval_status"),
                        "delivery_status": item.get("delivery_status"),
                    }
                    for item in pending_drafts[:6]
                ],
                "recent_events": [self._sanitize_event(event) for event in recent_events[:8]],
            },
            "capability_summary": {
                "tool_count": len(tool_catalog),
                "tool_namespace_count": len(self._tool_namespaces(tool_catalog)),
                "curated_skill_count": len([skill for skill in curated_skills if skill.get("enabled")]),
                "connector_count": len(connected_accounts),
            },
        }

    def _build_capabilities_manifest(
        self,
        *,
        workspace_root: dict[str, Any] | None,
        connected_accounts: list[dict[str, Any]],
        curated_skills: list[dict[str, Any]],
        tool_catalog: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "version": 1,
            "generated_at": self._now(),
            "workspace": {
                "display_name": workspace_root.get("display_name") if workspace_root else None,
                "root_path": workspace_root.get("root_path") if workspace_root else None,
            },
            "behavior_contract": {
                "core_files": list(CORE_FILES),
                "bootstrap_file": "BOOTSTRAP.md",
                "skill_policy": "curated_only",
                "local_source_priority": True,
                "draft_first_external_actions": True,
                "system_contract_file": "SYSTEM.md",
            },
            "approval_model": {
                "draft_plus_human_approval": True,
                "auto_dispatch": False,
                "execution_postures": ["ask", "suggest", "auto"],
            },
            "tool_namespaces": self._tool_namespaces(tool_catalog),
            "tools": tool_catalog,
            "connectors": self._connected_account_items(connected_accounts),
            "curated_skills": curated_skills,
            "context_policy": context_policy_dict(),
        }

    def _build_resources_manifest(
        self,
        *,
        workspace_dir: Path,
        bootstrap_required: bool,
    ) -> dict[str, Any]:
        now = self._now()
        resources = [
            self._resource_entry(workspace_dir / "AGENTS.md", "agents_md", "Runtime Rules", "Yüksek öncelikli ajan kuralları.", "assistant", 1.0, now),
            self._resource_entry(workspace_dir / "SOUL.md", "soul_md", "Behavior Core", "Asistanın davranış ve sınır notları.", "assistant", 1.0, now),
            self._resource_entry(workspace_dir / "USER.md", "user_md", "User Profile", "Kullanıcıya ait kalıcı tercih ve notlar.", "assistant", 1.0, now),
            self._resource_entry(workspace_dir / "IDENTITY.md", "identity_md", "Assistant Identity", "Asistan adı, rolü ve ton ayarları.", "assistant", 1.0, now),
            self._resource_entry(workspace_dir / "SYSTEM.md", "system_md", "System Contract", "Kanonik kaynak haritası ve aksiyon yürütme sırası.", "assistant", 1.0, now),
            self._resource_entry(workspace_dir / "TOOLS.md", "tools_md", "Capability Overview", "Araç, connector ve skill görünümü.", "assistant", 0.95, now),
            self._resource_entry(workspace_dir / "HEARTBEAT.md", "heartbeat_md", "Heartbeat Checklist", "Periyodik kontrol maddeleri.", "assistant", 0.9, now),
            self._resource_entry(workspace_dir / "MEMORY.md", "memory_md", "Operational Memory", "Güncel sayaçlar ve son konuşma akışı.", "assistant", 0.95, now),
            self._resource_entry(workspace_dir / "CONTEXT.md", "context_md", "Context Contract", "Static/dynamic bağlam sınırları ve cache notları.", "assistant", 1.0, now),
            self._resource_entry(workspace_dir / "PROGRESS.md", "progress_md", "Current Progress", "Aktif öncelikler, takip ve bekleyen işler.", "assistant", 0.95, now),
            self._resource_entry(self._structured_dir(workspace_dir) / "context-snapshot.json", "context_snapshot", "Structured Context Snapshot", "Makine tarafından okunabilir güncel bağlam özeti.", "assistant", 1.0, now),
            self._resource_entry(self._structured_dir(workspace_dir) / "capabilities.json", "capabilities_manifest", "Capabilities Manifest", "Araçlar, namespace'ler, connector'lar ve skill'ler.", "assistant", 0.95, now),
            self._resource_entry(self._structured_dir(workspace_dir) / "system-status.json", "system_status", "System Status", "Kanonik kaynaklar, aksiyon sırası ve çalışma postürü.", "assistant", 1.0, now),
            self._resource_entry(self._structured_dir(workspace_dir) / "resources.json", "resources_manifest", "Resources Manifest", "Workspace içindeki yardımcı resource envanteri.", "assistant", 0.9, now),
        ]
        if bootstrap_required:
            resources.append(
                self._resource_entry(workspace_dir / "BOOTSTRAP.md", "bootstrap_md", "Bootstrap Checklist", "Eksik ilk kurulum bilgileri.", "user", 0.85, now)
            )
        return {"version": 1, "generated_at": now, "resources": resources}

    @staticmethod
    def _resource_entry(path: Path, name: str, title: str, description: str, audience: str, priority: float, now: str) -> dict[str, Any]:
        suffix = path.suffix.lower()
        mime_type = "application/json" if suffix == ".json" else "text/markdown"
        return {
            "uri": path.resolve().as_uri(),
            "name": name,
            "title": title,
            "description": description,
            "mimeType": mime_type,
            "annotations": {
                "audience": [audience],
                "priority": priority,
                "lastModified": now,
            },
        }

    def _build_agents_md(self, runtime_profile: dict[str, Any]) -> str:
        role_summary = str(runtime_profile.get("role_summary") or DEFAULT_ASSISTANT_ROLE_SUMMARY).strip()
        tone = str(runtime_profile.get("tone") or DEFAULT_ASSISTANT_TONE).strip()
        active_forms = [
            str(item.get("title") or item.get("slug") or "").strip()
            for item in list(runtime_profile.get("assistant_forms") or [])
            if isinstance(item, dict) and item.get("active")
        ]
        contract = dict(runtime_profile.get("behavior_contract") or {})
        return "\n".join(
            [
                "# LawCopilot Runtime",
                "",
                "Bu çalışma alanı LawCopilot tarafından yönetilir.",
                "",
                "Rolün:",
                role_summary,
                "",
                "Çalışma Biçimi:",
                "- Kimlik ve davranış için SOUL.md, IDENTITY.md ve USER.md dosyalarını temel al.",
                "- Dinamik bağlam için önce CONTEXT.md, MEMORY.md, PROGRESS.md ve günlük loglara bak.",
                "- Önce yerel kaynaklar ve kayıtlı bağlam; sonra gerekirse küratörlü araçlar ve skill'ler.",
                "- LawCopilot aynı çekirdekten farklı rollere evrilebilen bir asistandır; aktif form ve bağlama göre hukuk, planlama, yazışma, ajanda veya kişisel tercih desteği sunabilirsin.",
                "",
                "Kurallar:",
                "- Yanıtları daima Türkçe yaz.",
                "- Önce çalışma alanındaki dayanaklara ve kayıtlı bağlama bak.",
                "- Kaynak yoksa bunu açıkça belirt; uydurma bilgi üretme.",
                "- Hukuki kesin görüş tonu yerine çalışma notu ve yardımcı asistan tonu kullan.",
                "- Dış iletişim gerektiren içerikleri taslak olarak üret; otomatik gönderim yapma.",
                "- Yalnız uygulama tarafından sağlanan küratörlü yetenekleri kullan; yeni skill kurmaya veya aramaya çalışma.",
                "- Dayanak kullanılıyorsa [1], [2] gibi atıf etiketlerini koru.",
                "",
                "Öncelik Sırası:",
                "1. Yerel dayanaklar ve seçili çalışma alanı",
                "2. Kullanıcı profili, önemli tarihler ve son konuşma bağlamı",
                "3. Düşük riskli okuma araçları",
                "4. Taslak + onay gerektiren dış aksiyonlar",
                "",
                f"Ton: {tone}",
                f"Aktif formlar: {', '.join(active_forms) if active_forms else 'Genel çekirdek'}",
                (
                    "Davranış kontratı: "
                    f"proaktiflik={contract.get('initiative_level') or 'balanced'}, "
                    f"takip={contract.get('follow_up_style') or 'check_in'}, "
                    f"plan={contract.get('planning_depth') or 'structured'}"
                ),
                "",
            ]
        )

    def _build_soul_md(self, runtime_profile: dict[str, Any]) -> str:
        extra = str(runtime_profile.get("soul_notes") or "").strip()
        lines = [
            "# SOUL.md",
            "",
            "## Çekirdek Doğrular",
            "- Süsleyerek değil çözerek yardımcı ol.",
            "- Belirsizlik varsa açıkça söyle; tahmin yürütüyorsan bunu görünür kıl.",
            "- Önce araştır, bağlamı oku, kaynağı tara; sonra soru sor.",
            "- İç analizde üretken, dış aksiyonda temkinli ol.",
            "- Kullanıcının yerine konuşma; özellikle hassas alanlarda taslak ve yardımcı ton kullan.",
            "",
            "## Sınırlar",
            "- Müvekkil, ofis ve kişisel veriler yerel bağlamdır; workspace dışına sızdırma.",
            "- Dış iletişim, paylaşım, gönderim ve yayın işlemleri açık onay olmadan ilerlemez.",
            "- Kaynaksız iddiayı kesin hüküm gibi yazma.",
            "",
            "## Süreklilik",
            "- Her oturumda USER.md, IDENTITY.md, CONTEXT.md, MEMORY.md ve PROGRESS.md dosyalarını çalışma belleği gibi kullan.",
            "- Kalıcı tercih ile geçici oturum bilgisini karıştırma.",
            "- Öğrenilen kalıcı kullanıcı/asistan tercihleri profile yansıtılır; geçici operasyon durumu progress ve günlük loglarda yaşar.",
            "",
            "## Ürün Duruşu",
            "- Müvekkil verisi ve ofis içeriği yerel bağlamdır; üçüncü taraflara sızdırma.",
            "- Açıkça istenmedikçe hukuki görüşü kesin hüküm gibi yazma.",
            "- Konuyu hızlandırmak için kısa, temiz ve profesyonel cevaplar ver.",
            "- Asistan çekirdeği aktif formlara göre hukuk, üretkenlik, iletişim, seyahat veya kişisel düzen gibi farklı alanlara uyum sağlayabilir.",
        ]
        if extra:
            lines.extend(["", "## Ek Notlar", extra])
        lines.append("")
        return "\n".join(lines)

    def _build_user_md(self, profile: dict[str, Any]) -> str:
        important_dates = profile.get("important_dates") or []
        related_profiles = profile.get("related_profiles") or []
        freeform_profile = str(profile.get("assistant_notes") or "").strip()
        lines = [
            "# USER.md",
            "",
            "## Temel Kimlik",
            f"- İsim / hitap: {profile.get('display_name') or 'Belirtilmedi'}",
            f"- Sevdiği renk: {profile.get('favorite_color') or 'Belirtilmedi'}",
            "",
            "## Kullanıcıdan Gelen Not",
            freeform_profile or "Henüz serbest profil notu girilmedi.",
            "",
        ]
        legacy_lines = [
            f"- Sevdiği renk: {profile.get('favorite_color') or 'Belirtilmedi'}",
            f"- İletişim stili: {profile.get('communication_style') or 'Belirtilmedi'}",
            f"- Ulaşım tercihi: {profile.get('transport_preference') or 'Belirtilmedi'}",
            f"- Hava tercihi: {profile.get('weather_preference') or 'Belirtilmedi'}",
            f"- Yeme içme: {profile.get('food_preferences') or 'Belirtilmedi'}",
            f"- Seyahat: {profile.get('travel_preferences') or 'Belirtilmedi'}",
            f"- Ana yaşam / dönüş noktası: {profile.get('home_base') or 'Belirtilmedi'}",
            f"- Güncel konum: {profile.get('current_location') or 'Belirtilmedi'}",
            f"- Yakın çevre tercihleri: {profile.get('location_preferences') or 'Belirtilmedi'}",
            f"- Harita tercihi: {profile.get('maps_preference') or 'Belirtilmedi'}",
            f"- Namaz desteği: {'Açık' if profile.get('prayer_notifications_enabled') else 'Kapalı'}",
            f"- İbadet notu: {profile.get('prayer_habit_notes') or 'Belirtilmedi'}",
        ]
        if any("Belirtilmedi" not in item for item in legacy_lines):
            lines.extend(["## Yapılandırılmış Alanlardan Taşınan Notlar", *legacy_lines, ""])
        lines.append("## Önemli Tarihler")
        if important_dates:
            for item in important_dates[:8]:
                label = item.get("label") or "Önemli tarih"
                value = item.get("date") or "Tarih yok"
                notes = item.get("notes") or ""
                lines.append(f"- {label}: {value}" + (f" | {notes}" if notes else ""))
        else:
            lines.append("- Kayıtlı önemli tarih yok.")
        lines.append("")
        lines.append("## Yakın Çevre Profilleri")
        if related_profiles:
            for item in related_profiles[:8]:
                name = item.get("name") or "Yakın çevre"
                relationship = item.get("relationship") or "İlişki belirtilmedi"
                notes = item.get("notes") or item.get("preferences") or ""
                lines.append(f"- {name} ({relationship})" + (f": {notes}" if notes else ""))
                for date_item in (item.get("important_dates") or [])[:4]:
                    label = date_item.get("label") or "Önemli tarih"
                    value = date_item.get("date") or "Tarih yok"
                    detail = date_item.get("notes") or ""
                    lines.append(f"  - {label}: {value}" + (f" | {detail}" if detail else ""))
        else:
            lines.append("- Kayıtlı aile / yakın çevre profili yok.")
        lines.append("")
        return "\n".join(lines)

    def _build_identity_md(self, runtime_profile: dict[str, Any]) -> str:
        active_forms = [
            str(item.get("title") or item.get("slug") or "").strip()
            for item in list(runtime_profile.get("assistant_forms") or [])
            if isinstance(item, dict) and item.get("active")
        ]
        contract = dict(runtime_profile.get("behavior_contract") or {})
        return "\n".join(
            [
                "# IDENTITY.md",
                "",
                "## Kimlik Kartı",
                f"- Asistan adı: {runtime_profile.get('assistant_name') or 'Belirtilmedi'}",
                f"- Rol özeti: {runtime_profile.get('role_summary') or DEFAULT_ASSISTANT_ROLE_SUMMARY}",
                f"- Ton: {runtime_profile.get('tone') or DEFAULT_ASSISTANT_TONE}",
                f"- Aktif formlar: {', '.join(active_forms) if active_forms else 'Genel çekirdek'}",
                (
                    "- Davranış kontratı: "
                    f"proaktiflik={contract.get('initiative_level') or 'balanced'}, "
                    f"takip={contract.get('follow_up_style') or 'check_in'}, "
                    f"plan={contract.get('planning_depth') or 'structured'}"
                ),
                f"- Avatar: {runtime_profile.get('avatar_path') or 'Belirtilmedi'}",
                "- Çalışma modu: Kaynak dayanaklı, taslak öncelikli, insan denetimli",
                "- Uzmanlık ekseni: Kullanıcının seçtiği forma göre uyarlanabilen çekirdek asistan",
                "- İmza biçimi: Kısa, net, profesyonel",
                "",
            ]
        )

    def _build_system_md(
        self,
        *,
        profile: dict[str, Any],
        runtime_profile: dict[str, Any],
        workspace_root: dict[str, Any] | None,
        connected_accounts: list[dict[str, Any]],
        curated_skills: list[dict[str, Any]],
        tool_catalog: list[dict[str, Any]],
        home: dict[str, Any],
        drafts: list[dict[str, Any]],
        bootstrap_required: bool,
    ) -> str:
        pending_drafts = [item for item in drafts if str(item.get("approval_status") or "") != "approved"]
        kb_root = str(getattr(self.settings, "personal_kb_root", "") or "").strip()
        kb_status = kb_root if bool(getattr(self.settings, "personal_kb_enabled", False)) and kb_root else "Kapalı veya yapılandırılmadı"
        active_skill_count = len([skill for skill in curated_skills if skill.get("enabled")])
        lines = [
            "# SYSTEM.md",
            "",
            "Bu dosya LawCopilot runtime içindeki kanonik kaynak haritasını ve aksiyon yürütme sırasını açıklar.",
            "",
            "## Kanonik Kaynak Haritası",
            "- Asistan kimliği ve rol özeti: IDENTITY.md",
            "- Davranış sınırları ve ürün duruşu: AGENTS.md + SOUL.md",
            "- Kullanıcı kimliği, kalıcı tercihler ve ilişkiler: USER.md",
            "- Anlık çalışma bağlamı: CONTEXT.md",
            "- Güncel operasyonel sayaçlar ve son konuşma izi: MEMORY.md",
            "- Sıradaki iş, bekleyen taslak ve aktif öncelikler: PROGRESS.md",
            "- Araç, connector ve skill görünümü: TOOLS.md + .openclaw/capabilities.json",
            f"- Uzun vadeli wiki/memory katmanı: {kb_status}",
            "",
            "## Aksiyon Yürütme Sırası",
            "1. IDENTITY.md, USER.md ve SOUL.md ile kimlik/ton/sınırları sabitle.",
            "2. CONTEXT.md, MEMORY.md, PROGRESS.md ve günlük loglardan güncel operasyon durumunu çıkar.",
            "3. Gerekirse yerel çalışma alanı ve uzun vadeli knowledge base kayıtlarını kullan.",
            "4. Önce düşük riskli okuma/analiz araçları, sonra taslak üretimi kullan.",
            "5. Dış iletişim, para harcama veya hukuki bağlayıcılığı olan adımları yalnız taslak + onay akışıyla ilerlet.",
            "",
            "## Çalışma Postürü",
            f"- Bootstrap gerekli: {'Evet' if bootstrap_required else 'Hayır'}",
            f"- Çalışma alanı: {workspace_root.get('display_name') if workspace_root else 'Belirtilmedi'}",
            f"- Kullanıcı: {profile.get('display_name') or 'Belirtilmedi'}",
            f"- Asistan: {runtime_profile.get('assistant_name') or 'Belirtilmedi'}",
            f"- Bağlı hesap sayısı: {len(connected_accounts)}",
            f"- Etkin skill sayısı: {active_skill_count}",
            f"- Araç sayısı: {len(tool_catalog)}",
            f"- Bekleyen taslak sayısı: {len(pending_drafts)}",
            f"- Gün özeti: {home.get('today_summary') or 'Özet yok.'}",
            "",
            "## Güvenlik ve Akış İlkeleri",
            "- Yerel kaynak ve kayıtlı bağlam harici web aramasından önce gelir.",
            "- Kanıt yoksa bunu açıkça söyle; boşluğu uydurma bilgiyle doldurma.",
            "- Sistem görünür şekilde taslak-öncelikli ve insan denetimli çalışır.",
            "- Aynı konu hem workspace hem KB tarafında görünüyorsa güncel ve açıklanabilir olan kayıt tercih edilir.",
            "",
        ]
        return "\n".join(lines)

    def _build_tools_md(
        self,
        runtime_profile: dict[str, Any],
        workspace_root: dict[str, Any] | None,
        connected_accounts: list[dict[str, Any]],
        curated_skills: list[dict[str, Any]],
        tool_catalog: list[dict[str, Any]],
    ) -> str:
        lines = [
            "# TOOLS.md",
            "",
            "## Çalışma Alanı",
            f"- Kök klasör: {workspace_root.get('display_name') if workspace_root else 'Belirtilmedi'}",
            f"- Yol: {workspace_root.get('root_path') if workspace_root else 'Belirtilmedi'}",
            "",
            "## Bağlı Hesaplar",
        ]
        if connected_accounts:
            for account in connected_accounts:
                scopes = ", ".join(account.get("scopes") or []) or "scope yok"
                lines.append(f"- {account.get('provider')}: {account.get('status')} | {scopes}")
        else:
            lines.append("- Bağlı hesap yok.")
        lines.extend(["", "## Küratörlü Yetenekler"])
        for skill in curated_skills:
            status = "etkin" if skill.get("enabled") else f"devre dışı ({skill.get('reason') or 'neden belirtilmedi'})"
            lines.append(f"- {skill.get('slug')}: {status}")
        lines.extend(["", "## Araç Namespace'leri"])
        for namespace in self._tool_namespaces(tool_catalog):
            lines.append(f"- {namespace.get('name')}: {namespace.get('tool_count')} araç")
        lines.extend(["", "## Araç Kataloğu"])
        for tool in tool_catalog:
            scopes = ", ".join(str(item).strip() for item in list(tool.get("allowed_scopes") or []) if str(item).strip()) or "scope yok"
            lines.append(
                f"- {tool.get('name')}: {tool.get('label')} | risk={tool.get('risk_level')} | onay={tool.get('approval_policy')} | scope={scopes}"
            )
        extra = str(runtime_profile.get("tools_notes") or "").strip()
        lines.extend(
            [
                "",
                "## Kullanım İlkeleri",
                "- Önce read-only ve düşük riskli araçları kullan.",
                "- Dış web veya harici kaynak yalnız gerçekten gerektiğinde açılır.",
                "- Araçlar düşünmenin yerine geçmez; bağlamla birlikte yorumlanır.",
                "",
                "## Operasyon Notları",
                "- Dış iletişimler taslak ve onay akışıyla yürütülür.",
                "- Araç kullanımı yalnız kullanıcı bağlamına hizmet ettiği kadar yapılır.",
            ]
        )
        if extra:
            lines.extend(["", "## Ek Araç Notları", extra])
        lines.append("")
        return "\n".join(lines)

    def _build_system_status(
        self,
        *,
        workspace_root: dict[str, Any] | None,
        profile: dict[str, Any],
        runtime_profile: dict[str, Any],
        connected_accounts: list[dict[str, Any]],
        curated_skills: list[dict[str, Any]],
        tool_catalog: list[dict[str, Any]],
        home: dict[str, Any],
        drafts: list[dict[str, Any]],
        bootstrap_required: bool,
    ) -> dict[str, Any]:
        pending_drafts = [item for item in drafts if str(item.get("approval_status") or "") != "approved"]
        kb_root = str(getattr(self.settings, "personal_kb_root", "") or "").strip()
        kb_enabled = bool(getattr(self.settings, "personal_kb_enabled", False))
        if bootstrap_required:
            posture = "bootstrap"
        elif pending_drafts:
            posture = "review_and_draft"
        elif list(home.get("priority_items") or []):
            posture = "active_assist"
        else:
            posture = "steady_state"
        return {
            "version": 1,
            "generated_at": self._now(),
            "operating_posture": posture,
            "workspace": {
                "display_name": workspace_root.get("display_name") if workspace_root else None,
                "root_path": workspace_root.get("root_path") if workspace_root else None,
                "bootstrap_required": bootstrap_required,
            },
            "assistant": {
                "name": runtime_profile.get("assistant_name"),
                "role_summary": runtime_profile.get("role_summary"),
                "tone": runtime_profile.get("tone"),
            },
            "user": {
                "display_name": profile.get("display_name"),
                "has_profile_notes": bool(str(profile.get("assistant_notes") or "").strip()),
            },
            "counts": {
                "connected_accounts": len(connected_accounts),
                "curated_skills": len([skill for skill in curated_skills if skill.get("enabled")]),
                "tools": len(tool_catalog),
                "tool_namespaces": len(self._tool_namespaces(tool_catalog)),
                "pending_drafts": len(pending_drafts),
                "priority_items": len(list(home.get("priority_items") or [])),
            },
            "knowledge_base": {
                "enabled": kb_enabled,
                "root": kb_root or None,
            },
            "canonical_sources": [
                {"key": "assistant_identity", "source": "IDENTITY.md", "kind": "workspace_markdown"},
                {"key": "behavior_rules", "source": "AGENTS.md + SOUL.md", "kind": "workspace_markdown"},
                {"key": "user_profile", "source": "USER.md", "kind": "workspace_markdown"},
                {"key": "current_context", "source": "CONTEXT.md", "kind": "workspace_markdown"},
                {"key": "operational_memory", "source": "MEMORY.md + PROGRESS.md", "kind": "workspace_markdown"},
                {"key": "capabilities", "source": ".openclaw/capabilities.json", "kind": "structured_json"},
                {"key": "system_contract", "source": "SYSTEM.md", "kind": "workspace_markdown"},
                {"key": "long_term_memory", "source": kb_root or "not_configured", "kind": "knowledge_base"},
            ],
            "action_pipeline": [
                "identity_and_rules",
                "current_context_and_progress",
                "local_sources_and_kb",
                "low_risk_tools",
                "draft_then_confirm",
            ],
        }

    def _build_context_md(
        self,
        *,
        profile: dict[str, Any],
        runtime_profile: dict[str, Any],
        workspace_root: dict[str, Any] | None,
        connected_accounts: list[dict[str, Any]],
        home: dict[str, Any],
        messages: list[dict[str, Any]],
        drafts: list[dict[str, Any]],
        tool_catalog: list[dict[str, Any]],
        curated_skills: list[dict[str, Any]],
    ) -> str:
        pending_drafts = [item for item in drafts if str(item.get("approval_status") or "") != "approved"]
        policy = context_policy_dict()
        lines = [
            "# CONTEXT.md",
            "",
            "## Static Prefix",
            f"- Kullanıcı hitabı: {profile.get('display_name') or 'Belirtilmedi'}",
            f"- Kullanıcı notu: {profile.get('assistant_notes') or 'Belirtilmedi'}",
            f"- Asistan adı: {runtime_profile.get('assistant_name') or 'Belirtilmedi'}",
            f"- Rol özeti: {runtime_profile.get('role_summary') or 'Belirtilmedi'}",
            f"- Ton: {runtime_profile.get('tone') or 'Belirtilmedi'}",
            f"- Çalışma alanı: {workspace_root.get('display_name') if workspace_root else 'Belirtilmedi'}",
            f"- Bağlı hesap sayısı: {len(connected_accounts)}",
            f"- Araç sayısı: {len(tool_catalog)}",
            f"- Etkin skill sayısı: {len([skill for skill in curated_skills if skill.get('enabled')])}",
            "",
            "## Dynamic Tail",
            f"- Gün özeti: {home.get('today_summary') or 'Özet yok.'}",
            f"- Öncelikli madde sayısı: {len(list(home.get('priority_items') or []))}",
            f"- Bekleyen taslak sayısı: {len(pending_drafts)}",
            "",
            "## Son Konuşma Penceresi",
        ]
        if messages:
            for item in messages[-6:]:
                lines.append(f"- {item.get('role')}: {self._compact_text(item.get('content') or '', max_len=180)}")
        else:
            lines.append("- Henüz mesaj kaydı yok.")
        lines.extend(
            [
                "",
                "## Context Policy",
                f"- Mesaj geçmişi fetch limiti: {policy['conversation_fetch_limit']}",
                f"- Aktif pencere mesaj sayısı: {policy['conversation_window_messages']}",
                f"- Mesaj başı excerpt limiti: {policy['conversation_message_excerpt_chars']}",
                f"- Konuşma char bütçesi: {policy['conversation_window_char_budget']}",
                f"- Daha eski özet limiti: {policy['older_summary_limit']}",
                f"- Harici bağlam limiti: {policy['external_context_limit']}",
                "",
                "## Cache Notu",
                "- Statik sistem bağlamı ile dinamik oturum kuyruğu ayrı tutulur.",
                "- Uzun geçmiş tam basılmaz; kısa özet + son pencere yaklaşımı kullanılır.",
                "",
                "## Süreklilik Disiplini",
                "- Kalıcı kişilik ve kullanıcı tercihleri USER/IDENTITY/SOUL katmanında yaşar.",
                "- Oturumluk operasyon durumu MEMORY/PROGRESS ve günlük loglarda tutulur.",
                "- Yeni bir adım planlanırken önce bu ayrım korunur, sonra araç kullanılır.",
                "",
            ]
        )
        return "\n".join(lines)

    def _build_heartbeat_md(self, profile: dict[str, Any], runtime_profile: dict[str, Any]) -> str:
        extra_checks = runtime_profile.get("heartbeat_extra_checks") or []
        lines = [
            "# HEARTBEAT.md",
            "",
            "- Önce CONTEXT.md, MEMORY.md ve PROGRESS.md dosyalarını oku.",
            "- Yaklaşan önemli tarihleri kontrol et.",
            "- Onay bekleyen taslakları kontrol et.",
            "- Yaklaşan ajanda kayıtlarını ve hazırlık ihtiyacını kontrol et.",
            "- Son konuşma penceresinde kalıcı profile yazılması gereken bir sinyal var mı bak.",
        ]
        if profile.get("assistant_notes"):
            lines.append("- Kullanıcı notlarında belirtilen özel hazırlık ihtiyaçlarını kontrol et.")
        for item in extra_checks[:10]:
            value = str(item or "").strip()
            if value:
                lines.append(f"- {value}")
        lines.append("")
        return "\n".join(lines)

    def _build_bootstrap_md(self, profile: dict[str, Any], runtime_profile: dict[str, Any]) -> str:
        missing: list[str] = []
        if not str(runtime_profile.get("assistant_name") or "").strip():
            missing.append("- Ayarlar ekranından asistan adı girilmedi.")
        if not str(profile.get("display_name") or "").strip() and not str(profile.get("assistant_notes") or "").strip():
            missing.append("- Kişisel profil içinde en az bir hitap veya serbest profil notu girilmedi.")
        return "\n".join(
            [
                "# BOOTSTRAP.md",
                "",
                "Bu çalışma alanı ilk kez hazırlanıyor. LawCopilot içindeki rehberli Ayarlar ekranından temel kimlik bilgilerini tamamla.",
                "",
                "Eksikler:",
                *(missing or ["- Temel profil eksik değil."]),
                "",
                "Tamamlanınca bu dosya otomatik kaldırılır.",
                "",
            ]
        )

    def _build_memory_md(
        self,
        *,
        workspace_root: dict[str, Any] | None,
        home: dict[str, Any],
        agenda: list[dict[str, Any]],
        inbox: list[dict[str, Any]],
        calendar: list[dict[str, Any]],
        connected_accounts: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        drafts: list[dict[str, Any]],
    ) -> str:
        lines = [
            "# MEMORY.md",
            "",
            f"- Son senkron: {self._now()}",
            f"- Çalışma alanı: {workspace_root.get('display_name') if workspace_root else 'Belirtilmedi'}",
            f"- Gün özeti: {home.get('today_summary') or 'Özet yok.'}",
            "- Bellek modu: statik kimlik + dinamik operasyon ayrımı",
            "",
            "## Sayaçlar",
            f"- Ajanda maddesi: {len(agenda)}",
            f"- Yanıt bekleyen iletişim: {len(inbox)}",
            f"- Takvim girdisi: {len(calendar)}",
            f"- Onay bekleyen taslak: {len([item for item in drafts if item.get('approval_status') != 'approved'])}",
            "",
            "## Bağlı Hesaplar",
        ]
        if connected_accounts:
            for item in connected_accounts:
                lines.append(f"- {item.get('provider')}: {item.get('status')}")
        else:
            lines.append("- Bağlı hesap yok.")
        lines.extend(["", "## Son Asistan Akışı"])
        if messages:
            for item in messages[-4:]:
                lines.append(f"- {item.get('role')}: {self._compact_text(item.get('content') or '')}")
        else:
            lines.append("- Henüz mesaj kaydı yok.")
        lines.extend(
            [
                "",
                "## Hafıza Disiplini",
                "- Kalıcı tercih değişimi USER.md / IDENTITY.md yönüne gider.",
                "- Güncel iş yükü ve takip bilgisi PROGRESS.md / günlük log katmanında tutulur.",
            ]
        )
        lines.append("")
        return "\n".join(lines)

    def _build_progress_md(
        self,
        *,
        home: dict[str, Any],
        agenda: list[dict[str, Any]],
        inbox: list[dict[str, Any]],
        calendar: list[dict[str, Any]],
        drafts: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        recent_events: list[dict[str, Any]],
    ) -> str:
        pending_drafts = [item for item in drafts if str(item.get("approval_status") or "") != "approved"]
        priority_items = list(home.get("priority_items") or [])
        lines = [
            "# PROGRESS.md",
            "",
            f"- Son senkron: {self._now()}",
            f"- Gün özeti: {home.get('today_summary') or 'Özet yok.'}",
            "",
            "## Sonraki En İyi Adım",
            (
                f"- {(priority_items[0].get('title') or 'Net bir sonraki adım görünmüyor.')}"
                if priority_items
                else "- Net bir sonraki adım görünmüyor."
            ),
            "",
            "## Aktif Öncelikler",
        ]
        if priority_items:
            for item in priority_items[:6]:
                title = item.get("title") or "Öncelik"
                details = item.get("details") or ""
                lines.append(f"- {title}" + (f" | {self._compact_text(details, max_len=140)}" if details else ""))
        else:
            lines.append("- Belirgin öncelik görünmüyor.")
        lines.extend(["", "## Operasyon Sayaçları"])
        lines.extend(
            [
                f"- Ajanda: {len(agenda)}",
                f"- İletişim: {len(inbox)}",
                f"- Takvim: {len(calendar)}",
                f"- Onay / taslak: {len(pending_drafts)}",
            ]
        )
        lines.extend(["", "## Bekleyen Taslaklar"])
        if pending_drafts:
            for item in pending_drafts[:6]:
                label = item.get("title") or item.get("subject") or item.get("draft_type") or "Taslak"
                channel = item.get("channel") or "assistant"
                status = item.get("approval_status") or "pending_review"
                lines.append(f"- {label} | kanal={channel} | onay={status}")
        else:
            lines.append("- Bekleyen taslak yok.")
        lines.extend(["", "## Yaklaşan Takvim"])
        if calendar:
            for item in calendar[:5]:
                title = item.get("title") or "Takvim kaydı"
                starts_at = item.get("starts_at") or item.get("start_at") or item.get("date") or "Tarih yok"
                lines.append(f"- {title} | {starts_at}")
        else:
            lines.append("- Yaklaşan takvim kaydı yok.")
        lines.extend(["", "## Son Konuşma"])
        if messages:
            for item in messages[-4:]:
                lines.append(f"- {item.get('role')}: {self._compact_text(item.get('content') or '', max_len=180)}")
        else:
            lines.append("- Konuşma kaydı yok.")
        lines.extend(["", "## Son Runtime Olayları"])
        if recent_events:
            for event in recent_events[:6]:
                lines.append(f"- {self._sanitize_event(event)}")
        else:
            lines.append("- Runtime olayı yok.")
        lines.append("")
        return "\n".join(lines)

    def _build_daily_log_md(
        self,
        *,
        workspace_root: dict[str, Any] | None,
        home: dict[str, Any],
        agenda: list[dict[str, Any]],
        connected_accounts: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        recent_events: list[dict[str, Any]],
        profile: dict[str, Any],
        runtime_profile: dict[str, Any],
        drafts: list[dict[str, Any]],
    ) -> str:
        lines = [
            f"# {date.today().isoformat()}",
            "",
            f"- Senkron zamanı: {self._now()}",
            f"- Çalışma alanı: {workspace_root.get('display_name') if workspace_root else 'Belirtilmedi'}",
            f"- Kullanıcı hitabı: {profile.get('display_name') or 'Belirtilmedi'}",
            f"- Asistan adı: {runtime_profile.get('assistant_name') or 'Belirtilmedi'}",
            f"- Gün özeti: {home.get('today_summary') or 'Özet yok.'}",
            f"- Ajanda sayısı: {len(agenda)}",
            f"- Onay bekleyen taslak sayısı: {len([item for item in drafts if item.get('approval_status') != 'approved'])}",
            "",
            "## Bağlı Hesaplar",
        ]
        if connected_accounts:
            for item in connected_accounts:
                lines.append(f"- {item.get('provider')}: {item.get('status')}")
        else:
            lines.append("- Bağlı hesap yok.")
        lines.extend(["", "## Son Mesajlar"])
        if messages:
            for item in messages[-5:]:
                lines.append(f"- {item.get('role')}: {self._compact_text(item.get('content') or '')}")
        else:
            lines.append("- Henüz mesaj yok.")
        lines.extend(["", "## Son Olaylar"])
        if recent_events:
            for event in recent_events[:8]:
                lines.append(f"- {self._sanitize_event(event)}")
        else:
            lines.append("- Kayıtlı olay yok.")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _compact_text(value: str, max_len: int = 160) -> str:
        compact = " ".join(str(value or "").split())
        return compact[:max_len]

    def _sanitize_event(self, event: dict[str, Any]) -> str:
        redacted_keys = {"token", "secret", "authorization", "api_key", "access", "refresh"}
        pieces = [str(event.get("event") or event.get("type") or "olay")]
        for key in ("task", "provider", "model", "subject", "error", "message"):
            value = event.get(key)
            if value is None:
                continue
            if any(part in key.lower() for part in redacted_keys):
                continue
            text = self._compact_text(str(value), max_len=100)
            if any(word in text.lower() for word in redacted_keys):
                continue
            pieces.append(f"{key}={text}")
        return " | ".join(pieces)

    def _latest_daily_log_path(self, workspace_dir: Path) -> Path:
        return workspace_dir / "memory" / "daily-logs" / f"{date.today().isoformat()}.md"
