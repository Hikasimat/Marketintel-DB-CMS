"""Tests for AES-256-GCM envelope encryption and secret protection at rest (SEC-3)."""

from __future__ import annotations

import os

import pytest

from apps.common.crypto import decrypt_secret, encrypt_secret


def test_encryption_roundtrip() -> None:
    plaintext = "super-secret-oauth-refresh-token-xyz-1234567890"
    envelope = encrypt_secret(plaintext)

    assert envelope.startswith("v1:")
    assert plaintext not in envelope

    decrypted = decrypt_secret(envelope)
    assert decrypted == plaintext


def test_envelope_randomness_and_unique_deks() -> None:
    plaintext = "same-payload-different-deks"
    env1 = encrypt_secret(plaintext)
    env2 = encrypt_secret(plaintext)

    # Different random nonces and DEKs must yield distinct envelopes
    assert env1 != env2
    assert decrypt_secret(env1) == plaintext
    assert decrypt_secret(env2) == plaintext


def test_tampering_triggers_decryption_failure() -> None:
    plaintext = "sensitive-api-key"
    envelope = encrypt_secret(plaintext)

    parts = envelope.split(":")
    # Tamper with the ciphertext payload
    tampered_ct = parts[4][:-4] + "AAAA"
    tampered_envelope = ":".join([*parts[:4], tampered_ct])

    with pytest.raises(ValueError, match="Decryption failed"):
        decrypt_secret(tampered_envelope)


def test_custom_kek_and_key_mismatch() -> None:
    kek_a = os.urandom(32)
    kek_b = os.urandom(32)

    plaintext = "custom-key-payload"
    env = encrypt_secret(plaintext, kek=kek_a)

    assert decrypt_secret(env, kek=kek_a) == plaintext

    # Decrypting with wrong key must fail authentication
    with pytest.raises(ValueError, match="Decryption failed"):
        decrypt_secret(env, kek=kek_b)
