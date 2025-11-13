from curator.app.config import FERNET_KEY
import json
from typing import Any
from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    if not FERNET_KEY:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not set")
    return Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)


def encrypt_access_token(token: Any) -> str:
    data = json.dumps(list(token)).encode()
    f = _get_fernet()
    return f.encrypt(data).decode()


def decrypt_access_token(ciphertext: str) -> list[str]:
    f = _get_fernet()
    data = f.decrypt(ciphertext.encode())
    return list(json.loads(data.decode()))
