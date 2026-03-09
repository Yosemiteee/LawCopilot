# Email Connector Safety Spec

- OAuth2 only (no raw password)
- Default action: DRAFT
- SEND requires explicit user confirmation each time
- Full audit record: who approved, when, recipient hash, subject hash
- Rate limit and domain allowlist support
