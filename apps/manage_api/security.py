"""Băm mật khẩu (scrypt, thư viện chuẩn) và token phiên."""
import base64
import hashlib
import hmac
import secrets

_N, _R, _P = 2 ** 14, 8, 1
MIN_PASSWORD_LENGTH = 10


def hash_password(password: str, *, n: int = _N) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=n, r=_R, p=_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(n, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Băm giả để thời gian phản hồi không lộ tài khoản có tồn tại hay không.
DUMMY_HASH = hash_password("dummy-password-for-timing")


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Mật khẩu cần ít nhất {MIN_PASSWORD_LENGTH} ký tự."
    if len(password) > 200:
        return "Mật khẩu quá dài."
    if password.strip() != password or password.isdigit() or len(set(password)) < 4:
        return "Mật khẩu quá dễ đoán: tránh toàn số, ký tự lặp hoặc khoảng trắng đầu/cuối."
    return None
