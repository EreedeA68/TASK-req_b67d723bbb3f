"""Password hashing helpers (bcrypt)."""
import bcrypt


def hash_password(plain: str) -> str:
    if not isinstance(plain, str) or not plain:
        raise ValueError("Password must be a non-empty string")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False
