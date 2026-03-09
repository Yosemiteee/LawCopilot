# Threat Model (v0.4)

## Scope
- API auth & authorization
- RAG ingest/query flow
- Connector output channels (mail/social/webhook)
- Installer ve binary indirme adımları

## Primary Threats

1. **Unauthorized API usage**
   - Attack: forged/expired token, role escalation
   - Mitigation: HMAC signature verify, exp check, role hierarchy

2. **Cross-tenant / over-broad retrieval**
   - Attack: query returns unauthorized chunks
   - Mitigation (now): role gate + audit visibility
   - Mitigation (next): tenant-id scoped vector filtering

3. **Prompt Injection + Data Exfiltration**
   - Attack: model outputs PII into connectors
   - Mitigation: connector preview safety wrapper, PII redaction, dry-run default

4. **Malicious outbound connector action**
   - Attack: send data to attacker-controlled destination
   - Mitigation: strict destination allowlist + rejection on mismatch

5. **Installer tampering / MITM**
   - Attack: modified package download
   - Mitigation: HTTPS/TLS1.2+, required SHA256 checksum verification

6. **Audit log deletion/tamper**
   - Attack: erase traces after abuse
   - Mitigation (now): append-only JSONL semantics, restricted perms
   - Mitigation (next): remote immutable log sink + signed chain

## Residual Risks
- In-memory RAG store persistence yok (restart sonrası kayıp)
- Token revocation list yok
- Connector approval workflow henüz 4-eyes değil
