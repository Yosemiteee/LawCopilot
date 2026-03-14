from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import os
import shutil
from pathlib import Path
from typing import Any

from .assistant import build_assistant_agenda, build_assistant_calendar, build_assistant_home, build_assistant_inbox

CORE_FILES = (
    "AGENTS.md",
    "SOUL.md",
    "USER.md",
    "IDENTITY.md",
    "TOOLS.md",
    "HEARTBEAT.md",
    "MEMORY.md",
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

        files = {
            "AGENTS.md": self._build_agents_md(runtime_profile),
            "SOUL.md": self._build_soul_md(runtime_profile),
            "USER.md": self._build_user_md(profile),
            "IDENTITY.md": self._build_identity_md(runtime_profile),
            "TOOLS.md": self._build_tools_md(runtime_profile, workspace_root, connected_accounts, curated_skills),
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
                "files": [],
                "daily_log_path": None,
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
            "files": files,
            "daily_log_path": str(self._latest_daily_log_path(workspace_dir)),
        }

    def _workspace_dir(self) -> Path:
        return (self.state_dir or Path()) / "workspace"

    def _workspace_state_path(self) -> Path:
        return self._workspace_dir() / ".openclaw" / "workspace-state.json"

    def _load_state(self) -> dict[str, Any]:
        path = self._workspace_state_path()
        if not path.exists():
            return {"version": 2}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"version": 2}

    def _ensure_dirs(self, workspace_dir: Path) -> None:
        (workspace_dir / ".openclaw").mkdir(parents=True, exist_ok=True)
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
        assistant_ready = bool(str(runtime_profile.get("assistant_name") or "").strip())
        return not user_ready or not assistant_ready

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
        return all(path.exists() for path in required_paths)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _build_agents_md(self, runtime_profile: dict[str, Any]) -> str:
        role_summary = str(runtime_profile.get("role_summary") or "Kaynak dayanaklı hukuk çalışma asistanı").strip()
        tone = str(runtime_profile.get("tone") or "Net, profesyonel ve Türkçe").strip()
        return "\n".join(
            [
                "# LawCopilot Runtime",
                "",
                "Bu çalışma alanı LawCopilot tarafından yönetilir.",
                "",
                "Rolün:",
                role_summary,
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
                f"Ton: {tone}",
                "",
            ]
        )

    def _build_soul_md(self, runtime_profile: dict[str, Any]) -> str:
        extra = str(runtime_profile.get("soul_notes") or "").strip()
        lines = [
            "# SOUL.md",
            "",
            "## Çekirdek Davranış",
            "- Faydalı ol, gereksiz süsleme yapma.",
            "- Belirsizlik varsa açıkça söyle.",
            "- Kaynak dayanaklı çalış; tahmin ettiğinde bunu belirt.",
            "- Kullanıcının sesi gibi davranma; özellikle dış iletişim ve hassas hukuk dilinde temkinli ol.",
            "- Dış aksiyonlarda daima taslak + onay sınırını koru.",
            "",
            "## Ürün Duruşu",
            "- Müvekkil verisi ve ofis içeriği yerel bağlamdır; üçüncü taraflara sızdırma.",
            "- Açıkça istenmedikçe hukuki görüşü kesin hüküm gibi yazma.",
            "- Konuyu hızlandırmak için kısa, temiz ve profesyonel cevaplar ver.",
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
        return "\n".join(
            [
                "# IDENTITY.md",
                "",
                f"- Asistan adı: {runtime_profile.get('assistant_name') or 'Belirtilmedi'}",
                f"- Rol özeti: {runtime_profile.get('role_summary') or 'Kaynak dayanaklı hukuk çalışma asistanı'}",
                f"- Ton: {runtime_profile.get('tone') or 'Net ve profesyonel'}",
                f"- Avatar: {runtime_profile.get('avatar_path') or 'Belirtilmedi'}",
                "",
            ]
        )

    def _build_tools_md(
        self,
        runtime_profile: dict[str, Any],
        workspace_root: dict[str, Any] | None,
        connected_accounts: list[dict[str, Any]],
        curated_skills: list[dict[str, Any]],
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
        extra = str(runtime_profile.get("tools_notes") or "").strip()
        lines.extend(
            [
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

    def _build_heartbeat_md(self, profile: dict[str, Any], runtime_profile: dict[str, Any]) -> str:
        extra_checks = runtime_profile.get("heartbeat_extra_checks") or []
        lines = [
            "# HEARTBEAT.md",
            "",
            "- Yaklaşan önemli tarihleri kontrol et.",
            "- Onay bekleyen taslakları kontrol et.",
            "- Yaklaşan ajanda kayıtlarını ve hazırlık ihtiyacını kontrol et.",
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
