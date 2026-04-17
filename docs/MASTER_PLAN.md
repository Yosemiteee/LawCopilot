# LawCopilot Master Plan (Adaptive Assistant V1)

## 1) Product Scope
LawCopilot: yerel-oncelikli, kaynak dayanakli, uyarlanabilir genel amacli asistan.
- Workspace + knowledge memory
- Belge hafizasi ve kaynakli arama
- Draft-first iletisim ve is akislari
- Gorev, not, zaman cizelgesi ve etkinlik akislari
- Coklu model secimi (local / cloud / hybrid)

## 2) Distribution Model
- Windows-first Tauri shell
- Ilk acilis onboarding:
  1) Ofis bilgisi
  2) Model secimi: Local / Local-first Hybrid / Cloud-assisted
  3) Dosya ve connector izinleri
  4) Guvenlik ve saklama politikasi
- Runtime kullaniciya "OpenClaw" olarak sunulmaz; bundled internal runtime olarak ele alinir

## 3) MVP / V1 Core
- Assistant-first workbench UI
- Backend API + PostgreSQL + pgvector hedefi
- Ingestion jobs + parser/chunk/retrieval
- RBAC + office/user/workspace boundaries + audit
- Model router (local / cloud / hybrid)

## 4) V1.5
- Gmail/Outlook connector olgunlastirma
- Sosyal medya monitor (gerekiyorsa)
- Explainable assignment recommendation
- Daha gelismis admin ve deployment yuzeyi

## 5) V2 (enterprise)
- On-prem deployment
- SIEM integration
- HSM/KMS key management
- SSO (Azure AD/Okta)

## Source of Truth

Bu belge yuksek seviye hedefi anlatir. Gercek durum ve kilit kararlar icin asagidaki belgeler onceliklidir:
- `PRODUCT_AUDIT.md`
- `V1_SCOPE.md`
- `BOUNDARY_DECISIONS.md`
- `V1_RELEASE_CRITERIA.md`
