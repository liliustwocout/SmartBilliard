import unicodedata


def fold(value: str | None) -> str:
    """Chữ thường, bỏ dấu tiếng Việt: để tìm 'dai nam' ra 'Đại Nam'."""
    text = unicodedata.normalize("NFD", (value or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower()
