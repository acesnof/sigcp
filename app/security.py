import hashlib
import secrets


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        150000
    ).hex()

    return salt, password_hash


def verificar_password(password, salt, password_hash):
    _, novo_hash = hash_password(password, salt)
    return secrets.compare_digest(novo_hash, password_hash)
