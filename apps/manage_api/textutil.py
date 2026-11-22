import re
import unicodedata


def fold(value: str | None) -> str:
    """Chữ thường, bỏ dấu tiếng Việt: để tìm 'dai nam' ra 'Đại Nam'."""
    text = unicodedata.normalize("NFD", (value or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower()


PHONE_RE = re.compile(r"^0\d{9}$")


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"[\s.\-()]", "", raw)
    if digits.startswith("+84"):
        digits = "0" + digits[3:]
    elif digits.startswith("84") and len(digits) == 11:
        digits = "0" + digits[2:]
    return digits
