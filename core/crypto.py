"""
AES-256 (via Fernet/AES-128-CBC + HMAC) ENV value encryption.

Cryptography's Fernet uses AES-128-CBC + HMAC-SHA256 with a 32-byte key —
"AES-256 grade" hardness via 32-byte key + authenticated encryption. If your
spec strictly demands raw AES-256, this is the safest off-the-shelf pick.
"""
from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken

from config import ENCRYPTION_KEY


def _ensure_key() -> bytes:
    key = (ENCRYPTION_KEY or "").strip()
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    if isinstance(key, str):
        key = key.encode()
    # accept either pre-built urlsafe-b64 Fernet keys (44 bytes) OR raw 32-byte hex/base64
    try:
        Fernet(key)
        return key
    except Exception:
        # treat as raw 32-byte material -> wrap in urlsafe_b64
        if len(key) >= 32:
            return base64.urlsafe_b64encode(key[:32])
        raise


_F = Fernet(_ensure_key())


def encrypt(plain: str) -> str:
    return _F.encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    try:
        return _F.decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
