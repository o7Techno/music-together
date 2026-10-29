import pytest

from app.auth.crypto import TokenCipher, TokenCipherError


def test_roundtrip_and_ciphertext_differs() -> None:
    cipher = TokenCipher(TokenCipher.generate_key())
    secret = "y0_AgAAAAB-very-secret-token"
    encrypted = cipher.encrypt(secret)
    assert secret not in encrypted
    assert cipher.decrypt(encrypted) == secret
    assert cipher.encrypt(secret) != encrypted  # Fernet: случайный IV


def test_key_rotation() -> None:
    old, new = TokenCipher.generate_key(), TokenCipher.generate_key()
    legacy = TokenCipher(old).encrypt("token")
    rotated_cipher = TokenCipher(f"{new},{old}")
    assert rotated_cipher.decrypt(legacy) == "token"  # старые записи читаются
    rotated = rotated_cipher.rotate(legacy)
    assert TokenCipher(new).decrypt(rotated) == "token"  # перешифровано новым ключом
    with pytest.raises(TokenCipherError):
        TokenCipher(old).decrypt(rotated)


def test_wrong_key_and_garbage() -> None:
    cipher = TokenCipher(TokenCipher.generate_key())
    other = TokenCipher(TokenCipher.generate_key())
    with pytest.raises(TokenCipherError):
        other.decrypt(cipher.encrypt("x"))
    with pytest.raises(TokenCipherError):
        cipher.decrypt("not-a-token")


def test_empty_keys_rejected() -> None:
    with pytest.raises(ValueError, match="пуст"):
        TokenCipher(" , ")
