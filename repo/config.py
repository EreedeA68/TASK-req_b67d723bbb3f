"""Application configuration."""
import base64
import hashlib
import os


def _derive_encryption_key(secret: str) -> str:
    """Derive a stable Fernet-compatible key from a secret string using PBKDF2.

    This ensures the encryption key is deterministic for a given secret,
    so encrypted data remains readable across process restarts.
    """
    key_bytes = hashlib.pbkdf2_hmac(
        "sha256", secret.encode(), b"wildlifelens-enc-salt", 100_000, dklen=32
    )
    return base64.urlsafe_b64encode(key_bytes).decode()


_DEFAULT_SECRET = "dev-secret-change-me"


class Config:
    """Base configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY", _DEFAULT_SECRET)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///wildlifelens.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_ENABLED = True

    # Fernet encryption key — derived deterministically from SECRET_KEY so that
    # encrypted data survives process restarts.  Override via ENCRYPTION_KEY env var.
    ENCRYPTION_KEY = os.environ.get(
        "ENCRYPTION_KEY",
    ) or _derive_encryption_key(os.environ.get("SECRET_KEY", _DEFAULT_SECRET))

    @staticmethod
    def init_app(app) -> None:
        """Fail-fast if insecure defaults are active in a non-test environment."""
        if not app.config.get("TESTING") and app.config.get("SECRET_KEY") == _DEFAULT_SECRET:
            raise RuntimeError(
                "INSECURE DEFAULT: SECRET_KEY is not set. "
                "Set the SECRET_KEY environment variable before running. "
                "Example: export SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')"
            )

    # Export directory
    EXPORT_DIR = os.environ.get("EXPORT_DIR", "exports")

    # Clock-in tuning
    CLOCKIN_MIN_BRIGHTNESS = float(os.environ.get("CLOCKIN_MIN_BRIGHTNESS", "0.5"))
    # Face-match threshold — prompt-specified default is 0.85.  Operators can
    # raise/lower via the CLOCKIN_FACE_THRESHOLD env var at deployment time.
    CLOCKIN_FACE_THRESHOLD = float(os.environ.get("CLOCKIN_FACE_THRESHOLD", "0.85"))

    # Strict biometric mode — requires face_image_hash for all clock-in punches.
    # Production deployments should leave this enabled.  Tests/dev can disable
    # via the TestConfig or CLOCKIN_STRICT=false env var.
    CLOCKIN_STRICT = os.environ.get("CLOCKIN_STRICT", "true").lower() != "false"


class TestConfig(Config):
    """Testing configuration."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret"
    ENCRYPTION_KEY = _derive_encryption_key("test-secret")
    EXPORT_DIR = "test_exports"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    # Tests rely on client-claim fallback — strict mode enforced separately.
    CLOCKIN_STRICT = False
