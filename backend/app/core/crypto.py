from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _ensure_secret_key_file(path: Path) -> bytes:
    if path.exists():
        return path.read_bytes()

    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    path.write_bytes(key)
    path.chmod(0o600)
    return key


def get_fernet() -> Fernet:
    settings = get_settings()
    key = _ensure_secret_key_file(settings.secret_key_path)
    return Fernet(key)


def encrypt_secret(value: str) -> bytes:
    return get_fernet().encrypt(value.encode("utf-8"))


def decrypt_secret(value: bytes | None) -> str | None:
    if value is None:
        return None
    return get_fernet().decrypt(value).decode("utf-8")


class CryptoService:
    def encrypt_secret(self, value: str) -> bytes:
        return encrypt_secret(value)

    def decrypt_secret(self, value: bytes | None) -> str | None:
        return decrypt_secret(value)
