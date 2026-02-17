"""Tests for cryptographic utilities."""

from curator.app.crypto import decrypt_access_token, encrypt_access_token


def test_encrypt_decrypt_roundtrip():
    """Test that encrypt and decrypt operations are reversible."""
    token = ("access_token", "access_secret")
    enc = encrypt_access_token(token)
    dec = decrypt_access_token(enc)
    assert tuple(dec) == token
