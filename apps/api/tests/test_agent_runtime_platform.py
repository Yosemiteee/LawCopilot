from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lawcopilot_api.agent_runtime import AgentRuntimeService
from lawcopilot_api.audit import AuditLogger
from lawcopilot_api.browser_client import BrowserWorkerClient
from lawcopilot_api.memory import MemoryService
from lawcopilot_api.persistence import Persistence
from lawcopilot_api.rag import build_persisted_chunks
from lawcopilot_api.tools import create_tool_registry
from lawcopilot_api.videointel import analyze_video_url
from lawcopilot_api.webintel import WebIntelService, extract_web_intelligence


class DummyEvents:
    def log(self, *_args, **_kwargs) -> None:
        return None


def _settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        office_id="default-office",
        browser_worker_enabled=False,
        browser_worker_command="",
        browser_profile_dir=str(tmp_path / "browser-profile"),
        browser_artifacts_dir=str(tmp_path / "browser-artifacts"),
        browser_allowed_domains=(),
        browser_worker_timeout_seconds=15,
    )


def test_agent_runtime_create_run_returns_flat_view_with_citations(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = Persistence(tmp_path / "agent-runtime.db")
    matter = store.create_matter(
        settings.office_id,
        title="Tahliye Davası",
        reference_code="2026/15",
        practice_area="kira",
        status="active",
        summary="Kiralananın tahliyesi dosyası",
        client_name="Örnek Müvekkil",
        lead_lawyer="Sami",
        opened_at="2026-04-01T09:00:00+00:00",
        created_by="tester",
    )
    document = store.create_document(
        settings.office_id,
        int(matter["id"]),
        filename="tahliye-dilekcesi.md",
        display_name="Tahliye Dilekçesi",
        content_type="text/markdown",
        source_type="upload",
        source_ref=None,
        checksum="checksum-1",
        size_bytes=256,
    )
    assert document is not None
    chunks = build_persisted_chunks(
        office_id=settings.office_id,
        matter_id=int(matter["id"]),
        document_id=int(document["id"]),
        document_name="Tahliye Dilekçesi",
        source_type="upload",
        text=(
            "Kiralananın tahliyesi ve birikmiş kira alacağı hakkında ayrıntılı talep sunulmuştur. "
            "Davacı, tahliye kararının kira borcunun ödenmemesi nedeniyle verilmesini istemektedir."
        ),
    )
    store.replace_document_chunks(settings.office_id, int(matter["id"]), int(document["id"]), chunks)
    store.update_document_status(settings.office_id, int(document["id"]), "indexed")

    events = DummyEvents()
    runtime = AgentRuntimeService(
        settings=settings,
        store=store,
        events=events,
        audit=AuditLogger(tmp_path / "audit.log"),
        tool_registry=create_tool_registry(settings=settings, store=store, events=events, web_intel=WebIntelService()),
        memory_service=MemoryService(store, settings.office_id),
    )

    run = runtime.create_run(
        goal="Tahliye ve kira alacağı dayanaklarını bul.",
        created_by="tester",
        matter_id=int(matter["id"]),
        preferred_tools=["matter.search"],
    )

    assert int(run["id"]) > 0
    assert run["status"] == "completed"
    assert "Görev işlendi" in str(run["summary"])
    assert "Görev işlendi" in str(run["final_output"])
    assert run["support_level"] in {"medium", "high"}
    assert run["confidence"] in {"medium", "high"}
    assert run["execution_posture"] in {"suggest", "auto"}
    assert str(run["review_summary"] or "").strip()
    assert run["tool_invocations"][0]["tool_name"] == "matter.search"
    assert run["citations"]
    assert run["steps"]
    assert any(str(step.get("role") or "") == "critic" for step in run["steps"])
    assert runtime.get_run_events(int(run["id"]))


def test_agent_runtime_marks_pending_approval_runs_with_low_confidence(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = Persistence(tmp_path / "agent-runtime-approval.db")
    events = DummyEvents()
    tool_registry = create_tool_registry(settings=settings, store=store, events=events, web_intel=WebIntelService())
    web_search = tool_registry.get("web.search")
    assert web_search is not None
    tool_registry._specs["web.search"] = replace(web_search, approval_policy="explicit", risk_level="medium")

    runtime = AgentRuntimeService(
        settings=settings,
        store=store,
        events=events,
        audit=AuditLogger(tmp_path / "audit-approval.log"),
        tool_registry=tool_registry,
        memory_service=MemoryService(store, settings.office_id),
    )

    run = runtime.create_run(
        goal="Güncel web sonuçlarını tara ve özetle.",
        created_by="tester",
        preferred_tools=["web.search"],
    )

    assert run["status"] == "awaiting_approval"
    assert run["support_level"] == "low"
    assert run["confidence"] == "low"
    assert run["execution_posture"] == "ask"
    assert "İnsan onayı" in str(run["review_summary"])
    assert run["approval_requests"]
    assert "onay" in str(run["approval_requests"][0]["reason"]).lower()
    assert any(str(step.get("role") or "") == "critic" for step in run["steps"])


def test_agent_runtime_approve_run_executes_pending_tools(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = Persistence(tmp_path / "agent-runtime-approve.db")
    events = DummyEvents()
    tool_registry = create_tool_registry(settings=settings, store=store, events=events, web_intel=WebIntelService())
    web_search = tool_registry.get("web.search")
    assert web_search is not None
    tool_registry._specs["web.search"] = replace(web_search, approval_policy="explicit", risk_level="medium")
    monkeypatch.setattr(
        "lawcopilot_api.connectors.web_search.search_web",
        lambda query, *, limit=5: [
            {
                "title": "Kira Hukuku Güncellemesi",
                "url": f"https://example.com/search?q={query}",
                "snippet": "Tahliye ve kira alacağı üzerine kısa güncel not.",
                "source": "test",
            }
        ][:limit],
    )

    runtime = AgentRuntimeService(
        settings=settings,
        store=store,
        events=events,
        audit=AuditLogger(tmp_path / "audit-approve.log"),
        tool_registry=tool_registry,
        memory_service=MemoryService(store, settings.office_id),
    )

    run = runtime.create_run(
        goal="Güncel web sonuçlarını tara ve özetle.",
        created_by="tester",
        preferred_tools=["web.search"],
    )
    assert run["status"] == "awaiting_approval"
    assert run["tool_invocations"][0]["status"] == "pending_approval"

    approved = runtime.approve_run(int(run["id"]), decided_by="reviewer")

    assert approved is not None
    assert approved["status"] == "completed"
    assert approved["tool_invocations"][0]["status"] == "completed"
    assert approved["approval_requests"][0]["status"] == "approved"
    assert approved["citations"]
    assert "1 kaynaklı dayanak bulundu" in str(approved["final_output"])
    assert any(str(step.get("title") or "") == "Onay sonrası çıktı değerlendirildi" for step in approved["steps"])


def test_agent_runtime_travel_query_uses_travel_search_tool(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = Persistence(tmp_path / "agent-runtime-travel.db")
    store.upsert_user_profile(
        settings.office_id,
        display_name="Sami",
        travel_preferences="Tren ve pencere kenarı koltuk sever.",
        important_dates=[],
        related_profiles=[],
    )
    events = DummyEvents()
    monkeypatch.setattr(
        "lawcopilot_api.connectors.web_search.search_web",
        lambda query, *, limit=5: [
            {
                "title": "İstanbul - Ankara hızlı tren",
                "url": f"https://example.com/train?q={query}",
                "snippet": "08:45 çıkış, 12:30 varış, esnek bilet.",
                "source": "test",
            }
        ][:limit],
    )
    runtime = AgentRuntimeService(
        settings=settings,
        store=store,
        events=events,
        audit=AuditLogger(tmp_path / "audit-travel.log"),
        tool_registry=create_tool_registry(settings=settings, store=store, events=events, web_intel=WebIntelService()),
        memory_service=MemoryService(store, settings.office_id),
    )

    run = runtime.create_run(
        goal="18 Mart için Ankara'ya tren bileti bak.",
        created_by="tester",
    )

    assert run["status"] == "completed"
    assert any(item["tool_name"] == "travel.search" for item in run["tool_invocations"])
    assert run["citations"]
    assert "1 kaynaklı dayanak bulundu" in str(run["final_output"])


def test_agent_runtime_youtube_query_uses_youtube_search_tool(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = Persistence(tmp_path / "agent-runtime-youtube.db")
    events = DummyEvents()
    monkeypatch.setattr(
        "lawcopilot_api.connectors.web_search.search_web",
        lambda query, *, limit=5: [
            {
                "title": "Kira Hukuku 2026 Güncel Değerlendirme",
                "url": "https://www.youtube.com/watch?v=demo123",
                "snippet": "Tahliye ve kira artışı kararlarına dair kısa video.",
                "source": "test",
            }
        ][:limit],
    )
    runtime = AgentRuntimeService(
        settings=settings,
        store=store,
        events=events,
        audit=AuditLogger(tmp_path / "audit-youtube.log"),
        tool_registry=create_tool_registry(settings=settings, store=store, events=events, web_intel=WebIntelService()),
        memory_service=MemoryService(store, settings.office_id),
    )

    run = runtime.create_run(
        goal="YouTube'da kira hukuku videolarını ara.",
        created_by="tester",
    )

    assert run["status"] == "completed"
    assert any(item["tool_name"] == "youtube.search" for item in run["tool_invocations"])
    assert run["citations"]


def test_agent_runtime_video_summary_uses_video_analyze_tool(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = Persistence(tmp_path / "agent-runtime-video.db")
    events = DummyEvents()
    monkeypatch.setattr(
        "lawcopilot_api.tools.registry.analyze_video_url",
        lambda url, transcript_text=None, max_segments=24: {
            "url": url,
            "video_id": "demo123",
            "transcript_source": "provided",
            "transcript_available": True,
            "transcript": "Kısa transcript.",
            "segments": [
                {"segment_index": 1, "excerpt": "Kira artışı kararları anlatılıyor.", "text": "Kira artışı kararları anlatılıyor."},
            ],
            "summary": "Video transkriptinden özet çıkarıldı.",
            "citations": [
                {"label": "[1]", "excerpt": "Kira artışı kararları anlatılıyor.", "source_type": "video_transcript"}
            ],
        },
    )
    runtime = AgentRuntimeService(
        settings=settings,
        store=store,
        events=events,
        audit=AuditLogger(tmp_path / "audit-video.log"),
        tool_registry=create_tool_registry(settings=settings, store=store, events=events, web_intel=WebIntelService()),
        memory_service=MemoryService(store, settings.office_id),
    )

    run = runtime.create_run(
        goal="https://youtu.be/demo123 videosunu özetle.",
        created_by="tester",
    )

    assert run["status"] == "completed"
    assert any(item["tool_name"] == "video.analyze" for item in run["tool_invocations"])
    assert run["citations"]


def test_agent_runtime_profile_dates_tool_reads_upcoming_dates(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = Persistence(tmp_path / "agent-runtime-profile-dates.db")
    target_date = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
    store.upsert_user_profile(
        settings.office_id,
        display_name="Sami",
        important_dates=[
            {
                "label": "Ayşe doğum günü",
                "date": target_date,
                "notes": "Kısa kutlama mesajı hazırlansın.",
                "recurring_annually": True,
            }
        ],
        related_profiles=[],
    )
    events = DummyEvents()
    runtime = AgentRuntimeService(
        settings=settings,
        store=store,
        events=events,
        audit=AuditLogger(tmp_path / "audit-profile-dates.log"),
        tool_registry=create_tool_registry(settings=settings, store=store, events=events, web_intel=WebIntelService()),
        memory_service=MemoryService(store, settings.office_id),
    )

    run = runtime.create_run(
        goal="Ayşe'nin yaklaşan doğum gününe göre hazırlık çıkar.",
        created_by="tester",
        preferred_tools=["assistant.profile_dates"],
    )

    assert run["status"] == "completed"
    assert run["tool_invocations"][0]["tool_name"] == "assistant.profile_dates"
    outputs = run["result_payload"]["tool_outputs"]
    profile_dates_output = next(item for item in outputs if item["tool"] == "assistant.profile_dates")
    assert profile_dates_output["output"]["items"]
    assert profile_dates_output["output"]["items"][0]["title"] == "Ayşe doğum günü"


def test_agent_runtime_weather_query_uses_weather_search_tool(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = Persistence(tmp_path / "agent-runtime-weather.db")
    store.upsert_user_profile(
        settings.office_id,
        display_name="Sami",
        weather_preference="Serin ve yağmursuz hava sever.",
        important_dates=[],
        related_profiles=[],
    )
    events = DummyEvents()
    monkeypatch.setattr(
        "lawcopilot_api.connectors.web_search.search_web",
        lambda query, *, limit=5: [
            {
                "title": "İstanbul hava durumu",
                "url": f"https://example.com/weather?q={query}",
                "snippet": "Bugün 17C, hafif rüzgarlı ve parçalı bulutlu.",
                "source": "test",
            }
        ][:limit],
    )
    runtime = AgentRuntimeService(
        settings=settings,
        store=store,
        events=events,
        audit=AuditLogger(tmp_path / "audit-weather.log"),
        tool_registry=create_tool_registry(settings=settings, store=store, events=events, web_intel=WebIntelService()),
        memory_service=MemoryService(store, settings.office_id),
    )

    run = runtime.create_run(
        goal="Bugün İstanbul'da hava durumu nasıl?",
        created_by="tester",
    )

    assert run["status"] == "completed"
    assert any(item["tool_name"] == "weather.search" for item in run["tool_invocations"])
    assert run["citations"]


def test_agent_runtime_semantic_plan_can_select_weather_tool(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = Persistence(tmp_path / "agent-runtime-semantic-weather.db")
    events = DummyEvents()
    monkeypatch.setattr(
        "lawcopilot_api.connectors.web_search.search_web",
        lambda query, *, limit=5: [
            {
                "title": "İstanbul akşam hava durumu",
                "url": f"https://example.com/weather?q={query}",
                "snippet": "Akşam 11C, hafif rüzgarlı.",
                "source": "test",
            }
        ][:limit],
    )

    class FakeSemanticRuntime:
        def complete(self, prompt, events, *, task, **meta):
            assert task == "agent_runtime_tool_plan"
            return {
                "text": json.dumps(
                    {
                        "primary_tool": "weather.search",
                        "supplemental_tools": [],
                        "confidence": "high",
                        "reason": "Kullanıcı hava durumuna göre hazırlık yapmak istiyor.",
                    }
                ),
                "provider": "intent-planner",
                "model": "planner-mini",
            }

    runtime = AgentRuntimeService(
        settings=settings,
        store=store,
        events=events,
        audit=AuditLogger(tmp_path / "audit-semantic-weather.log"),
        tool_registry=create_tool_registry(settings=settings, store=store, events=events, web_intel=WebIntelService()),
        memory_service=MemoryService(store, settings.office_id),
        semantic_runtime=FakeSemanticRuntime(),
    )

    run = runtime.create_run(
        goal="Akşama İstanbul'da mont gerekir mi?",
        created_by="tester",
    )

    assert run["status"] == "completed"
    assert any(item["tool_name"] == "weather.search" for item in run["tool_invocations"])
    assert run["citations"]


def test_agent_runtime_places_query_uses_places_search_tool(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = Persistence(tmp_path / "agent-runtime-places.db")
    store.upsert_user_profile(
        settings.office_id,
        display_name="Sami",
        food_preferences="Üçüncü nesil kahveci ve sakin mekân sever.",
        transport_preference="Kısa yürüyüş mesafesi tercih eder.",
        important_dates=[],
        related_profiles=[],
    )
    events = DummyEvents()
    monkeypatch.setattr(
        "lawcopilot_api.connectors.web_search.search_web",
        lambda query, *, limit=5: [
            {
                "title": "Moda üçüncü nesil kahveciler",
                "url": f"https://example.com/places?q={query}",
                "snippet": "Sessiz çalışma alanı ve filtre kahve seçenekleri.",
                "source": "test",
            }
        ][:limit],
    )
    runtime = AgentRuntimeService(
        settings=settings,
        store=store,
        events=events,
        audit=AuditLogger(tmp_path / "audit-places.log"),
        tool_registry=create_tool_registry(settings=settings, store=store, events=events, web_intel=WebIntelService()),
        memory_service=MemoryService(store, settings.office_id),
    )

    run = runtime.create_run(
        goal="Moda'da yakındaki iyi bir kahveci bul.",
        created_by="tester",
    )

    assert run["status"] == "completed"
    assert any(item["tool_name"] == "places.search" for item in run["tool_invocations"])
    assert run["citations"]


def test_tool_registry_search_tools_persist_learning_signals(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = Persistence(tmp_path / "agent-runtime-learning.db")
    tool_registry = create_tool_registry(settings=settings, store=store, events=DummyEvents(), web_intel=WebIntelService())

    monkeypatch.setattr(
        "lawcopilot_api.tools.registry.build_weather_context",
        lambda query, profile_note=None, limit=5: {
            "summary": "Kadıköy akşam yağmurlu.",
            "results": [
                {
                    "title": "Kadıköy akşam hava durumu",
                    "snippet": "12C ve yağmurlu.",
                    "url": "https://example.test/weather",
                }
            ],
        },
    )
    monkeypatch.setattr(
        "lawcopilot_api.tools.registry.build_places_context",
        lambda query, profile_note=None, transport_note=None, limit=5: {
            "summary": "Moda'da sakin kahveci bulundu.",
            "results": [
                {
                    "title": "Moda Roast Club",
                    "snippet": "Sessiz çalışma alanı.",
                    "url": "https://example.test/place",
                }
            ],
            "map_url": "https://example.test/maps",
        },
    )

    weather_payload = tool_registry.execute("weather.search", {"query": "Kadıköy hava durumu"})
    places_payload = tool_registry.execute("places.search", {"query": "Moda'da sakin kahveci bul"})
    external_events = store.list_external_events(settings.office_id, limit=10)
    providers = {(str(item.get("provider") or ""), str(item.get("event_type") or "")) for item in external_events}

    assert weather_payload["summary"] == "Kadıköy akşam yağmurlu."
    assert places_payload["summary"] == "Moda'da sakin kahveci bulundu."
    assert ("weather", "weather_search") in providers
    assert ("places", "places_search") in providers


def test_agent_runtime_lists_recent_runs_with_flattened_fields(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = Persistence(tmp_path / "agent-runtime-list.db")
    events = DummyEvents()
    runtime = AgentRuntimeService(
        settings=settings,
        store=store,
        events=events,
        audit=AuditLogger(tmp_path / "audit-list.log"),
        tool_registry=create_tool_registry(settings=settings, store=store, events=events, web_intel=WebIntelService()),
        memory_service=MemoryService(store, settings.office_id),
    )

    first = runtime.create_run(goal="Bugünkü çalışma planını çıkar.", created_by="tester")
    second = runtime.create_run(goal="Takvim ve taslak durumunu özetle.", created_by="tester")

    runs = runtime.list_run_views(limit=5)

    assert len(runs) >= 2
    assert int(runs[0]["id"]) == int(second["id"])
    assert int(runs[1]["id"]) == int(first["id"])
    assert runs[0]["summary"]
    assert runs[0]["result_status"] in {"completed", "awaiting_approval"}
    assert isinstance(runs[0]["steps"], list)


def test_extract_web_intelligence_reads_public_html(monkeypatch: pytest.MonkeyPatch) -> None:
    html_text = """
    <html>
      <head>
        <title>LawCopilot Test Site</title>
        <meta name="description" content="Örnek test sayfası" />
      </head>
      <body>
        <h1>Ana Başlık</h1>
        <p>İletişim için <a href="mailto:info@example.com">info@example.com</a> ve <a href="tel:+905550001122">+90 555 000 11 22</a>.</p>
        <a href="https://x.com/lawcopilot">X</a>
      </body>
    </html>
    """

    class _FakeResponse:
        def __init__(self) -> None:
            self.url = "https://example.com/test"
            self.headers = {"Content-Type": "text/html; charset=utf-8"}

        def read(self, _limit: int) -> bytes:
            return html_text.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr("lawcopilot_api.webintel.service.urlopen", lambda *_args, **_kwargs: _FakeResponse())

    result = extract_web_intelligence("https://example.com/test", render_mode="cheap")

    assert result["reachable"] is True
    assert result["title"] == "LawCopilot Test Site"
    assert "Ana Başlık" in result["headings"]
    assert "e-posta" in result["contact_hints"]
    assert result["social_links"] == ["https://x.com/lawcopilot"]


def test_extract_web_intelligence_blocks_local_file_scheme() -> None:
    result = extract_web_intelligence("file:///tmp/secret.txt", render_mode="cheap")

    assert result["reachable"] is False
    assert "unsupported_scheme" in result["issues"]


def test_web_intel_skips_browser_when_render_mode_is_cheap() -> None:
    browser_client = Mock()
    browser_client.extract.return_value = {"ok": True, "payload": {"summary": "browser"}}
    service = WebIntelService(browser_client=browser_client)

    result = service.extract(url="https://example.com", render_mode="cheap", include_screenshot=False)

    assert result["render_mode"] == "cheap"
    browser_client.extract.assert_not_called()


def test_analyze_video_url_uses_transcript_text_segments() -> None:
    transcript = (
        "Bu video kira sözleşmesinin feshi ve tahliye sürecini anlatıyor. "
        "İlk bölümde borcun temerrüde düşmesi, ikinci bölümde icra ve dava stratejisi açıklanıyor. "
        "Son bölümde delil toplama ve zaman çizelgesi özetleniyor."
    )

    result = analyze_video_url("https://www.youtube.com/watch?v=demo123", transcript_text=transcript, max_segments=6)

    assert result["transcript_available"] is True
    assert result["transcript_source"] == "provided"
    assert result["segments"]
    assert result["citations"][0]["source_type"] == "video_transcript"


@pytest.mark.skipif(shutil.which("node") is None, reason="node binary not available")
def test_browser_worker_client_normalizes_extract_response(tmp_path: Path) -> None:
    extract_artifact = tmp_path / "extract.json"
    screenshot_artifact = tmp_path / "page.png"
    extract_artifact.write_text("{}", encoding="utf-8")
    screenshot_artifact.write_bytes(b"png")

    worker_script = tmp_path / "fake-browser-worker.js"
    worker_script.write_text(
        f"""
        const chunks = [];
        process.stdin.on("data", (chunk) => chunks.push(chunk));
        process.stdin.on("end", () => {{
          const payload = {{
            ok: true,
            results: [
              {{
                action: "extract",
                ok: true,
                url: "https://example.com",
                data: {{
                  title: "Example Domain",
                  url: "https://example.com",
                  text: "Contact us at info@example.com or +90 555 111 22 33",
                  links: [{{ text: "X", href: "https://x.com/example" }}]
                }},
                artifactPaths: [{extract_artifact.as_posix()!r}]
              }},
              {{
                action: "screenshot",
                ok: true,
                url: "https://example.com",
                artifactPaths: [{screenshot_artifact.as_posix()!r}]
              }}
            ],
            warnings: []
          }};
          process.stdout.write(JSON.stringify(payload));
        }});
        """,
        encoding="utf-8",
    )

    client = BrowserWorkerClient(
        enabled=True,
        command=f"node {worker_script}",
        profile_dir=str(tmp_path / "profile"),
        artifacts_dir=str(tmp_path / "artifacts"),
        downloads_dir=str(tmp_path / "downloads"),
        timeout_seconds=10,
    )

    result = client.extract("https://example.com", include_screenshot=True, preferred_mode="browser")

    assert result["ok"] is True
    assert result["payload"]["title"] == "Example Domain"
    assert "e-posta" in result["payload"]["contact_hints"]
    assert result["payload"]["social_links"] == ["https://x.com/example"]
    assert len(result["payload"]["artifacts"]) == 2
