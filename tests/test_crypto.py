from curator.app.crypto import encrypt_access_token, decrypt_access_token


def test_encrypt_decrypt_roundtrip():
    token = ("access_token", "access_secret")
    enc = encrypt_access_token(token)
    dec = decrypt_access_token(enc)
    assert tuple(dec) == token
