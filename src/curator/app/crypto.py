import json

from cryptography.fernet import Fernet
from mwoauth import AccessToken

from curator.app.config import TOKEN_ENCRYPTION_KEY


def _get_fernet() -> Fernet:
    return Fernet(TOKEN_ENCRYPTION_KEY)


def encrypt_access_token(token: AccessToken) -> str:
    data = json.dumps(list(token)).encode()
    f = _get_fernet()
    return f.encrypt(data).decode()


def decrypt_access_token(ciphertext: str) -> AccessToken:
    f = _get_fernet()
    data = f.decrypt(ciphertext.encode())
    return AccessToken(*json.loads(data.decode()))
