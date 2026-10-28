"""Envelope encryption for secrets and OAuth credentials at rest (SEC-3).

Uses AES-256-GCM authenticated encryption:
- Master Key (KEK) is 256-bit (from settings or env).
- Per-record Data Encryption Key (DEK) is randomly generated (256-bit).
- DEK is encrypted under KEK. Payload is encrypted under DEK.
- Ciphertext envelope format:
  'v1:<nonce_kek_b64>:<encrypted_dek_b64>:<nonce_data_b64>:<ciphertext_b64>'
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _get_master_kek() -> bytes:
    """Retrieve 256-bit master Key Encryption Key from settings or derive from SECRET_KEY."""
    raw_key = getattr(settings, "ENCRYPTION_MASTER_KEY", None)
    if not raw_key:
        raw_key = getattr(settings, "SECRET_KEY", "fallback-insecure-key-for-test")
        if not raw_key:
            raise ImproperlyConfigured("ENCRYPTION_MASTER_KEY or SECRET_KEY must be configured.")

    if isinstance(raw_key, str):
        # Derive fixed-size 32-byte (256-bit) key using SHA-256
        return hashlib.sha256(raw_key.encode("utf-8")).digest()
    if isinstance(raw_key, bytes):
        if len(raw_key) == 32:
            return raw_key
        return hashlib.sha256(raw_key).digest()
    raise ImproperlyConfigured("Invalid ENCRYPTION_MASTER_KEY format.")


def encrypt_secret(plaintext: str | bytes, kek: bytes | None = None) -> str:
    """Encrypt plaintext using AES-256-GCM envelope encryption."""
    data = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext

    master_kek = kek if kek is not None else _get_master_kek()

    # 1. Generate 256-bit per-record DEK and 96-bit nonces
    dek = os.urandom(32)
    nonce_data = os.urandom(12)
    nonce_kek = os.urandom(12)

    # 2. Encrypt data with DEK
    aesgcm_dek = AESGCM(dek)
    ciphertext = aesgcm_dek.encrypt(nonce_data, data, None)

    # 3. Encrypt DEK with master KEK
    aesgcm_kek = AESGCM(master_kek)
    encrypted_dek = aesgcm_kek.encrypt(nonce_kek, dek, None)

    # 4. Serialize envelope
    parts = [
        "v1",
        base64.urlsafe_b64encode(nonce_kek).decode("ascii"),
        base64.urlsafe_b64encode(encrypted_dek).decode("ascii"),
        base64.urlsafe_b64encode(nonce_data).decode("ascii"),
        base64.urlsafe_b64encode(ciphertext).decode("ascii"),
    ]
    return ":".join(parts)


def decrypt_secret(envelope: str, kek: bytes | None = None) -> str:
    """Decrypt envelope and return original plaintext string."""
    master_kek = kek if kek is not None else _get_master_kek()

    parts = envelope.strip().split(":")
    if len(parts) != 5:
        raise ValueError("Invalid ciphertext envelope format.")

    version, nonce_kek_b64, enc_dek_b64, nonce_data_b64, ct_b64 = parts
    if version != "v1":
        raise ValueError(f"Unsupported encryption envelope version: {version}")

    try:
        nonce_kek = base64.urlsafe_b64decode(nonce_kek_b64.encode("ascii"))
        encrypted_dek = base64.urlsafe_b64decode(enc_dek_b64.encode("ascii"))
        nonce_data = base64.urlsafe_b64decode(nonce_data_b64.encode("ascii"))
        ciphertext = base64.urlsafe_b64decode(ct_b64.encode("ascii"))
    except Exception as exc:
        raise ValueError("Invalid base64 encoding in ciphertext envelope.") from exc

    # 1. Decrypt DEK using master KEK
    aesgcm_kek = AESGCM(master_kek)
    try:
        dek = aesgcm_kek.decrypt(nonce_kek, encrypted_dek, None)
    except Exception as exc:
        raise ValueError("Decryption failed: master key mismatch or corrupted DEK.") from exc

    # 2. Decrypt data using DEK
    aesgcm_dek = AESGCM(dek)
    try:
        data = aesgcm_dek.decrypt(nonce_data, ciphertext, None)
    except Exception as exc:
        raise ValueError(
            "Decryption failed: corrupted ciphertext or authentication tag mismatch."
        ) from exc

    return data.decode("utf-8")
