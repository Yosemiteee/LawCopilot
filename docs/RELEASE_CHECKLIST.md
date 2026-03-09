# Release Checklist (0.7.0-pilot.1)

## Build & Quality
- [ ] `scripts/check.sh` çalıştırıldı ve geçti
- [ ] API unit/integration testleri geçti
- [ ] UI smoke testleri geçti
- [ ] Desktop smoke testi geçti
- [ ] Desktop `package:dir` çıktısı üretildi

## Security
- [ ] `LAWCOPILOT_JWT_SECRET` production secret ile set edildi
- [ ] `LAWCOPILOT_BOOTSTRAP_ADMIN_KEY` configured
- [ ] Connector allowlist doğrulandı
- [ ] Connector prompt-injection blocking doğrulandı
- [ ] Audit log path ve izinleri (0600) doğrulandı
- [ ] Structured event log doğrulandı
- [ ] `LAWCOPILOT_ALLOW_HEADER_AUTH=false` kaldı
- [ ] `LAWCOPILOT_CONNECTOR_DRY_RUN=true` varsayilanı korundu

## Distribution
- [ ] `scripts/pilot_local.sh` ile local pilot bootstrap doğrulandı
- [ ] `deployment/installer/bootstrap.sh` ve `bootstrap.ps1` LawCopilot-first akışa hizalandı
- [ ] Kurulum adımları ve rollback adımları doğrulandı
- [ ] Customer-facing akışlarda OpenClaw komutu kalmadı

## UX & Docs
- [ ] docs/SECURITY.md ve docs/ARCHITECTURE.md güncel
- [ ] docs/BOUNDARY_DECISIONS.md kod gerçekliğiyle hizalı
- [ ] docs/PILOT_INSTALL_GUIDE.md güncel
- [ ] CHANGELOG güncel
