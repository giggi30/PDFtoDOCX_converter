import hashlib
import hmac
import secrets


def create_access_token() -> str:
    return secrets.token_urlsafe(32)


def hash_access_token(token: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), token.encode(), hashlib.sha256).hexdigest()


def token_matches(token: str, expected_hash: str, pepper: str) -> bool:
    return hmac.compare_digest(hash_access_token(token, pepper), expected_hash)
