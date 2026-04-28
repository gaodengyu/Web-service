from app_helpers import safe_float


def order_status_class(status):
    mapping = {
        "待接待": "badge-soft-warning",
        "待接单": "badge-soft-warning",
        "已接单": "badge-soft-info",
        "待确认完成": "badge-soft-primary",
        "已完成": "badge-soft-success",
        "已取消": "badge-soft-muted",
        "已拒单": "badge-soft-danger",
        "已退款": "badge-soft-danger",
    }
    return mapping.get(status, "badge-soft-muted")


def payment_status_class(status):
    mapping = {
        "未支付": "badge-soft-muted",
        "已支付": "badge-soft-success",
        "待退款": "badge-soft-warning",
        "已退款": "badge-soft-danger",
    }
    return mapping.get(status, "badge-soft-muted")


def complaint_status_class(status):
    mapping = {
        "无投诉": "badge-soft-muted",
        "待处理": "badge-soft-warning",
        "处理中": "badge-soft-info",
        "已解决": "badge-soft-success",
        "已退款": "badge-soft-danger",
        "已驳回": "badge-soft-muted",
    }
    return mapping.get(status, "badge-soft-muted")


def store_is_approved(store):
    return bool(store) and (store.get("approval_status") or "approved") == "approved"


def store_review_label(store):
    status = (store or {}).get("approval_status") or "pending"
    return {
        "approved": "已通过",
        "rejected": "已驳回",
        "pending": "待审核",
    }.get(status, "待审核")


def store_review_badge(store):
    status = (store or {}).get("approval_status") or "pending"
    return {
        "approved": "badge-soft-success",
        "rejected": "badge-soft-danger",
        "pending": "badge-soft-warning",
    }.get(status, "badge-soft-warning")


def stringify_price(value):
    if value in {None, ""}:
        return ""
    amount = safe_float(value, default=0)
    if amount <= 0:
        return str(value).strip()
    return str(int(amount)) if float(amount).is_integer() else f"{amount:.2f}"
