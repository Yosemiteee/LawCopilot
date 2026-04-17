from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any


PREFIX_V1 = "lcintsec:v1"
PREFIX_V2 = "lcintsec:v2"
CONTEXT_V1 = b"lawcopilot.integration.secretbox.v1"
CONTEXT_V2 = b"lawcopilot.integration.secretbox.v2"


class SecretBox:
    """Small sealed-box helper for local secret blobs.

    This intentionally keeps the API narrow: JSON in, JSON out. The key source is
    injected by the runtime so the storage backend can be swapped later without
    changing callers.
    """

    def __init__(
        self,
        secret_material: str,
        *,
        posture: str,
        key_id: str = "default",
        previous_keys: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self.active_key_id = str(key_id or "default").strip() or "default"
        self.posture = posture
        materials = [str(secret_material or "").strip(), *(str(item or "").strip() for item in list(previous_keys or []))]
        normalized_materials = [item for item in materials if item]
        if not normalized_materials:
            normalized_materials = ["lawcopilot-local-secret-fallback"]
        self._v1_keys = [self._derive_v1_key(item) for item in normalized_materials]
        self._v2_keys = {
            self.active_key_id if index == 0 else f"legacy-{index}": self._derive_v2_key(item)
            for index, item in enumerate(normalized_materials)
        }
        self.key_count = len(normalized_materials)

    def seal_json(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        nonce = secrets.token_bytes(16)
        key = self._v2_keys[self.active_key_id]
        ciphertext = _xor(raw, _keystream(key, nonce, len(raw)))
        mac = hmac.new(key, CONTEXT_V2 + nonce + ciphertext, hashlib.sha256).digest()
        token = base64.urlsafe_b64encode(nonce + ciphertext + mac).decode("ascii").rstrip("=")
        return f"{PREFIX_V2}:{self.active_key_id}:{token}"

    def open_json(self, token: str) -> dict[str, Any]:
        raw = str(token or "").strip()
        if not raw:
            return {}
        if raw.startswith(f"{PREFIX_V2}:"):
            return self._open_v2(raw)
        if raw.startswith(f"{PREFIX_V1}:"):
            return self._open_v1(raw)
        raise ValueError("invalid_secret_blob")

    def _open_v2(self, token: str) -> dict[str, Any]:
        _, _, key_id, encoded = token.split(":", 3)
        padded = encoded + "=" * ((4 - len(encoded) % 4) % 4)
        blob = base64.urlsafe_b64decode(padded.encode("ascii"))
        if len(blob) < 48:
            raise ValueError("invalid_secret_blob")
        nonce = blob[:16]
        mac = blob[-32:]
        ciphertext = blob[16:-32]
        candidate_keys: list[bytes] = []
        if key_id in self._v2_keys:
            candidate_keys.append(self._v2_keys[key_id])
        candidate_keys.extend(key for key_name, key in self._v2_keys.items() if key_name != key_id)
        return self._decode_blob(ciphertext=ciphertext, mac=mac, nonce=nonce, keys=candidate_keys, context=CONTEXT_V2)

    def _open_v1(self, token: str) -> dict[str, Any]:
        encoded = token.split(":", 2)[-1]
        padded = encoded + "=" * ((4 - len(encoded) % 4) % 4)
        blob = base64.urlsafe_b64decode(padded.encode("ascii"))
        if len(blob) < 48:
            raise ValueError("invalid_secret_blob")
        nonce = blob[:16]
        mac = blob[-32:]
        ciphertext = blob[16:-32]
        return self._decode_blob(ciphertext=ciphertext, mac=mac, nonce=nonce, keys=self._v1_keys, context=CONTEXT_V1)

    def _decode_blob(self, *, ciphertext: bytes, mac: bytes, nonce: bytes, keys: list[bytes], context: bytes) -> dict[str, Any]:
        for key in keys:
            expected = hmac.new(key, context + nonce + ciphertext, hashlib.sha256).digest()
            if not hmac.compare_digest(mac, expected):
                continue
            plaintext = _xor(ciphertext, _keystream(key, nonce, len(ciphertext)))
            parsed = json.loads(plaintext.decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {}
        raise ValueError("invalid_secret_mac")

    def _derive_v1_key(self, secret_material: str) -> bytes:
        material = str(secret_material or "").encode("utf-8")
        if not material:
            material = b"lawcopilot-local-secret-fallback"
        return hashlib.sha256(CONTEXT_V1 + material).digest()

    def _derive_v2_key(self, secret_material: str) -> bytes:
        material = str(secret_material or "").encode("utf-8")
        if not material:
            material = b"lawcopilot-local-secret-fallback"
        posture = str(self.posture or "default").encode("utf-8")
        return hashlib.sha256(CONTEXT_V2 + posture + material).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks = bytearray()
    counter = 0
    while len(blocks) < length:
        blocks.extend(hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest())
        counter += 1
    return bytes(blocks[:length])


def _xor(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))
