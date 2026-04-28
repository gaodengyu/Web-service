import re


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def split_tags(value):
    if not value:
        return []
    text = str(value)
    for sep in ["，", "/", "|", "、", ";", "；"]:
        text = text.replace(sep, ",")
    return [item.strip() for item in text.split(",") if item.strip()]


def normalize_email(value):
    return (value or "").strip().lower()


def normalize_phone(value):
    raw = "".join(char for char in str(value or "") if char.isdigit() or char == "+")
    if raw.startswith("+86"):
        raw = raw[3:]
    elif raw.startswith("86") and len(raw) >= 11:
        raw = raw[2:]
    return "".join(char for char in raw if char.isdigit())


def looks_like_email(value):
    email = normalize_email(value)
    if " " in email or "@" not in email:
        return False
    local_part, _, domain = email.partition("@")
    return bool(local_part and domain and "." in domain)


def looks_like_phone(value):
    phone = normalize_phone(value)
    return phone.isdigit() and 6 <= len(phone) <= 15


def validate_email_address(email):
    email = normalize_email(email)
    if not email:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", email):
        return "请输入有效的邮箱地址。"
    return ""


def validate_password_policy(password):
    password = (password or "").strip()
    if len(password) < 8:
        return "密码至少需要 8 位。"
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "密码至少需要同时包含字母和数字。"
    return ""


def format_price_text(value):
    amount = safe_float(value, default=0)
    if amount <= 0:
        return "价格面议"
    if float(amount).is_integer():
        return f"¥{int(amount)} 起"
    return f"¥{amount:.2f} 起"


def parse_rating(value):
    rating = safe_float(value, default=0)
    if rating <= 0:
        return None
    return rating
