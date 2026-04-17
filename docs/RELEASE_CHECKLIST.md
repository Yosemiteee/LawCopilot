# Release Checklist (0.7.0-pilot.2)

## Build & Quality
- [ ] `scripts/check.sh` çalıştırıldı ve geçti
- [ ] `scripts/run_eval_suite.sh` çalıştırıldı ve geçti
- [ ] API unit/integration testleri geçti
- [ ] UI smoke testleri geçti
- [ ] Desktop smoke testi geçti
- [ ] `scripts/pilot_diagnostics.sh` geçti
- [ ] Desktop `package:dir` çıktısı üretildi
- [ ] `apps/api/tests/test_knowledge_base.py` geçti
- [ ] `apps/api/tests/test_integrations_platform.py` geçti
- [ ] `apps/api/tests/test_assistant_integration_chat.py` geçti
- [ ] `apps/api/tests/test_launch_stability.py` geçti
- [ ] `apps/ui/src/pages/AssistantOperationalSurface.test.tsx` geçti
- [ ] `apps/ui/src/pages/IntegrationsPage.test.tsx` geçti
- [ ] UI `npm run build` geçti
- [ ] `node --check apps/desktop/main.cjs` geçti
- [ ] `node --check apps/desktop/scripts/packaged-runtime-smoke.cjs` geçti
- [ ] Packaged runtime smoke script gerçek artifact üstünde geçti

## Security
- [ ] `LAWCOPILOT_JWT_SECRET` production secret ile set edildi
- [ ] `LAWCOPILOT_BOOTSTRAP_ADMIN_KEY` configured
- [ ] Connector allowlist doğrulandı
- [ ] Connector prompt-injection blocking doğrulandı
- [ ] Integration secret rotation key id / previous keys doğrulandı
- [ ] Audit log path ve izinleri (0600) doğrulandı
- [ ] Structured event log doğrulandı
- [ ] `LAWCOPILOT_ALLOW_HEADER_AUTH=false` kaldı
- [ ] `LAWCOPILOT_CONNECTOR_DRY_RUN=true` varsayilanı korundu
- [ ] `GET /integrations/ops/summary` rollout posture uyarıları kontrol edildi
- [ ] `GET /integrations/ops/summary` içinde `default_jwt_secret` ve `local_secret_posture` uyarısı kalmadı
- [ ] Location permission-denied / privacy-mode fallback davranışı doğrulandı
- [ ] Silent irreversible action olmadığı tekrar doğrulandı
- [ ] Multi-tenant office isolation smoke doğrulandı
- [ ] Staging veya release-aday ortamında gerçek OAuth smoke koşuldu
  - [ ] Google
  - [ ] Slack
  - [ ] Notion
- [ ] Gerçek provider webhook delivery bir kez doğrulandı
- [ ] Packaged runtime içinde `assistant/inbox` ve `assistant/calendar` canlı provider verisiyle smoke doğrulandı

## Distribution
- [ ] `scripts/pilot_local.sh` ile local pilot bootstrap doğrulandı
- [ ] `deployment/installer/bootstrap.sh` ve `bootstrap.ps1` LawCopilot-first akışa hizalandı
- [ ] Kurulum adımları ve rollback adımları doğrulandı
- [ ] Customer-facing akışlarda OpenClaw komutu kalmadı

## UX & Docs
- [ ] docs/SECURITY.md ve docs/ARCHITECTURE.md güncel
- [ ] docs/BOUNDARY_DECISIONS.md kod gerçekliğiyle hizalı
- [ ] docs/PILOT_INSTALL_GUIDE.md güncel
- [ ] docs/PILOT_OBSERVABILITY.md güncel
- [ ] CHANGELOG güncel
- [ ] docs/LAUNCH_READINESS.md güncel
- [ ] docs/INTEGRATIONS_PLATFORM.md güncel
- [ ] Explainability drawer, memory correction ve operational cards manuel smoke ile gözden geçirildi
- [ ] Integrations `Rollout ve destek ozeti` kartı manuel smoke ile gözden geçirildi
- [ ] Dashboard `Pilot durumu` ve `Operasyon sinyalleri` kartları manuel smoke ile gözden geçirildi
