# Security Hardening

## Scope
This hardening pass focused on prompt injection, untrusted-content contamination, and outbound data exfiltration risks in LawCopilot.

## Risks Found
- External content from email, WhatsApp, Telegram, X, and attachment analysis was flowing into assistant context with minimal isolation.
- Malicious messages could embed phrases such as "ignore previous instructions", "system prompt", "send token", or Turkish variants of the same ideas.
- Attachment analysis text could be treated as trusted context even when it contained instruction-like text.
- Outbound channel actions already required approvals, but inbound prompt contamination still risked steering the model.

## Protections Implemented
### 1. Untrusted content quarantine
- Added `assess_untrusted_text(...)` in `apps/api/lawcopilot_api/connectors/safety.py`.
- External snippets are now:
  - compacted
  - length-limited
  - scanned for prompt-injection markers
  - redacted with `[redacted-untrusted-instruction]`
  - flagged as quarantined when suspicious

### 2. Broader prompt-injection detection
- Added English and Turkish patterns for:
  - ignoring instructions
  - system/developer prompt references
  - secret/token exfiltration attempts
  - tool/command execution requests
  - prompt markup markers

### 3. Safer assistant runtime prompts
- Assistant prompt builders now explicitly state that email, message, social, and attachment content is untrusted data.
- When quarantined items exist, the runtime prompt adds a security note so the model treats them only as data, never as instructions.

### 4. Attachment analysis hardening
- Source-ref attachment text now goes through the same quarantine pass.
- Attachment context lines show a quarantine marker instead of silently passing suspicious text through.

### 5. Test coverage
- Added regression tests to ensure:
  - malicious email and WhatsApp content is redacted before prompt use
  - attachment analysis text is quarantined
  - Turkish and English instruction-injection variants are both covered

## Residual Risks
- OCR or document parsers may still produce semantically malicious but pattern-light text that avoids regex matches.
- Extremely long or obfuscated indirect prompt injection can still degrade output quality even when explicit phrases are removed.
- Connected account actions remain high sensitivity; approvals reduce risk but do not replace policy review.
- The assistant can still summarize malicious content as data, so downstream operators should not treat summaries as trusted instructions.

## Recommended Next Steps
- Add semantic risk scoring on top of regex heuristics for documents and long messages.
- Add connector-specific allowlists and sensitivity classes for inboxes and chat channels.
- Add rate limits and anomaly logging for repeated quarantined content from the same sender/channel.
- Add stronger secrets redaction for tokens, cookies, API keys, and access URLs before any model exposure.
- Add a visible UI badge when a reply relied on quarantined external content.
