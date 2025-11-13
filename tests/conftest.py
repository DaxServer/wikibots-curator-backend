import os
import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True, scope="session")
def _ensure_crypto_key():
    if not os.environ.get("TOKEN_ENCRYPTION_KEY"):
        os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    yield
