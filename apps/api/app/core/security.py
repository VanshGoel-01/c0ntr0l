import hashlib
import hmac
import secrets

API_KEY_MARKER = "ctl_"


def generate_api_key() -> str:
    return f"{API_KEY_MARKER}{secrets.token_urlsafe(32)}"


def api_key_prefix(raw_key: str) -> str:
    return raw_key[:12]


def hash_api_key(raw_key: str, pepper: str) -> str:
    return hmac.new(
        pepper.encode("utf-8"),
        raw_key.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def has_valid_api_key_shape(raw_key: str) -> bool:
    return raw_key.startswith(API_KEY_MARKER) and 36 <= len(raw_key) <= 64
