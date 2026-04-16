"""Symmetric encryption using Fernet (AES-128-CBC under the hood)."""
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


def _get_fernet() -> Fernet:
    key = current_app.config["ENCRYPTION_KEY"].encode()
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return the base64-encoded ciphertext."""
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext back to plaintext."""
    if not ciphertext:
        return ""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        return ""


def mask_phone(phone: str) -> str:
    """Mask all but last 4 digits: ****1234."""
    if not phone or len(phone) < 4:
        return "****"
    return "****" + phone[-4:]


def mask_balance(balance: str) -> str:
    """Fully mask balance."""
    return "****"
