"""Шифрование токенов Яндекса at rest (SPEC §4.1, §7.6): MultiFernet с ротацией ключей.

`TOKEN_ENCRYPTION_KEYS` — ключи через запятую; первый шифрует, все расшифровывают.
Ротация: добавить новый ключ первым, перезапустить, вызвать `rotate()` для существующих записей,
затем удалить старый ключ.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.errors import AppError


class TokenCipherError(AppError):
    code = "token_cipher"
    default_message = "Не удалось прочитать сохранённый вход — войдите заново."


class TokenCipher:
    def __init__(self, keys: str) -> None:
        parts = [k.strip() for k in keys.split(",") if k.strip()]
        if not parts:
            raise ValueError("TOKEN_ENCRYPTION_KEYS пуст")
        self._fernet = MultiFernet([Fernet(k.encode()) for k in parts])

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as e:
            raise TokenCipherError from e

    def rotate(self, ciphertext: str) -> str:
        """Перешифровать текущим (первым) ключом."""
        try:
            return self._fernet.rotate(ciphertext.encode()).decode()
        except InvalidToken as e:
            raise TokenCipherError from e

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode()
