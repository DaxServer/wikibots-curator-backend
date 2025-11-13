import os
import json
from typing import Any
from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    key = os.environ.get("TOKEN_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not set")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_access_token(token: Any) -> str:
    data = json.dumps(list(token)).encode()
    f = _get_fernet()
    return f.encrypt(data).decode()


def decrypt_access_token(ciphertext: str) -> list[str]:
    f = _get_fernet()
    data = f.decrypt(ciphertext.encode())
    return list(json.loads(data.decode()))
