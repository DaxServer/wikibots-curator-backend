import os
import json
from cryptography.fernet import Fernet
from mwoauth import AccessToken


def _get_fernet() -> Fernet:
    key = os.environ.get("TOKEN_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not set")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_access_token(token: AccessToken) -> str:
    data = json.dumps(list(token)).encode()
    f = _get_fernet()
    return f.encrypt(data).decode()


def decrypt_access_token(ciphertext: str) -> AccessToken:
    f = _get_fernet()
    data = f.decrypt(ciphertext.encode())
    return AccessToken(*json.loads(data.decode()))
