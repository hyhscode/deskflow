import base64
import hashlib
import hmac
import json
import secrets
import time

from app.core.config import settings

PBKDF2_ITERATIONS = 260_000
SALT_BYTES = 16


def hash_password(password:str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",password.encode("utf-8"),salt,PBKDF2_ITERATIONS
    )

    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"

def verify_password(password:str,stored:str) -> bool:
    try:
        algorithm,iterations,salt_hex,hash_hex = stored.split("$")
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        int(iterations),
    )

    return hmac.compare_digest(digest.hex(),hash_hex)

ALGORITHM = "HS256"

class TokenError(Exception):
    pass

def _b64url_encode(raw:bytes) -> str:
    return base64.urlsafe_b64decode(raw).rstrip(b"=").decode("ascii")

def _b64url_decode(text:str) -> bytes:
    padding = "=" *(-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)

def _sign(signing_input:bytes) -> bytes:
    secret = settings.secret_key.get_secret_value().encode("utf-8")
    return hmac.new(secret, signing_input, hashlib.sha256).digest()

def create_access_token(user_id: int, expires_minutes: int | None = None) -> str:
    now = int(time.time())          # 秒级时间戳
    minutes = expires_minutes or settings.token_expire_minutes

    header = {"alg": ALGORITHM, "typ": "JWT"}

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + minutes * 60,
    }

    segments = [
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode()),
        _b64url_encode(json.dumps(payload, separators=(",", ":")).encode()),
    ]

    signing_input = ".".join(segments).encode("ascii")
    segments.append(_b64url_encode(_sign(signing_input)))

    return ".".join(segments)

def decode_access_token(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError("token 格式不正确，应该是三段")

    header_b64, payload_b64, signature_b64 = parts
    try:
        actual_signature = _b64url_decode(signature_b64)
    except Exception as exc:
        raise TokenError("签名不是合法的 base64") from exc

    expected_signature = _sign(f"{header_b64}.{payload_b64}".encode("ascii"))
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise TokenError("签名不匹配：token 被篡改过，或不是本服务签发的")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as exc:
        raise TokenError("payload 不是合法 JSON") from exc

    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise TokenError("token 缺少过期时间")
    if exp < int(time.time()):
        raise TokenError("token 已过期，请重新登录")

    return payload