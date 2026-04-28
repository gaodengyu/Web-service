from datetime import datetime, timedelta, timezone
from functools import wraps
import json
import os

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception

CHINA_TIMEZONE = timezone(timedelta(hours=8))
if ZoneInfo is not None:
    try:
        CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")
    except ZoneInfoNotFoundError:
        CHINA_TIMEZONE = timezone(timedelta(hours=8))
import secrets
import sqlite3
import smtplib
import ssl
import sys
import uuid
from email.message import EmailMessage
import os

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None

try:
    import stripe
except ImportError:
    stripe = None
from flask import Flask, flash, g, has_request_context, redirect, render_template, request, session, url_for
try:
    from flask_socketio import SocketIO, join_room
except ImportError:
    SocketIO = None

    def join_room(*args, **kwargs):
        return None
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


from app_constants import (
    ALLOWED_IMAGE_EXTENSIONS,
    COMPLAINT_STATUS_OPTIONS,
    DISCOVERY_FILTER_TAGS,
    DISCOVERY_GAMES,
    ORDER_STATUS_OPTIONS,
    ROLE_LABELS,
    SEED_BOOSTERS,
    SEED_MERCHANTS,
    SERVICE_TYPE_OPTIONS,
    SHOWCASE_STORES,
    SOCIAL_PROVIDER_LABELS,
    STORE_THEME_OPTIONS,
)
from app_helpers import (
    format_price_text,
    looks_like_email,
    looks_like_phone,
    normalize_email,
    normalize_phone,
    parse_rating,
    safe_float,
    safe_int,
    split_tags,
    validate_email_address,
    validate_password_policy,
)
from app_dependencies import (
    API_ROUTE_DEP_KEYS,
    MARKET_DEP_KEYS,
    MISC_ROUTE_DEP_KEYS,
    STOREFRONT_DEP_KEYS,
    select_dependencies,
)
from service_system import create_service_system_blueprint
from routes.auth_routes import (
    choose_role_view as auth_choose_role_view,
    forgot_password as auth_forgot_password,
    login_view as auth_login_view,
    register_view as auth_register_view,
)
from routes.admin_routes import admin_users_view as admin_users_handler
from routes.admin_routes import social_login_disabled as social_login_disabled_handler
from routes.payment_routes import (
    create_checkout_session as payments_create_checkout_session,
    create_checkout_redirect_url as payments_create_checkout_redirect_url,
    payment_cancel as payments_payment_cancel,
    payment_cancel_storefront as payments_payment_cancel_storefront,
    payment_success as payments_payment_success,
    payment_success_storefront as payments_payment_success_storefront,
)
from app_order_view_helpers import (
    calculate_time_based_quote as helpers_calculate_time_based_quote,
    build_store_order_payload as helpers_build_store_order_payload,
    decorate_order_for_view as helpers_decorate_order_for_view,
    get_order_store as helpers_get_order_store,
    get_store_applications_for_owner as helpers_get_store_applications_for_owner,
    public_store_access_allowed as helpers_public_store_access_allowed,
    resolve_store_for_order_target as helpers_resolve_store_for_order_target,
)
from app_market import (
    build_booster_card as market_build_booster_card,
    build_store_card as market_build_store_card,
    create_order_notifications as market_create_order_notifications,
    filter_and_rank_boosters as market_filter_and_rank_boosters,
    filter_and_rank_stores as market_filter_and_rank_stores,
    get_featured_stores as market_get_featured_stores,
    get_merchant_orders as market_get_merchant_orders,
    get_merchant_stats as market_get_merchant_stats,
    get_player_stats as market_get_player_stats,
    get_store_boosters as market_get_store_boosters,
    get_top_boosters as market_get_top_boosters,
    notify_merchant_for_order as market_notify_merchant_for_order,
)
from routes.storefront_routes import (
    admin_users_storefront as sf_admin_users_storefront,
    booster_home_storefront as sf_booster_home_storefront,
    booster_orders_storefront as sf_booster_orders_storefront,
    booster_profile_storefront as sf_booster_profile_storefront,
    boosters_list_storefront as sf_boosters_list_storefront,
    choose_role_storefront as sf_choose_role_storefront,
    contact_store_storefront as sf_contact_store_storefront,
    create_order_storefront as sf_create_order_storefront,
    home_storefront as sf_home_storefront,
    merchant_home_storefront as sf_merchant_home_storefront,
    merchant_store_storefront as sf_merchant_store_storefront,
    merchant_talents_storefront as sf_merchant_talents_storefront,
    player_orders_storefront as sf_player_orders_storefront,
    store_detail_storefront as sf_store_detail_storefront,
)
from app_status import (
    complaint_status_class,
    order_status_class,
    payment_status_class,
    store_is_approved,
    store_review_badge,
    store_review_label,
    stringify_price,
)
from routes.misc_routes import (
    admin_home_view as routes_admin_home_view,
    admin_orders_view as routes_admin_orders_view,
    admin_send_notification_view as routes_admin_send_notification_view,
    booster_chats_view as routes_booster_chats_view,
    chat_view as routes_chat_view,
    logout_view as routes_logout_view,
    merchant_application_status_view as routes_merchant_application_status_view,
    merchant_chats_view as routes_merchant_chats_view,
    player_chats_view as routes_player_chats_view,
    send_message_view as routes_send_message_view,
)


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def china_now_text():
    return datetime.now(CHINA_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


def load_local_env_file():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    allow_dotenv_database_url = (os.environ.get("ALLOW_DOTENV_DATABASE_URL") or "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip().lstrip("\ufeff")
                value = value.strip().strip('"').strip("'")
                if key == "DATABASE_URL" and not allow_dotenv_database_url:
                    continue
                current = (os.environ.get(key) or "").strip()
                if key and (not current or current.startswith("your_")):
                    os.environ[key] = value
    except Exception as exc:
        print(f"[DEBUG] Failed to load .env file: {exc}", file=sys.stderr)


load_local_env_file()


def resolve_stripe_api_key():
    candidates = [
        os.environ.get("STRIPE_SECRET_KEY"),
        os.environ.get("STRIPE_API_KEY"),
        os.environ.get("STRIPE_SECERET_KEY"),
    ]
    for key in candidates:
        value = (key or "").strip()
        if value:
            return value
    return ""


STRIPE_API_KEY = resolve_stripe_api_key()
if stripe is not None:
    stripe.api_key = STRIPE_API_KEY or ""


def stripe_is_configured():
    key = (STRIPE_API_KEY or "").strip()
    return stripe is not None and bool(key) and not key.startswith("your_") and key.startswith("sk_")


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "your_secret_key")
if SocketIO is not None:
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
else:
    socketio = None

APP_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip() or None
DATABASE = os.path.join(APP_BASE_DIR, "data.db")
USER_FILE = "users.json"
ORDER_FILE = "orders.json"

ADMIN_REGISTER_PASSWORD = os.environ.get("ADMIN_REGISTER_PASSWORD", "").strip()
MAX_LOGIN_ATTEMPTS = 5
MAIL_SERVER = (os.environ.get("MAIL_SERVER") or os.environ.get("SMTP_HOST") or "").strip()
try:
    MAIL_PORT = int((os.environ.get("MAIL_PORT") or os.environ.get("SMTP_PORT") or "587").strip())
except ValueError:
    MAIL_PORT = 587
MAIL_USERNAME = (os.environ.get("MAIL_USERNAME") or os.environ.get("SMTP_USERNAME") or "").strip()
MAIL_PASSWORD = (os.environ.get("MAIL_PASSWORD") or os.environ.get("SMTP_PASSWORD") or "").strip()
MAIL_FROM = (os.environ.get("MAIL_FROM") or os.environ.get("SMTP_FROM") or MAIL_USERNAME or "").strip()
MAIL_USE_TLS = (os.environ.get("MAIL_USE_TLS") or "true").strip().lower() in {"1", "true", "yes", "on"}
try:
    PASSWORD_RESET_CODE_TTL_MINUTES = int((os.environ.get("PASSWORD_RESET_CODE_TTL_MINUTES") or "10").strip())
except ValueError:
    PASSWORD_RESET_CODE_TTL_MINUTES = 10
SYSTEM_USERNAME = "__system__"
RESERVED_USERNAMES = {SYSTEM_USERNAME.lower()}

BUDDY_COIN_TO_CASH_RATE = 1.0
WITHDRAW_CASH_PER_COIN = 0.8
BOOSTER_REVENUE_SHARE = 0.8
SYNC_SEED_PASSWORDS_ON_BOOT = (os.environ.get("SYNC_SEED_PASSWORDS_ON_BOOT") or "").strip().lower() in {"1", "true", "yes", "on"}


def get_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def chat_room_name(user_a, user_b):
    left = (user_a or "").strip()
    right = (user_b or "").strip()
    if not left or not right:
        return ""
    return "chat::" + "::".join(sorted([left, right]))


def emit_chat_message(sender, receiver, message, timestamp=""):
    if socketio is None:
        return
    room = chat_room_name(sender, receiver)
    if not room:
        return
    socketio.emit(
        "chat:message",
        {
            "sender": (sender or "").strip(),
            "receiver": (receiver or "").strip(),
            "message": (message or "").strip(),
            "timestamp": timestamp or china_now_text(),
        },
        to=room,
    )


if socketio is not None:

    @socketio.on("chat:join")
    def socket_chat_join(payload):
        room = chat_room_name((payload or {}).get("user"), (payload or {}).get("partner"))
        if room:
            join_room(room)


@app.before_request
def validate_csrf_token():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None

    provided_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    if request.is_json and not provided_token:
        provided_token = (request.get_json(silent=True) or {}).get("csrf_token", "")
    expected_token = session.get("_csrf_token", "")

    if app.config.get("TESTING") and provided_token == "test-csrf-token":
        return None
    if expected_token and provided_token and secrets.compare_digest(expected_token, provided_token):
        return None

    if request.is_json:
        return {"error": "CSRF 校验失败，请刷新页面后重试。"}, 400

    flash("请求已过期，请刷新页面后重试。", "danger")
    return redirect(request.referrer or url_for("home"))


def is_postgres():
    return bool(DATABASE_URL)


def placeholder():
    return "%s" if is_postgres() else "?"


def role_label(role):
    return ROLE_LABELS.get(role, role or "访客")


def sanitize_username_seed(value):
    text = (value or "").strip()
    cleaned = "".join(char for char in text if char.isalnum() or char in {"_", "-", "."})
    return cleaned.strip("._-")[:24]


def unique_username_from_seed(value, fallback_prefix="gb"):
    base = sanitize_username_seed(value) or f"{fallback_prefix}_{uuid.uuid4().hex[:6]}"
    candidate = base
    suffix = 2
    while get_user(candidate):
        trimmed = base[: max(8, 24 - len(str(suffix)) - 1)]
        candidate = f"{trimmed}-{suffix}"
        suffix += 1
    return candidate


def static_upload_dir(*parts):
    return os.path.join(app.root_path, "static", *parts)


def ensure_upload_dirs():
    for subdir in [
        ("uploads",),
        ("uploads", "stores"),
        ("uploads", "stores", "logo"),
        ("uploads", "stores", "cover"),
        ("uploads", "stores", "proof"),
        ("uploads", "boosters"),
        ("uploads", "boosters", "avatar"),
        ("uploads", "boosters", "cover"),
        ("uploads", "boosters", "proof"),
    ]:
        os.makedirs(static_upload_dir(*subdir), exist_ok=True)


def allowed_image(filename):
    ext = os.path.splitext(filename or "")[1].lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS


def save_uploaded_image(file_storage, *subdir, prefix="img"):
    if not file_storage or not getattr(file_storage, "filename", ""):
        return ""
    if not allowed_image(file_storage.filename):
        raise ValueError("仅支持 png/jpg/jpeg/webp/gif 图片。")
    ensure_upload_dirs()
    ext = os.path.splitext(file_storage.filename)[1].lower()
    filename = secure_filename(f"{prefix}_{uuid.uuid4().hex[:12]}{ext}")
    absolute_dir = static_upload_dir(*subdir)
    absolute_path = os.path.join(absolute_dir, filename)
    file_storage.save(absolute_path)
    return "/".join([*subdir, filename])


def image_url(path):
    if not path:
        return ""
    if has_request_context():
        return url_for("static", filename=path)
    return f"/static/{path}"


def password_is_hashed(value):
    value = value or ""
    return value.startswith(("pbkdf2:", "scrypt:", "argon2:"))


def serialize_profile(profile):
    return json.dumps(profile or {}, ensure_ascii=False)


def parse_profile(raw_value):
    if not raw_value:
        return {}
    if isinstance(raw_value, dict):
        return raw_value
    try:
        return json.loads(raw_value)
    except (TypeError, ValueError):
        return {}


def round_coin(value):
    return round(safe_float(value, 0.0), 2)


def get_wallet_snapshot(user):
    profile = dict((user or {}).get("profile") or {})
    balance = max(round_coin(profile.get("buddy_coin_balance", 0.0)), 0.0)
    locked = max(round_coin(profile.get("buddy_coin_locked", 0.0)), 0.0)
    return {
        "balance": balance,
        "locked": min(locked, balance),
        "available": max(round_coin(balance - min(locked, balance)), 0.0),
        "profile": profile,
    }


def save_wallet_snapshot(username, wallet_snapshot):
    profile = dict(wallet_snapshot.get("profile") or {})
    profile["buddy_coin_balance"] = round_coin(wallet_snapshot.get("balance", 0.0))
    profile["buddy_coin_locked"] = round_coin(wallet_snapshot.get("locked", 0.0))
    update_user(username, {"profile": profile})


def add_wallet_transaction(username, tx_type, coin_amount, cash_amount=0.0, note="", related_order_id=0, status="completed"):
    execute_query(
        (
            f"INSERT INTO wallet_transactions (username, tx_type, coin_amount, cash_amount, related_order_id, status, note, created_at) "
            f"VALUES ({placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()})"
        ),
        (
            username,
            (tx_type or "").strip(),
            round_coin(coin_amount),
            round_coin(cash_amount),
            safe_int(related_order_id, 0),
            (status or "completed").strip() or "completed",
            (note or "").strip(),
            now_text(),
        ),
        commit=True,
    )


def get_wallet_transactions(username, limit=50):
    rows = execute_query(
        (
            f"SELECT * FROM wallet_transactions WHERE username = {placeholder()} "
            f"ORDER BY id DESC LIMIT {placeholder()}"
        ),
        ((username or "").strip(), max(safe_int(limit, 50), 1)),
        fetchall=True,
    )
    return [
        {
            "id": row["id"],
            "username": row["username"],
            "tx_type": row["tx_type"],
            "coin_amount": round_coin(row["coin_amount"]),
            "cash_amount": round_coin(row["cash_amount"]),
            "related_order_id": safe_int(row["related_order_id"], 0),
            "status": row["status"] or "completed",
            "note": row["note"] or "",
            "created_at": row["created_at"] or "",
        }
        for row in rows
    ]


def recharge_buddy_coin(username, amount, note="玩家充值", related_order_id=0):
    user = get_user(username)
    if not user:
        return False, "用户不存在。"
    coins = round_coin(amount)
    if coins <= 0:
        return False, "充值数量必须大于 0。"
    wallet = get_wallet_snapshot(user)
    wallet["balance"] = round_coin(wallet["balance"] + coins)
    save_wallet_snapshot(username, wallet)
    add_wallet_transaction(
        username,
        "recharge",
        coins,
        cash_amount=round_coin(coins * BUDDY_COIN_TO_CASH_RATE),
        note=note,
        related_order_id=related_order_id,
    )
    return True, ""


def wallet_recharge_processed(username, session_id):
    row = execute_query(
        (
            f"SELECT id FROM wallet_transactions WHERE username = {placeholder()} "
            f"AND tx_type = {placeholder()} AND note LIKE {placeholder()} LIMIT 1"
        ),
        ((username or "").strip(), "recharge", f"%stripe_session:{(session_id or '').strip()}%"),
        fetchone=True,
    )
    return bool(row)


def create_wallet_recharge_checkout_session(username, coin_amount):
    coins = round_coin(coin_amount)
    if coins <= 0:
        return False, "充值数量必须大于 0。", ""
    if not stripe_is_configured():
        return False, "Stripe 未配置：请设置有效的 STRIPE_SECRET_KEY。", ""
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": "GameBuddy 巴迪币充值"},
                        "unit_amount": int(round_coin(coins * BUDDY_COIN_TO_CASH_RATE) * 100),
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=url_for("wallet_recharge_success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=url_for("wallet_recharge_cancel", _external=True),
            metadata={
                "flow": "wallet_recharge",
                "username": username,
                "coin_amount": stringify_price(coins),
            },
        )
        checkout_url = ""
        if isinstance(checkout_session, dict):
            checkout_url = (checkout_session.get("url") or "").strip()
        else:
            checkout_url = (getattr(checkout_session, "url", "") or "").strip()
        if not checkout_url:
            return False, "Stripe 返回的充值会话缺少跳转地址。", ""
        return True, "", checkout_url
    except Exception as exc:
        return False, f"创建 Stripe 充值会话失败：{exc}", ""


def withdraw_buddy_coin(username, amount, note="余额提现", role_hint=""):
    user = get_user(username)
    if not user:
        return False, "用户不存在。"
    role = role_hint or user.get("role")
    if role not in {"merchant", "booster"}:
        return False, "当前身份不支持提现。"
    coins = round_coin(amount)
    if coins <= 0:
        return False, "提现数量必须大于 0。"
    wallet = get_wallet_snapshot(user)
    if wallet["available"] < coins:
        return False, "可提现巴迪币不足。"
    wallet["balance"] = round_coin(wallet["balance"] - coins)
    save_wallet_snapshot(username, wallet)
    add_wallet_transaction(
        username,
        "withdraw",
        -coins,
        cash_amount=round_coin(coins * WITHDRAW_CASH_PER_COIN),
        note=note,
    )
    return True, ""


def withdraw_buddy_coin_via_stripe(username, amount, note="余额提现", role_hint=""):
    user = get_user(username)
    if not user:
        return False, "用户不存在。"
    role = role_hint or user.get("role")
    if role not in {"merchant", "booster"}:
        return False, "当前身份不支持提现。"
    coins = round_coin(amount)
    if coins <= 0:
        return False, "提现数量必须大于 0。"
    wallet = get_wallet_snapshot(user)
    if wallet["available"] < coins:
        return False, "可提现巴迪币不足。"
    if not stripe_is_configured():
        return False, "Stripe 未配置：请设置有效的 STRIPE_SECRET_KEY。"

    cash_amount = round_coin(coins * WITHDRAW_CASH_PER_COIN)
    payout_amount_cents = safe_int(round_coin(cash_amount * 100), 0)
    if payout_amount_cents <= 0:
        return False, "提现金额过小，无法发起 Stripe 提现。"
    payout_currency = (os.environ.get("STRIPE_PAYOUT_CURRENCY") or "usd").strip().lower() or "usd"
    # 币种配置说明：
    # STRIPE_PAYOUT_CURRENCY 可在 .env 文件中设置，如 usd、cny、eur 等，需与 Stripe 后台已绑定的外部账户币种一致。
    # 例如：

    try:
        payout = stripe.Payout.create(
            amount=payout_amount_cents,
            currency=payout_currency,
            metadata={
                "flow": "wallet_withdraw",
                "username": username,
                "role": role,
                "coin_amount": stringify_price(coins),
                "cash_amount": stringify_price(cash_amount),
            },
            description=f"GameBuddy {username} withdraw {stringify_price(coins)} coin",
        )
    except Exception as exc:
        message = str(exc)
        if "don't have any external accounts in that currency" in message:
            return (
                False,
                (
                    f"Stripe 提现失败：当前 Stripe 账号未绑定可接收 {payout_currency.upper()} 的外部账户。\n"
                    f"【操作指引】请登录 Stripe Dashboard，依次进入：设置 > 银行账户和调度 > 添加外部账户，确保已绑定支持 {payout_currency.upper()} 的银行卡/银行账户。\n"
                    f"如需更换币种，请在 .env 文件中设置 STRIPE_PAYOUT_CURRENCY=目标币种（如 usd、cny），并确保 Stripe 后台已绑定该币种账户。"
                ),
            )
        if "currency" in message and "is not supported" in message:
            return (
                False,
                (
                    f"Stripe 提现失败：当前币种 {payout_currency.upper()} 不被支持。\n"
                    f"请检查 STRIPE_PAYOUT_CURRENCY 设置，或在 Stripe 后台确认支持的币种列表。"
                ),
            )
        return False, f"Stripe 提现失败：{exc}"

    payout_id = (payout.get("id") if isinstance(payout, dict) else getattr(payout, "id", "")) or ""
    wallet["balance"] = round_coin(wallet["balance"] - coins)
    save_wallet_snapshot(username, wallet)
    add_wallet_transaction(
        username,
        "withdraw",
        -coins,
        cash_amount=cash_amount,
        note=f"{note} stripe_payout:{payout_id}".strip(),
    )
    return True, payout_id


def collect_order_payment_in_buddy_coin(player_username, store_owner_username, order_amount, related_order_id=0):
    player = get_user(player_username)
    merchant = get_user(store_owner_username)
    if not player or player.get("role") != "player":
        return False, "玩家账号不存在。"
    if not merchant or merchant.get("role") != "merchant":
        return False, "店铺账号不存在。"
    amount = round_coin(order_amount)
    if amount <= 0:
        return False, "订单金额无效。"

    player_wallet = get_wallet_snapshot(player)
    if player_wallet["available"] < amount:
        return False, f"巴迪币余额不足，当前可用 {player_wallet['available']}。"

    booster_share = round_coin(amount * BOOSTER_REVENUE_SHARE)
    merchant_wallet = get_wallet_snapshot(merchant)

    player_wallet["balance"] = round_coin(player_wallet["balance"] - amount)
    merchant_wallet["balance"] = round_coin(merchant_wallet["balance"] + amount)
    merchant_wallet["locked"] = round_coin(merchant_wallet["locked"] + booster_share)

    save_wallet_snapshot(player_username, player_wallet)
    save_wallet_snapshot(store_owner_username, merchant_wallet)

    add_wallet_transaction(
        player_username,
        "order_payment",
        -amount,
        related_order_id=related_order_id,
        note=f"订单支付 #{related_order_id}" if related_order_id else "订单支付",
    )
    add_wallet_transaction(
        store_owner_username,
        "order_income",
        amount,
        related_order_id=related_order_id,
        note=f"收到订单收入 #{related_order_id}" if related_order_id else "收到订单收入",
    )
    return True, ""


def settle_order_booster_share(order, booster_username, reviewer_username=""):
    if not order:
        return False, "订单不存在。"
    if safe_int(order.get("booster_coin_settled"), 0):
        return True, ""
    store_owner = (order.get("store_owner") or "").strip()
    if not store_owner:
        return False, "订单缺少店铺归属。"
    merchant = get_user(store_owner)
    booster = get_user((booster_username or "").strip())
    if not merchant or merchant.get("role") != "merchant":
        return False, "店铺账号不存在。"
    if not booster or booster.get("role") != "booster":
        return False, "打手账号不存在。"

    total_coin = round_coin(order.get("coin_amount") or order.get("price") or 0)
    share_coin = round_coin(order.get("booster_coin_share") or total_coin * BOOSTER_REVENUE_SHARE)
    if share_coin <= 0:
        return False, "订单分账金额无效。"
    if total_coin <= 0:
        return False, "订单金额无效，无法完成分账。"

    payment_status = (order.get("payment_status") or "").strip()
    order_id = safe_int(order.get("id"), 0)
    booster_wallet = get_wallet_snapshot(booster)

    if payment_status == "巴迪币已支付":
        merchant_wallet = get_wallet_snapshot(merchant)
        if merchant_wallet["locked"] < share_coin or merchant_wallet["balance"] < share_coin:
            return False, "店铺可分账余额不足，请先补充巴迪币后再完成订单。"

        merchant_wallet["locked"] = round_coin(max(merchant_wallet["locked"] - share_coin, 0.0))
        merchant_wallet["balance"] = round_coin(merchant_wallet["balance"] - share_coin)
        booster_wallet["balance"] = round_coin(booster_wallet["balance"] + share_coin)

        save_wallet_snapshot(store_owner, merchant_wallet)
        save_wallet_snapshot(booster["username"], booster_wallet)

        add_wallet_transaction(
            store_owner,
            "booster_share_paid",
            -share_coin,
            related_order_id=order_id,
            note=f"订单 #{order_id} 分账给打手",
        )
        add_wallet_transaction(
            booster["username"],
            "booster_income",
            share_coin,
            related_order_id=order_id,
            note=f"订单 #{order_id} 服务收入",
        )
    elif payment_status == "已支付":
        merchant_wallet = get_wallet_snapshot(merchant)
        merchant_share = round_coin(max(total_coin - share_coin, 0.0))

        merchant_wallet["balance"] = round_coin(merchant_wallet["balance"] + merchant_share)
        booster_wallet["balance"] = round_coin(booster_wallet["balance"] + share_coin)

        save_wallet_snapshot(store_owner, merchant_wallet)
        save_wallet_snapshot(booster["username"], booster_wallet)

        add_wallet_transaction(
            store_owner,
            "order_income_settled",
            merchant_share,
            related_order_id=order_id,
            note=f"订单 #{order_id} Stripe 分账入账",
        )
        add_wallet_transaction(
            booster["username"],
            "booster_income",
            share_coin,
            related_order_id=order_id,
            note=f"订单 #{order_id} Stripe 服务收入",
        )
    else:
        return False, "当前订单支付状态不支持分账。"

    update_order(
        order_id,
        {
            "booster": booster["username"],
            "assigned_booster": booster["username"],
            "coin_amount": stringify_price(total_coin),
            "booster_coin_share": stringify_price(share_coin),
            "booster_coin_settled": 1,
            "admin_note": (order.get("admin_note") or "") + ("\n" if order.get("admin_note") else "") + f"分账完成：{now_text()} by {(reviewer_username or SYSTEM_USERNAME)}",
        },
    )
    return True, ""


def refund_order_buddy_coin(order, reason="订单退款", operator_username=""):
    if not order:
        return False, "订单不存在。"
    payment_status = (order.get("payment_status") or "").strip()
    if payment_status in {"巴迪币已退款", "已退款"}:
        return True, ""

    order_id = safe_int(order.get("id"), 0)
    amount = round_coin(order.get("coin_amount") or order.get("price") or 0)
    if amount <= 0:
        return False, "订单退款金额无效。"
    player_username = (order.get("player") or "").strip()
    store_owner = (order.get("store_owner") or "").strip()
    if not player_username or not store_owner:
        return False, "订单缺少退款对象。"

    player = get_user(player_username)
    merchant = get_user(store_owner)
    if not player or not merchant:
        return False, "退款对象账号不存在。"

    merchant_wallet = get_wallet_snapshot(merchant)
    player_wallet = get_wallet_snapshot(player)
    if merchant_wallet["balance"] < amount:
        return False, "店铺余额不足，无法执行退款。"

    locked_delta = round_coin(order.get("booster_coin_share") or amount * BOOSTER_REVENUE_SHARE)
    merchant_wallet["balance"] = round_coin(merchant_wallet["balance"] - amount)
    merchant_wallet["locked"] = round_coin(max(merchant_wallet["locked"] - locked_delta, 0.0))
    player_wallet["balance"] = round_coin(player_wallet["balance"] + amount)

    save_wallet_snapshot(store_owner, merchant_wallet)
    save_wallet_snapshot(player_username, player_wallet)

    add_wallet_transaction(
        store_owner,
        "order_refund_out",
        -amount,
        related_order_id=order_id,
        note=f"订单 #{order_id} 退款支出",
    )
    add_wallet_transaction(
        player_username,
        "order_refund_in",
        amount,
        related_order_id=order_id,
        note=f"订单 #{order_id} 退款到账",
    )

    update_order(
        order_id,
        {
            "payment_status": "巴迪币已退款",
            "admin_note": (order.get("admin_note") or "") + ("\n" if order.get("admin_note") else "") + f"退款完成：{reason} by {(operator_username or SYSTEM_USERNAME)}",
        },
    )
    return True, ""


@app.context_processor
def inject_helpers():
    username = session.get("username")
    role = session.get("role")
    show_booster_store_apply_shortcut = False
    if role == "booster" and username:
        try:
            show_booster_store_apply_shortcut = should_redirect_booster_to_store_application(username)
        except Exception:
            show_booster_store_apply_shortcut = False
    icons_dir = os.path.join(APP_BASE_DIR, "static", "images", "games")
    games_icons_version = 0
    try:
        if os.path.isdir(icons_dir):
            for filename in os.listdir(icons_dir):
                path = os.path.join(icons_dir, filename)
                if os.path.isfile(path):
                    games_icons_version = max(games_icons_version, int(os.path.getmtime(path)))
    except OSError:
        games_icons_version = 0
    return {
        "csrf_token": get_csrf_token(),
        "order_status_class": order_status_class,
        "payment_status_class": payment_status_class,
        "complaint_status_class": complaint_status_class,
        "role_label": role_label,
        "format_price_text": format_price_text,
        "store_theme_options": STORE_THEME_OPTIONS,
        "dock_message_endpoint": message_center_endpoint_for_role(role),
        "dock_servers": get_dock_store_servers(username, role),
        "show_booster_store_apply_shortcut": show_booster_store_apply_shortcut,
        "games_icons_version": games_icons_version,
    }


def message_center_endpoint_for_role(role):
    mapping = {
        "player": "player_chats",
        "booster": "booster_chats",
        "merchant": "merchant_chats",
        "admin": "admin_home",
    }
    return mapping.get(role, "login")


def normalize_string_list(raw_value):
    if not raw_value:
        return []
    if isinstance(raw_value, (list, tuple, set)):
        candidates = list(raw_value)
    elif isinstance(raw_value, str):
        value = raw_value.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            candidates = parsed
        else:
            candidates = value.split(",")
    else:
        return []

    normalized = []
    seen = set()
    for item in candidates:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def get_contacted_store_slugs(profile):
    return normalize_string_list((profile or {}).get("contacted_stores", []))


def remember_contacted_store(profile, store_slug):
    next_profile = dict(profile or {})
    slugs = get_contacted_store_slugs(next_profile)
    if store_slug and store_slug not in slugs:
        slugs.append(store_slug)
    next_profile["contacted_stores"] = slugs
    return next_profile


def get_chat_partner_names(username):
    rows = execute_query(
        f"""
        SELECT sender, receiver
        FROM messages
        WHERE type = {placeholder()}
          AND (sender = {placeholder()} OR receiver = {placeholder()})
        ORDER BY id DESC
        """,
        ("chat", username, username),
        fetchall=True,
    )
    partner_names = []
    seen = set()
    for row in rows:
        partner_name = row["receiver"] if row["sender"] == username else row["sender"]
        if not partner_name or partner_name == username or partner_name in seen:
            continue
        seen.add(partner_name)
        partner_names.append(partner_name)
    return partner_names


def get_dock_store_servers(username, role):
    if not username:
        return []

    stores = []
    seen = set()

    def add_store(store):
        if not store:
            return
        slug = str(store.get("slug", "")).strip()
        if not slug or slug in seen:
            return
        card = build_store_card(store)
        seen.add(slug)
        stores.append(
            {
                "slug": card["slug"],
                "name": card["name"],
                "logo_url": card["logo_url"],
                "logo_text": card["logo_text"],
                "owner_username": card["owner_username"],
            }
        )

    if role == "player":
        user = get_user(username)
        if not user:
            return []
        for store_slug in get_contacted_store_slugs(user.get("profile", {})):
            add_store(get_store_by_slug(store_slug))
        for partner_name in get_chat_partner_names(username):
            partner_user = get_user(partner_name)
            if partner_user and partner_user["role"] == "merchant":
                add_store(get_store_by_owner(partner_name))
    elif role == "merchant":
        add_store(get_store_by_owner(username))

    return stores


def dashboard_endpoint_for_role(role):
    mapping = {
        "player": "home",
        "booster": "booster_home",
        "merchant": "merchant_home",
        "admin": "admin_home",
    }
    return mapping.get(role, "home")


def service_dashboard_path(role):
    mapping = {
        "player": "/service/dashboard",
        "booster": "/service/dashboard",
        "merchant": "/service/dashboard",
        "admin": "/service/dashboard",
    }
    return mapping.get(role, "/service")


def should_redirect_booster_to_store_application(username):
    user = get_user((username or "").strip())
    if not user or user.get("role") != "booster":
        return False

    profile = dict(user.get("profile") or {})
    if get_store_for_profile(profile):
        return False

    # 未绑定店铺的打手，登录后优先引导到店铺申请页。
    return True


def redirect_to_dashboard():
    if session.get("role") == "booster" and should_redirect_booster_to_store_application(session.get("username")):
        if not session.get("booster_store_apply_prompted"):
            flash("平台审核已通过，请先完成店铺入驻申请。", "info")
            session["booster_store_apply_prompted"] = True
        return redirect(url_for("booster_apply_store"))
    endpoint = dashboard_endpoint_for_role(session.get("role"))
    return redirect(url_for(endpoint))


def log_user_in(user):
    session["username"] = user["username"]
    session["role"] = user["role"]
    session.pop("booster_store_apply_prompted", None)


def current_user():
    username = (session.get("username") or "").strip()
    if not username:
        return None
    return get_user(username)


def clear_auth_onboarding():
    session.pop("auth_onboarding", None)


def get_auth_onboarding():
    onboarding = session.get("auth_onboarding")
    return onboarding if isinstance(onboarding, dict) else None


def start_auth_onboarding(payload):
    session["auth_onboarding"] = payload


def resolve_user_for_login(identifier):
    value = (identifier or "").strip()
    if not value:
        return None
    phone_user = get_user_by_phone(value)
    if phone_user:
        return phone_user
    email_user = get_user_by_email(value)
    if email_user:
        return email_user
    return get_user(value)


def password_matches(stored_password, raw_password):
    stored = (stored_password or "").strip()
    candidate = (raw_password or "").strip()
    if not stored or not candidate:
        return False
    if password_is_hashed(stored):
        return check_password_hash(stored, candidate)
    return stored == candidate


def admin_password_matches(raw_password):
    configured_password = (ADMIN_REGISTER_PASSWORD or "").strip()
    candidate = (raw_password or "").strip()
    if not configured_password or not candidate:
        return False
    return secrets.compare_digest(configured_password, candidate)


def render_auth_gateway(active_panel="login"):
    requested_method = (request.args.get("method", "email") or "email").strip().lower()
    if requested_method not in {"email", "phone"}:
        requested_method = "email"
    return render_template(
        "auth_gateway.html",
        active_panel=active_panel,
        social_providers=SOCIAL_PROVIDER_LABELS,
        default_login_method=requested_method,
        launch_image_url=url_for("static", filename="images/gamebuddy-launch-source.png"),
    )


def role_required(*roles):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            username = session.get("username")
            role = session.get("role")
            if not username:
                flash("请先登录后再继续。", "warning")
                return redirect(url_for("login"))
            if roles and role not in roles:
                flash("你没有权限访问该页面。", "warning")
                return redirect_to_dashboard()
            user = get_user(username)
            if not user:
                session.clear()
                flash("账号不存在，请重新登录。", "warning")
                return redirect(url_for("login"))
            if user.get("banned"):
                session.clear()
                flash("账号已被封禁。", "danger")
                return redirect(url_for("login"))
            return func(*args, **kwargs)

        return wrapper

    return decorator


def get_db():
    db = getattr(g, "_database", None)
    if db is not None:
        return db
    if is_postgres():
        if psycopg2 is None:
            raise RuntimeError("DATABASE_URL 已配置，但当前环境缺少 psycopg2。")
        try:
            db = psycopg2.connect(
                DATABASE_URL,
                cursor_factory=RealDictCursor,
                connect_timeout=3,
            )
        except Exception as exc:
            print(f"[DEBUG] PostgreSQL unavailable, fallback to sqlite: {exc}", file=sys.stderr)
            db = sqlite3.connect(DATABASE)
            db.row_factory = sqlite3.Row
    else:
        db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    g._database = db
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()
        g._database = None


def execute_query(sql, params=(), fetchone=False, fetchall=False, commit=False):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(sql, params)
    result = None
    if fetchone:
        result = cursor.fetchone()
    elif fetchall:
        result = cursor.fetchall()
    if commit:
        db.commit()
    cursor.close()
    return result


def table_has_column(table_name, column_name):
    db = get_db()
    cursor = db.cursor()
    if is_postgres():
        cursor.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
            (table_name, column_name),
        )
        exists = cursor.fetchone() is not None
    else:
        cursor.execute(f"PRAGMA table_info({table_name})")
        rows = cursor.fetchall()
        exists = any((row["name"] if isinstance(row, sqlite3.Row) else row[1]) == column_name for row in rows)
    cursor.close()
    return exists


def ensure_column(table_name, column_name, definition):
    if table_has_column(table_name, column_name):
        return
    sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
    execute_query(sql, commit=True)


def init_db():
    user_table_sql = """
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            banned INTEGER NOT NULL DEFAULT 0,
            profile TEXT DEFAULT '{}'
        )
    """
    order_table_sql = """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player TEXT NOT NULL,
            booster TEXT NOT NULL,
            store_id TEXT DEFAULT '',
            store_owner TEXT DEFAULT '',
            store_name TEXT DEFAULT '',
            assigned_booster TEXT DEFAULT '',
            assigned_booster_name TEXT DEFAULT '',
            game TEXT,
            detail TEXT,
            status TEXT,
            price TEXT,
            rating TEXT,
            comment TEXT,
            complaint TEXT,
            service_type TEXT DEFAULT '',
            target_rank TEXT DEFAULT '',
            duration TEXT DEFAULT '',
            preferred_time TEXT DEFAULT '',
            payment_status TEXT DEFAULT '未支付',
            complaint_status TEXT DEFAULT '无投诉',
            complaint_reply TEXT DEFAULT '',
            admin_note TEXT DEFAULT '',
            payment_session_id TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            FOREIGN KEY(player) REFERENCES users(username),
            FOREIGN KEY(booster) REFERENCES users(username)
        )
    """
    message_table_sql = """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            receiver TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            type TEXT NOT NULL,
            FOREIGN KEY(sender) REFERENCES users(username),
            FOREIGN KEY(receiver) REFERENCES users(username)
        )
    """
    store_table_sql = """
        CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_username TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            slug TEXT DEFAULT '',
            tagline TEXT DEFAULT '',
            description TEXT DEFAULT '',
            games TEXT DEFAULT '',
            city TEXT DEFAULT '',
            min_price TEXT DEFAULT '',
            logo_path TEXT DEFAULT '',
            cover_path TEXT DEFAULT '',
            theme TEXT DEFAULT 'graphite',
            badge TEXT DEFAULT '',
            contact_note TEXT DEFAULT '',
            is_featured INTEGER NOT NULL DEFAULT 0,
            approval_status TEXT DEFAULT 'pending',
            review_note TEXT DEFAULT '',
            reviewed_at TEXT DEFAULT '',
            reviewed_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT '',
            FOREIGN KEY(owner_username) REFERENCES users(username)
        )
    """
    booster_application_table_sql = """
        CREATE TABLE IF NOT EXISTS booster_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT DEFAULT '',
            auth_provider TEXT DEFAULT 'local',
            social_id TEXT DEFAULT '',
            game_account TEXT DEFAULT '',
            proof_image_path TEXT DEFAULT '',
            profile_json TEXT DEFAULT '{}',
            status TEXT DEFAULT 'pending',
            review_note TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            reviewed_at TEXT DEFAULT '',
            reviewed_by TEXT DEFAULT ''
        )
    """
    merchant_application_table_sql = """
        CREATE TABLE IF NOT EXISTS merchant_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT DEFAULT '',
            auth_provider TEXT DEFAULT 'local',
            social_id TEXT DEFAULT '',
            store_name TEXT DEFAULT '',
            store_city TEXT DEFAULT '',
            business_license_path TEXT DEFAULT '',
            id_proof_path TEXT DEFAULT '',
            profile_json TEXT DEFAULT '{}',
            status TEXT DEFAULT 'pending',
            review_note TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            reviewed_at TEXT DEFAULT '',
            reviewed_by TEXT DEFAULT ''
        )
    """
    wallet_transaction_table_sql = """
        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            tx_type TEXT NOT NULL,
            coin_amount REAL NOT NULL DEFAULT 0,
            cash_amount REAL NOT NULL DEFAULT 0,
            related_order_id INTEGER NOT NULL DEFAULT 0,
            status TEXT DEFAULT 'completed',
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            FOREIGN KEY(username) REFERENCES users(username)
        )
    """

    if is_postgres():
        order_table_sql = order_table_sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        message_table_sql = """
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                sender TEXT NOT NULL,
                receiver TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                type TEXT NOT NULL,
                FOREIGN KEY(sender) REFERENCES users(username),
                FOREIGN KEY(receiver) REFERENCES users(username)
            )
        """
        store_table_sql = store_table_sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        booster_application_table_sql = booster_application_table_sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        merchant_application_table_sql = merchant_application_table_sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        wallet_transaction_table_sql = wallet_transaction_table_sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")

    execute_query(user_table_sql, commit=True)
    execute_query(order_table_sql, commit=True)
    execute_query(message_table_sql, commit=True)
    execute_query(store_table_sql, commit=True)
    execute_query(booster_application_table_sql, commit=True)
    execute_query(merchant_application_table_sql, commit=True)
    execute_query(wallet_transaction_table_sql, commit=True)

    for column_name, definition in [
        ("email", "TEXT DEFAULT ''"),
        ("phone", "TEXT DEFAULT ''"),
        ("auth_provider", "TEXT DEFAULT 'local'"),
        ("social_id", "TEXT DEFAULT ''"),
        ("created_at", "TEXT DEFAULT ''"),
    ]:
        ensure_column("users", column_name, definition)

    for column_name, definition in [
        ("store_id", "TEXT DEFAULT ''"),
        ("store_owner", "TEXT DEFAULT ''"),
        ("store_name", "TEXT DEFAULT ''"),
        ("assigned_booster", "TEXT DEFAULT ''"),
        ("assigned_booster_name", "TEXT DEFAULT ''"),
        ("service_type", "TEXT DEFAULT ''"),
        ("target_rank", "TEXT DEFAULT ''"),
        ("duration", "TEXT DEFAULT ''"),
        ("preferred_time", "TEXT DEFAULT ''"),
        ("payment_status", "TEXT DEFAULT '未支付'"),
        ("complaint_status", "TEXT DEFAULT '无投诉'"),
        ("complaint_reply", "TEXT DEFAULT ''"),
        ("admin_note", "TEXT DEFAULT ''"),
        ("payment_session_id", "TEXT DEFAULT ''"),
        ("coin_amount", "TEXT DEFAULT '0'"),
        ("booster_coin_share", "TEXT DEFAULT '0'"),
        ("booster_coin_settled", "INTEGER NOT NULL DEFAULT 0"),
        ("created_at", "TEXT DEFAULT ''"),
    ]:
        ensure_column("orders", column_name, definition)

    for column_name, definition in [
        ("slug", "TEXT DEFAULT ''"),
        ("tagline", "TEXT DEFAULT ''"),
        ("description", "TEXT DEFAULT ''"),
        ("games", "TEXT DEFAULT ''"),
        ("city", "TEXT DEFAULT ''"),
        ("min_price", "TEXT DEFAULT ''"),
        ("logo_path", "TEXT DEFAULT ''"),
        ("cover_path", "TEXT DEFAULT ''"),
        ("theme", "TEXT DEFAULT 'graphite'"),
        ("badge", "TEXT DEFAULT ''"),
        ("contact_note", "TEXT DEFAULT ''"),
        ("is_featured", "INTEGER NOT NULL DEFAULT 0"),
        ("approval_status", "TEXT DEFAULT 'pending'"),
        ("review_note", "TEXT DEFAULT ''"),
        ("reviewed_at", "TEXT DEFAULT ''"),
        ("reviewed_by", "TEXT DEFAULT ''"),
        ("created_at", "TEXT DEFAULT ''"),
        ("updated_at", "TEXT DEFAULT ''"),
    ]:
        ensure_column("stores", column_name, definition)

    for column_name, definition in [
        ("store_id", "TEXT DEFAULT ''"),
        ("store_owner_username", "TEXT DEFAULT ''"),
        ("store_name", "TEXT DEFAULT ''"),
        ("display_name", "TEXT DEFAULT ''"),
        ("phone", "TEXT DEFAULT ''"),
        ("auth_provider", "TEXT DEFAULT 'local'"),
        ("social_id", "TEXT DEFAULT ''"),
        ("game_account", "TEXT DEFAULT ''"),
        ("proof_image_path", "TEXT DEFAULT ''"),
        ("profile_json", "TEXT DEFAULT '{}'"),
        ("status", "TEXT DEFAULT 'pending'"),
        ("review_note", "TEXT DEFAULT ''"),
        ("created_at", "TEXT DEFAULT ''"),
        ("reviewed_at", "TEXT DEFAULT ''"),
        ("reviewed_by", "TEXT DEFAULT ''"),
    ]:
        ensure_column("booster_applications", column_name, definition)

    for column_name, definition in [
        ("phone", "TEXT DEFAULT ''"),
        ("auth_provider", "TEXT DEFAULT 'local'"),
        ("social_id", "TEXT DEFAULT ''"),
        ("store_name", "TEXT DEFAULT ''"),
        ("store_city", "TEXT DEFAULT ''"),
        ("business_license_path", "TEXT DEFAULT ''"),
        ("id_proof_path", "TEXT DEFAULT ''"),
        ("profile_json", "TEXT DEFAULT '{}'"),
        ("status", "TEXT DEFAULT 'pending'"),
        ("review_note", "TEXT DEFAULT ''"),
        ("created_at", "TEXT DEFAULT ''"),
        ("reviewed_at", "TEXT DEFAULT ''"),
        ("reviewed_by", "TEXT DEFAULT ''"),
    ]:
        ensure_column("merchant_applications", column_name, definition)


def row_to_user(row):
    if row is None:
        return None
    profile = parse_profile(row["profile"])
    return {
        "username": row["username"],
        "password": row["password"],
        "role": row["role"],
        "banned": bool(row["banned"]),
        "email": normalize_email(row["email"] if "email" in row.keys() else ""),
        "phone": normalize_phone(row["phone"] if "phone" in row.keys() else ""),
        "auth_provider": (row["auth_provider"] if "auth_provider" in row.keys() else "local") or "local",
        "social_id": (row["social_id"] if "social_id" in row.keys() else "") or "",
        "created_at": (row["created_at"] if "created_at" in row.keys() else "") or "",
        "profile": profile,
        "failed_login_attempts": safe_int(profile.get("failed_login_attempts"), default=0),
        "lock_reason": profile.get("lock_reason", ""),
    }


def row_to_order(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "player": row["player"],
        "booster": row["booster"],
        "store_id": row["store_id"] if "store_id" in row.keys() else "",
        "store_owner": row["store_owner"] if "store_owner" in row.keys() else "",
        "store_name": row["store_name"] if "store_name" in row.keys() else "",
        "assigned_booster": row["assigned_booster"] if "assigned_booster" in row.keys() else (row["booster"] or ""),
        "assigned_booster_name": row["assigned_booster_name"] if "assigned_booster_name" in row.keys() else "",
        "game": row["game"] or "",
        "detail": row["detail"] or "",
        "status": row["status"] or "",
        "price": row["price"] or "",
        "rating": row["rating"] or "",
        "comment": row["comment"] or "",
        "complaint": row["complaint"] or "",
        "service_type": row["service_type"] or "",
        "target_rank": row["target_rank"] or "",
        "duration": row["duration"] or "",
        "preferred_time": row["preferred_time"] or "",
        "payment_status": row["payment_status"] or "未支付",
        "complaint_status": row["complaint_status"] or "无投诉",
        "complaint_reply": row["complaint_reply"] or "",
        "admin_note": row["admin_note"] or "",
        "payment_session_id": row["payment_session_id"] or "",
        "coin_amount": row["coin_amount"] if "coin_amount" in row.keys() else (row["price"] or "0"),
        "booster_coin_share": row["booster_coin_share"] if "booster_coin_share" in row.keys() else "0",
        "booster_coin_settled": safe_int(row["booster_coin_settled"] if "booster_coin_settled" in row.keys() else 0, 0),
        "created_at": row["created_at"] or "",
    }


def row_to_message(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "sender": row["sender"],
        "receiver": row["receiver"],
        "message": row["message"],
        "timestamp": str(row["timestamp"]),
        "type": row["type"],
    }


def row_to_store(row):
    if row is None:
        return None
    games = split_tags(row["games"] or "")
    return {
        "id": row["id"],
        "owner_username": row["owner_username"],
        "name": row["name"] or "",
        "slug": row["slug"] or "",
        "tagline": row["tagline"] or "",
        "description": row["description"] or "",
        "games": games,
        "games_text": " / ".join(games) if games else "",
        "city": row["city"] or "",
        "min_price": row["min_price"] or "",
        "logo_path": row["logo_path"] or "",
        "cover_path": row["cover_path"] or "",
        "logo_url": image_url(row["logo_path"] or ""),
        "cover_url": image_url(row["cover_path"] or ""),
        "theme": row["theme"] or "graphite",
        "badge": row["badge"] or "",
        "contact_note": row["contact_note"] or "",
        "is_featured": bool(row["is_featured"]),
        "approval_status": (row["approval_status"] if "approval_status" in row.keys() else "approved") or "approved",
        "review_note": (row["review_note"] if "review_note" in row.keys() else "") or "",
        "reviewed_at": (row["reviewed_at"] if "reviewed_at" in row.keys() else "") or "",
        "reviewed_by": (row["reviewed_by"] if "reviewed_by" in row.keys() else "") or "",
        "created_at": row["created_at"] or "",
        "updated_at": row["updated_at"] or "",
    }


def row_to_booster_application(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "username": row["username"] or "",
        "password": row["password"] or "",
        "store_id": (row["store_id"] if "store_id" in row.keys() else "") or "",
        "store_owner_username": (row["store_owner_username"] if "store_owner_username" in row.keys() else "") or "",
        "store_name": (row["store_name"] if "store_name" in row.keys() else "") or "",
        "display_name": (row["display_name"] if "display_name" in row.keys() else "") or "",
        "email": normalize_email(row["email"] or ""),
        "phone": normalize_phone(row["phone"] if "phone" in row.keys() else ""),
        "auth_provider": (row["auth_provider"] if "auth_provider" in row.keys() else "local") or "local",
        "social_id": (row["social_id"] if "social_id" in row.keys() else "") or "",
        "game_account": row["game_account"] or "",
        "proof_image_path": row["proof_image_path"] or "",
        "proof_image_url": image_url(row["proof_image_path"] or ""),
        "profile": parse_profile(row["profile_json"] if "profile_json" in row.keys() else ""),
        "status": row["status"] or "pending",
        "review_note": row["review_note"] or "",
        "created_at": row["created_at"] or "",
        "reviewed_at": row["reviewed_at"] or "",
        "reviewed_by": row["reviewed_by"] or "",
    }


def row_to_merchant_application(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "username": row["username"] or "",
        "password": row["password"] or "",
        "email": normalize_email(row["email"] or ""),
        "phone": normalize_phone(row["phone"] if "phone" in row.keys() else ""),
        "auth_provider": (row["auth_provider"] if "auth_provider" in row.keys() else "local") or "local",
        "social_id": (row["social_id"] if "social_id" in row.keys() else "") or "",
        "store_name": (row["store_name"] if "store_name" in row.keys() else "") or "",
        "store_city": (row["store_city"] if "store_city" in row.keys() else "") or "",
        "business_license_path": (row["business_license_path"] if "business_license_path" in row.keys() else "") or "",
        "business_license_url": image_url((row["business_license_path"] if "business_license_path" in row.keys() else "") or ""),
        "id_proof_path": (row["id_proof_path"] if "id_proof_path" in row.keys() else "") or "",
        "id_proof_url": image_url((row["id_proof_path"] if "id_proof_path" in row.keys() else "") or ""),
        "profile": parse_profile(row["profile_json"] if "profile_json" in row.keys() else ""),
        "status": row["status"] or "pending",
        "review_note": row["review_note"] or "",
        "created_at": row["created_at"] or "",
        "reviewed_at": row["reviewed_at"] or "",
        "reviewed_by": row["reviewed_by"] or "",
    }


def hash_password(password):
    return generate_password_hash(password)


def add_user(username, password, role, banned=False, profile=None, email="", phone="", auth_provider="local", social_id="", created_at=""):
    pwd_value = password if password_is_hashed(password) else hash_password(password)
    payload = (
        username,
        pwd_value,
        role,
        int(bool(banned)),
        serialize_profile(profile),
        normalize_email(email),
        normalize_phone(phone),
        (auth_provider or "local").strip() or "local",
        (social_id or "").strip(),
        created_at or now_text(),
    )
    sql = (
        f"INSERT INTO users (username, password, role, banned, profile, email, phone, auth_provider, social_id, created_at) VALUES ({placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()})"
        if is_postgres()
        else "INSERT OR REPLACE INTO users (username, password, role, banned, profile, email, phone, auth_provider, social_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    execute_query(sql, payload, commit=True)


def find_user_by_email(email):
    return get_user_by_email(email)


def get_user(username):
    row = execute_query(
        f"SELECT * FROM users WHERE username = {placeholder()}",
        (username,),
        fetchone=True,
    )
    return row_to_user(row)


def get_user_by_email(email):
    normalized_email = normalize_email(email)
    if not normalized_email:
        return None
    row = execute_query(
        f"SELECT * FROM users WHERE email = {placeholder()}",
        (normalized_email,),
        fetchone=True,
    )
    return row_to_user(row)


def get_user_by_phone(phone):
    normalized_phone = normalize_phone(phone)
    if not normalized_phone:
        return None
    row = execute_query(
        f"SELECT * FROM users WHERE phone = {placeholder()}",
        (normalized_phone,),
        fetchone=True,
    )
    return row_to_user(row)


def get_user_by_social(provider, social_id):
    provider = (provider or "").strip()
    social_id = (social_id or "").strip()
    if not provider or not social_id:
        return None
    row = execute_query(
        f"SELECT * FROM users WHERE auth_provider = {placeholder()} AND social_id = {placeholder()}",
        (provider, social_id),
        fetchone=True,
    )
    return row_to_user(row)


def all_users(include_system=False):
    rows = execute_query("SELECT * FROM users ORDER BY role, username", fetchall=True)
    users = [row_to_user(row) for row in rows]
    if not include_system:
        users = [user for user in users if user["username"] != SYSTEM_USERNAME]
    return users


def update_user(username, fields):
    if not fields:
        return
    assignments = []
    values = []
    for key, value in fields.items():
        if key == "profile":
            value = serialize_profile(value)
        if key == "banned":
            value = int(bool(value))
        if key == "password" and not password_is_hashed(value):
            value = hash_password(value)
        if key == "email":
            value = normalize_email(value)
        if key == "phone":
            value = normalize_phone(value)
        if key in {"auth_provider", "social_id"}:
            value = (value or "").strip()
        assignments.append(f"{key} = {placeholder()}")
        values.append(value)
    values.append(username)
    sql = f"UPDATE users SET {', '.join(assignments)} WHERE username = {placeholder()}"
    execute_query(sql, tuple(values), commit=True)


def mail_is_configured():
    return bool(MAIL_SERVER and MAIL_PORT and MAIL_FROM)


def send_email_message(to_email, subject, body):
    if not mail_is_configured():
        raise RuntimeError("邮件服务未配置，请先设置 MAIL_SERVER / MAIL_PORT / MAIL_USERNAME / MAIL_PASSWORD / MAIL_FROM。")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = MAIL_FROM
    message["To"] = to_email
    message.set_content(body)

    if MAIL_PORT == 465 and not MAIL_USE_TLS:
        with smtplib.SMTP_SSL(MAIL_SERVER, MAIL_PORT, context=ssl.create_default_context(), timeout=20) as server:
            if MAIL_USERNAME and MAIL_PASSWORD:
                server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(message)
        return

    with smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=20) as server:
        server.ehlo()
        if MAIL_USE_TLS:
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        if MAIL_USERNAME and MAIL_PASSWORD:
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(message)


def issue_password_reset_code(username, email):
    user = get_user(username)
    if not user:
        return ""
    code = f"{secrets.randbelow(1_000_000):06d}"
    profile = dict(user.get("profile") or {})
    profile["email"] = normalize_email(email)
    profile["password_reset_code_hash"] = hash_password(code)
    profile["password_reset_expires_at"] = (datetime.now() + timedelta(minutes=PASSWORD_RESET_CODE_TTL_MINUTES)).isoformat()
    profile["password_reset_requested_at"] = datetime.now().isoformat()
    update_user(username, {"email": normalize_email(email), "profile": profile})
    return code


def verify_password_reset_code(user, code):
    profile = dict(user.get("profile") or {})
    stored_hash = str(profile.get("password_reset_code_hash", "")).strip()
    expires_at_raw = str(profile.get("password_reset_expires_at", "")).strip()
    if not stored_hash:
        return False, "请先获取邮箱验证码。"
    if not code:
        return False, "请输入邮箱收到的验证码。"
    if not check_password_hash(stored_hash, code):
        return False, "验证码错误，请重新输入。"
    if not expires_at_raw:
        return False, "验证码已失效，请重新获取。"
    try:
        expires_at = datetime.fromisoformat(expires_at_raw)
    except ValueError:
        return False, "验证码已失效，请重新获取。"
    if datetime.now() > expires_at:
        return False, "验证码已过期，请重新获取。"
    return True, ""


def clear_password_reset_state(username):
    user = get_user(username)
    if not user:
        return
    profile = dict(user.get("profile") or {})
    profile.pop("password_reset_code_hash", None)
    profile.pop("password_reset_expires_at", None)
    profile.pop("password_reset_requested_at", None)
    update_user(username, {"profile": profile})


def send_password_reset_email(username, email):
    code = issue_password_reset_code(username, email)
    subject = "GameBuddy 密码重置验证码"
    body = (
        f"验证码：{code}\n"
        f"你好，{username}\n\n"
        f"你正在为 GameBuddy 账号申请重置密码。\n"
        f"有效期：{PASSWORD_RESET_CODE_TTL_MINUTES} 分钟。\n\n"
        "如果这不是你本人操作，请忽略此邮件，并尽快联系管理员。"
    )
    send_email_message(email, subject, body)
    return code


def send_booster_application_review_email(application, approved, review_note=""):
    if not application or not application.get("email"):
        return
    username = application.get("username", "")
    game_account = application.get("game_account", "")
    status_text = "审核通过" if approved else "审核未通过"
    subject = f"GameBuddy 打手申请{status_text}通知"
    body = (
        f"你好，{username}\n\n"
        f"你提交的打手申请（游戏账号：{game_account or '未填写'}）{status_text}。\n"
    )
    if approved:
        body += "管理员已通过审核，你现在可以使用该账号登录平台接单。\n"
    else:
        body += "本次申请未通过，系统不会创建打手账号。你可以根据审核意见调整资料后重新提交。\n"
    if review_note:
        body += f"审核意见：{review_note}\n"
    body += "\n此邮件由平台自动发送。"
    send_email_message(application["email"], subject, body)


def send_merchant_application_review_email(application, approved, review_note=""):
    if not application or not application.get("email"):
        return
    username = application.get("username", "")
    store_name = application.get("store_name", "")
    status_text = "审核通过" if approved else "审核未通过"
    subject = f"GameBuddy 商家入驻申请{status_text}通知"
    body = (
        f"你好，{username}\n\n"
        f"你提交的商家入驻申请（店铺名：{store_name or '未填写'}）{status_text}。\n"
    )
    if approved:
        body += "管理员已通过审核，你现在可以使用该账号登录并继续完善店铺。\n"
    else:
        body += "本次申请未通过，系统不会创建商家账号。你可以根据审核意见调整资料后重新提交。\n"
    if review_note:
        body += f"审核意见：{review_note}\n"
    body += "\n此邮件由平台自动发送。"
    send_email_message(application["email"], subject, body)


def record_failed_login_attempt(username):
    user = get_user(username)
    if not user:
        return 0, False
    profile = dict(user.get("profile") or {})
    attempts = safe_int(profile.get("failed_login_attempts"), default=0) + 1
    profile["failed_login_attempts"] = attempts
    if attempts >= MAX_LOGIN_ATTEMPTS:
        profile["lock_reason"] = "too_many_failed_password_attempts"
        update_user(username, {"profile": profile, "banned": True})
        return attempts, True
    update_user(username, {"profile": profile})
    return attempts, False


def clear_failed_login_attempts(username, *, unlock_account=False):
    user = get_user(username)
    if not user:
        return
    profile = dict(user.get("profile") or {})
    profile["failed_login_attempts"] = 0
    profile.pop("lock_reason", None)
    fields = {"profile": profile}
    if unlock_account:
        fields["banned"] = False
    update_user(username, fields)


def add_booster_application(
    username,
    password,
    email,
    game_account,
    proof_image_path,
    phone="",
    auth_provider="local",
    social_id="",
    store_id="",
    store_owner_username="",
    store_name="",
    display_name="",
    profile=None,
):
    password_value = password if password_is_hashed(password) else hash_password(password)
    execute_query(
        (
            f"INSERT INTO booster_applications (username, password, email, phone, auth_provider, social_id, game_account, proof_image_path, profile_json, store_id, store_owner_username, store_name, display_name, status, review_note, created_at, reviewed_at, reviewed_by) "
            f"VALUES ({placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()})"
        ),
        (
            username,
            password_value,
            normalize_email(email),
            normalize_phone(phone),
            (auth_provider or "local").strip() or "local",
            (social_id or "").strip(),
            game_account,
            proof_image_path,
            serialize_profile(profile),
            str(store_id or ""),
            (store_owner_username or "").strip(),
            (store_name or "").strip(),
            (display_name or "").strip(),
            "pending",
            "",
            now_text(),
            "",
            "",
        ),
        commit=True,
    )


def get_booster_application(application_id):
    row = execute_query(
        f"SELECT * FROM booster_applications WHERE id = {placeholder()}",
        (application_id,),
        fetchone=True,
    )
    return row_to_booster_application(row)


def get_booster_applications(status=None):
    params = []
    sql = "SELECT * FROM booster_applications"
    if status:
        sql += f" WHERE status = {placeholder()}"
        params.append(status)
    sql += " ORDER BY id DESC"
    rows = execute_query(sql, tuple(params), fetchall=True)
    return [row_to_booster_application(row) for row in rows]


def update_booster_application(application_id, fields):
    if not fields:
        return
    assignments = []
    values = []
    for key, value in fields.items():
        assignments.append(f"{key} = {placeholder()}")
        values.append(value)
    values.append(application_id)
    sql = f"UPDATE booster_applications SET {', '.join(assignments)} WHERE id = {placeholder()}"
    execute_query(sql, tuple(values), commit=True)


def find_pending_booster_application_by_username(username):
    row = execute_query(
        f"SELECT * FROM booster_applications WHERE username = {placeholder()} AND status = {placeholder()} ORDER BY id DESC",
        (username, "pending"),
        fetchone=True,
    )
    return row_to_booster_application(row)


def find_pending_booster_application_by_email(email):
    normalized = normalize_email(email)
    if not normalized:
        return None
    row = execute_query(
        f"SELECT * FROM booster_applications WHERE email = {placeholder()} AND status = {placeholder()} ORDER BY id DESC",
        (normalized, "pending"),
        fetchone=True,
    )
    return row_to_booster_application(row)


def find_latest_booster_application_by_username(username):
    normalized_username = (username or "").strip()
    if not normalized_username:
        return None
    row = execute_query(
        f"SELECT * FROM booster_applications WHERE username = {placeholder()} ORDER BY id DESC",
        (normalized_username,),
        fetchone=True,
    )
    return row_to_booster_application(row)


def add_merchant_application(
    username,
    password,
    email,
    phone="",
    auth_provider="local",
    social_id="",
    store_name="",
    store_city="",
    business_license_path="",
    id_proof_path="",
    profile=None,
):
    password_value = password if password_is_hashed(password) else hash_password(password)
    execute_query(
        (
            f"INSERT INTO merchant_applications (username, password, email, phone, auth_provider, social_id, store_name, store_city, business_license_path, id_proof_path, profile_json, status, review_note, created_at, reviewed_at, reviewed_by) "
            f"VALUES ({placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()})"
        ),
        (
            username,
            password_value,
            normalize_email(email),
            normalize_phone(phone),
            (auth_provider or "local").strip() or "local",
            (social_id or "").strip(),
            (store_name or "").strip(),
            (store_city or "").strip(),
            business_license_path,
            id_proof_path,
            serialize_profile(profile),
            "pending",
            "",
            now_text(),
            "",
            "",
        ),
        commit=True,
    )


def get_merchant_application(application_id):
    row = execute_query(
        f"SELECT * FROM merchant_applications WHERE id = {placeholder()}",
        (application_id,),
        fetchone=True,
    )
    return row_to_merchant_application(row)


def get_merchant_applications(status=None):
    params = []
    sql = "SELECT * FROM merchant_applications"
    if status:
        sql += f" WHERE status = {placeholder()}"
        params.append(status)
    sql += " ORDER BY id DESC"
    rows = execute_query(sql, tuple(params), fetchall=True)
    return [row_to_merchant_application(row) for row in rows]


def update_merchant_application(application_id, fields):
    if not fields:
        return
    assignments = []
    values = []
    for key, value in fields.items():
        assignments.append(f"{key} = {placeholder()}")
        values.append(value)
    values.append(application_id)
    sql = f"UPDATE merchant_applications SET {', '.join(assignments)} WHERE id = {placeholder()}"
    execute_query(sql, tuple(values), commit=True)


def find_pending_merchant_application_by_username(username):
    row = execute_query(
        f"SELECT * FROM merchant_applications WHERE username = {placeholder()} AND status = {placeholder()} ORDER BY id DESC",
        (username, "pending"),
        fetchone=True,
    )
    return row_to_merchant_application(row)


def find_pending_merchant_application_by_email(email):
    normalized = normalize_email(email)
    if not normalized:
        return None
    row = execute_query(
        f"SELECT * FROM merchant_applications WHERE email = {placeholder()} AND status = {placeholder()} ORDER BY id DESC",
        (normalized, "pending"),
        fetchone=True,
    )
    return row_to_merchant_application(row)


def find_latest_merchant_application(username, email):
    username = (username or "").strip()
    email = normalize_email(email)
    if not username or not email:
        return None
    row = execute_query(
        f"SELECT * FROM merchant_applications WHERE username = {placeholder()} AND email = {placeholder()} ORDER BY id DESC",
        (username, email),
        fetchone=True,
    )
    return row_to_merchant_application(row)


def find_latest_merchant_application_by_username(username):
    normalized_username = (username or "").strip()
    if not normalized_username:
        return None
    row = execute_query(
        f"SELECT * FROM merchant_applications WHERE username = {placeholder()} ORDER BY id DESC",
        (normalized_username,),
        fetchone=True,
    )
    return row_to_merchant_application(row)


def find_application_for_status_lookup(username, password):
    normalized_username = (username or "").strip()
    raw_password = (password or "").strip()
    if not normalized_username or not raw_password:
        return None

    matches = []
    booster_application = find_latest_booster_application_by_username(normalized_username)
    if booster_application and password_matches(booster_application.get("password", ""), raw_password):
        matches.append({"role": "booster", "application": booster_application})

    merchant_application = find_latest_merchant_application_by_username(normalized_username)
    if merchant_application and password_matches(merchant_application.get("password", ""), raw_password):
        matches.append({"role": "merchant", "application": merchant_application})

    if not matches:
        return None
    matches.sort(key=lambda item: item["application"].get("created_at", ""), reverse=True)
    return matches[0]


def delete_user(username):
    user = get_user(username)
    if user and user["role"] == "merchant":
        store = get_store_by_owner(username)
        if store:
            delete_store(store["id"])
        for booster in get_store_boosters(owner_username=username):
            booster_user = get_user(booster["username"])
            if not booster_user:
                continue
            profile = dict(booster_user.get("profile", {}))
            profile["store_id"] = ""
            profile["store_name"] = ""
            profile["managed_by"] = ""
            update_user(booster_user["username"], {"profile": profile})
    execute_query(
        f"DELETE FROM orders WHERE player = {placeholder()} OR booster = {placeholder()}",
        (username, username),
        commit=True,
    )
    execute_query(
        f"DELETE FROM messages WHERE sender = {placeholder()} OR receiver = {placeholder()}",
        (username, username),
        commit=True,
    )
    execute_query(
        f"DELETE FROM users WHERE username = {placeholder()}",
        (username,),
        commit=True,
    )


def slugify(value):
    text = (value or "").strip().lower()
    result = []
    last_dash = False
    for char in text:
        if char.isalnum() or char in {"-", "_"}:
            result.append(char)
            last_dash = False
        elif char in {" ", "/", "|"}:
            if not last_dash:
                result.append("-")
                last_dash = True
    slug = "".join(result).strip("-_")
    return slug or f"store-{uuid.uuid4().hex[:6]}"


def add_store(store_data):
    payload = {
        "owner_username": store_data.get("owner_username", ""),
        "name": store_data.get("name", ""),
        "slug": store_data.get("slug", ""),
        "tagline": store_data.get("tagline", ""),
        "description": store_data.get("description", ""),
        "games": store_data.get("games", ""),
        "city": store_data.get("city", ""),
        "min_price": store_data.get("min_price", ""),
        "logo_path": store_data.get("logo_path", ""),
        "cover_path": store_data.get("cover_path", ""),
        "theme": store_data.get("theme", "graphite"),
        "badge": store_data.get("badge", ""),
        "contact_note": store_data.get("contact_note", ""),
        "is_featured": int(bool(store_data.get("is_featured", False))),
        "approval_status": store_data.get("approval_status", "pending"),
        "review_note": store_data.get("review_note", ""),
        "reviewed_at": store_data.get("reviewed_at", ""),
        "reviewed_by": store_data.get("reviewed_by", ""),
        "created_at": store_data.get("created_at", now_text()),
        "updated_at": store_data.get("updated_at", now_text()),
    }
    params = tuple(payload.values())
    placeholders = ", ".join([placeholder()] * len(payload))
    sql = f"INSERT INTO stores ({', '.join(payload.keys())}) VALUES ({placeholders})"
    execute_query(sql, params, commit=True)


def get_store(store_id):
    row = execute_query(
        f"SELECT * FROM stores WHERE id = {placeholder()}",
        (store_id,),
        fetchone=True,
    )
    return row_to_store(row)


def get_store_by_owner(owner_username):
    row = execute_query(
        f"SELECT * FROM stores WHERE owner_username = {placeholder()}",
        (owner_username,),
        fetchone=True,
    )
    return row_to_store(row)


def get_store_by_slug(store_slug):
    row = execute_query(
        f"SELECT * FROM stores WHERE slug = {placeholder()}",
        (store_slug,),
        fetchone=True,
    )
    return row_to_store(row)


def unique_store_slug(base_value, exclude_store_id=None):
    candidate = slugify(base_value)
    existing = get_store_by_slug(candidate)
    if not existing or str(existing["id"]) == str(exclude_store_id):
        return candidate
    index = 2
    while True:
        next_candidate = f"{candidate}-{index}"
        existing = get_store_by_slug(next_candidate)
        if not existing or str(existing["id"]) == str(exclude_store_id):
            return next_candidate
        index += 1


def update_store(store_id, fields):
    if not fields:
        return
    assignments = []
    values = []
    for key, value in fields.items():
        if key == "is_featured":
            value = int(bool(value))
        assignments.append(f"{key} = {placeholder()}")
        values.append(value)
    values.append(store_id)
    sql = f"UPDATE stores SET {', '.join(assignments)} WHERE id = {placeholder()}"
    execute_query(sql, tuple(values), commit=True)


def delete_store(store_id):
    execute_query(
        f"DELETE FROM stores WHERE id = {placeholder()}",
        (store_id,),
        commit=True,
    )


def get_all_stores(featured_only=False):
    sql = "SELECT * FROM stores"
    params = ()
    if featured_only:
        sql += f" WHERE is_featured = {placeholder()}"
        params = (1,)
    sql += " ORDER BY is_featured DESC, id DESC"
    rows = execute_query(sql, params, fetchall=True)
    return [row_to_store(row) for row in rows]


def add_order(order_data):
    payload = {
        "player": order_data.get("player", ""),
        "booster": order_data.get("booster", ""),
        "store_id": str(order_data.get("store_id", "")),
        "store_owner": order_data.get("store_owner", ""),
        "store_name": order_data.get("store_name", ""),
        "assigned_booster": order_data.get("assigned_booster", ""),
        "assigned_booster_name": order_data.get("assigned_booster_name", ""),
        "game": order_data.get("game", ""),
        "detail": order_data.get("detail", ""),
        "status": order_data.get("status", "待接单"),
        "price": str(order_data.get("price", "")),
        "rating": order_data.get("rating", ""),
        "comment": order_data.get("comment", ""),
        "complaint": order_data.get("complaint", ""),
        "service_type": order_data.get("service_type", ""),
        "target_rank": order_data.get("target_rank", ""),
        "duration": order_data.get("duration", ""),
        "preferred_time": order_data.get("preferred_time", ""),
        "payment_status": order_data.get("payment_status", "未支付"),
        "complaint_status": order_data.get("complaint_status", "无投诉"),
        "complaint_reply": order_data.get("complaint_reply", ""),
        "admin_note": order_data.get("admin_note", ""),
        "payment_session_id": order_data.get("payment_session_id", ""),
        "coin_amount": str(order_data.get("coin_amount", order_data.get("price", "0"))),
        "booster_coin_share": str(order_data.get("booster_coin_share", "0")),
        "booster_coin_settled": safe_int(order_data.get("booster_coin_settled", 0), 0),
        "created_at": order_data.get("created_at", now_text()),
    }
    params = tuple(payload.values())
    placeholders = ", ".join([placeholder()] * len(payload))
    sql = f"""
        INSERT INTO orders ({', '.join(payload.keys())})
        VALUES ({placeholders})
    """
    execute_query(sql, params, commit=True)


def get_order(order_id):
    row = execute_query(
        f"SELECT * FROM orders WHERE id = {placeholder()}",
        (order_id,),
        fetchone=True,
    )
    return row_to_order(row)


def get_order_by_payment_session_id(payment_session_id):
    if not payment_session_id:
        return None
    row = execute_query(
        f"SELECT * FROM orders WHERE payment_session_id = {placeholder()}",
        (payment_session_id,),
        fetchone=True,
    )
    return row_to_order(row)


def update_order(order_id, fields):
    if not fields:
        return
    assignments = []
    values = []
    for key, value in fields.items():
        assignments.append(f"{key} = {placeholder()}")
        values.append(value)
    values.append(order_id)
    sql = f"UPDATE orders SET {', '.join(assignments)} WHERE id = {placeholder()}"
    execute_query(sql, tuple(values), commit=True)


def get_all_orders():
    rows = execute_query("SELECT * FROM orders ORDER BY id DESC", fetchall=True)
    return [row_to_order(row) for row in rows]


def get_orders_for_player(player):
    rows = execute_query(
        f"SELECT * FROM orders WHERE player = {placeholder()} ORDER BY id DESC",
        (player,),
        fetchall=True,
    )
    return [row_to_order(row) for row in rows]


def get_orders_for_booster(booster):
    rows = execute_query(
        f"SELECT * FROM orders WHERE booster = {placeholder()} ORDER BY id DESC",
        (booster,),
        fetchall=True,
    )
    return [row_to_order(row) for row in rows]


def get_store_boosters(store_id=None, owner_username=None):
    boosters = []
    for user in all_users():
        if user["role"] != "booster" or user.get("banned"):
            continue
        profile = user.get("profile", {})
        if store_id and str(profile.get("store_id", "")) != str(store_id):
            continue
        if owner_username and profile.get("managed_by") != owner_username:
            continue
        boosters.append(build_booster_card(user))
    boosters.sort(key=lambda item: (-item["stats"]["recommendation_score"], item["price_value"]))
    return boosters



def get_matching_legacy_order(order_like):
    params = (
        order_like.get("player", ""),
        order_like.get("booster", ""),
        order_like.get("game", ""),
        order_like.get("detail", ""),
        order_like.get("status", ""),
        str(order_like.get("price", "")),
    )
    row = execute_query(
        f"""
        SELECT * FROM orders
        WHERE player = {placeholder()}
          AND booster = {placeholder()}
          AND game = {placeholder()}
          AND detail = {placeholder()}
          AND status = {placeholder()}
          AND price = {placeholder()}
        ORDER BY id DESC
        """,
        params,
        fetchone=True,
    )
    return row_to_order(row)


def add_message(sender, receiver, message, msg_type="chat"):
    timestamp = china_now_text()
    execute_query(
        f"""
        INSERT INTO messages (sender, receiver, message, timestamp, type)
        VALUES ({placeholder()}, {placeholder()}, {placeholder()}, {placeholder()}, {placeholder()})
        """,
        (sender, receiver, message, timestamp, msg_type),
        commit=True,
    )
    return timestamp


def get_messages_between(user1, user2):
    rows = execute_query(
        f"""
        SELECT * FROM messages
        WHERE (sender = {placeholder()} AND receiver = {placeholder()})
           OR (sender = {placeholder()} AND receiver = {placeholder()})
        ORDER BY id ASC
        """,
        (user1, user2, user2, user1),
        fetchall=True,
    )
    return [row_to_message(row) for row in rows]


def get_notifications_for_user(username, limit=None):
    sql = f"""
        SELECT * FROM messages
        WHERE receiver = {placeholder()} AND type = {placeholder()}
        ORDER BY id DESC
    """
    rows = execute_query(sql, (username, "notification"), fetchall=True)
    notifications = [row_to_message(row) for row in rows]
    return notifications[:limit] if limit else notifications


def ensure_system_user():
    if get_user(SYSTEM_USERNAME):
        return
    add_user(SYSTEM_USERNAME, hash_password("disabled"), "admin", profile={"hidden": True})


def notify_user(receiver, message, sender=None):
    receiver_user = get_user(receiver)
    if not receiver_user or receiver == SYSTEM_USERNAME:
        return
    sender = sender or SYSTEM_USERNAME
    if not get_user(sender):
        sender = SYSTEM_USERNAME
    add_message(sender, receiver, message, "notification")


def notify_admins(message, sender=None):
    for admin in all_users():
        if admin["role"] == "admin":
            notify_user(admin["username"], message, sender=sender or SYSTEM_USERNAME)


def booster_order_stats(username):
    orders = get_orders_for_booster(username)
    completed_orders = [order for order in orders if order["status"] == "已完成"]
    active_orders = [order for order in orders if order["status"] in {"待接单", "已接单", "待确认完成"}]
    ratings = [parse_rating(order["rating"]) for order in completed_orders]
    ratings = [rating for rating in ratings if rating is not None]
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None
    total_income = round(sum(safe_float(order["price"]) for order in completed_orders), 2)
    completion_rate = round((len(completed_orders) / len(orders)) * 100, 1) if orders else 0
    recommendation_score = (avg_rating or 4.0) * 20 + len(completed_orders) * 2 - len(active_orders) * 3
    return {
        "total_orders": len(orders),
        "completed_orders": len(completed_orders),
        "active_orders": len(active_orders),
        "avg_rating": avg_rating,
        "total_income": total_income,
        "completion_rate": completion_rate,
        "recommendation_score": recommendation_score,
    }


def get_store_for_profile(profile):
    store = None
    store_id = str(profile.get("store_id", "")).strip()
    if store_id:
        store = get_store(store_id)
    if not store and profile.get("managed_by"):
        store = get_store_by_owner(profile.get("managed_by"))
    if not store and profile.get("store_name"):
        target_name = str(profile.get("store_name")).strip()
        for candidate in get_all_stores():
            if candidate["name"] == target_name:
                store = candidate
                break
    return store


def build_store_card(store):
    if not store:
        return None
    boosters = get_store_boosters(store_id=store["id"], owner_username=store["owner_username"])
    ratings = [booster["stats"]["avg_rating"] for booster in boosters if booster["stats"]["avg_rating"]]
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None
    completed_orders = sum(safe_int(booster["stats"]["completed_orders"], 0) for booster in boosters)
    active_orders = sum(safe_int(booster["stats"]["active_orders"], 0) for booster in boosters)
    min_prices = [safe_float(booster["profile"].get("price"), 0) for booster in boosters if safe_float(booster["profile"].get("price"), 0) > 0]
    base_min_price = safe_float(store.get("min_price"), 0)
    if base_min_price > 0:
        min_prices.append(base_min_price)
    min_price_value = min(min_prices) if min_prices else 0
    owner_user = get_user(store["owner_username"])
    owner_profile = owner_user.get("profile", {}) if owner_user else {}
    return {
        **store,
        "boosters": boosters,
        "booster_count": len(boosters),
        "avg_rating": avg_rating,
        "completed_orders": completed_orders,
        "active_orders": active_orders,
        "price_text": format_price_text(min_price_value or store.get("min_price")),
        "min_price_value": min_price_value,
        "hero_text": store.get("tagline") or store.get("description") or "多风格陪玩、排班派单、快速响应。",
        "logo_text": (store.get("name") or "店铺")[:2],
        "owner_display_name": owner_profile.get("display_name") or store["owner_username"],
    }


def build_booster_card(user):
    profile = user.get("profile", {})
    linked_store = get_store_for_profile(profile)
    stats = booster_order_stats(user["username"])
    seed_completed_orders = safe_int(profile.get("display_completed_orders"), 0)
    seed_total_orders = safe_int(profile.get("display_total_orders"), seed_completed_orders)
    seed_avg_rating = parse_rating(profile.get("display_avg_rating"))
    display_completed_orders = max(stats["completed_orders"], seed_completed_orders)
    display_total_orders = max(stats["total_orders"], seed_total_orders, display_completed_orders)
    display_avg_rating = stats["avg_rating"] or seed_avg_rating
    display_active_orders = max(stats["active_orders"], safe_int(profile.get("display_active_orders"), 0))
    display_completion_rate = round((display_completed_orders / display_total_orders) * 100, 1) if display_total_orders else 0
    recommendation_score = (display_avg_rating or 4.6) * 20 + display_completed_orders * 2 - display_active_orders * 2
    tags = split_tags(profile.get("persona_tags"))
    price_value = safe_float(profile.get("price"), default=999999)
    return {
        **user,
        "profile": {
            "games": profile.get("games", ""),
            "rank": profile.get("rank", ""),
            "price": profile.get("price", ""),
            "available_time": profile.get("available_time", ""),
            "play_style": profile.get("play_style", ""),
            "intro": profile.get("intro", ""),
            "store_id": profile.get("store_id", linked_store["id"] if linked_store else ""),
            "store_slug": profile.get("store_slug", linked_store["slug"] if linked_store else ""),
            "store_name": profile.get("store_name", linked_store["name"] if linked_store else ""),
            "managed_by": profile.get("managed_by", linked_store["owner_username"] if linked_store else ""),
            "badge": profile.get("badge", "店铺认证陪玩师" if linked_store else ""),
            "response_time": profile.get("response_time", ""),
            "status_text": profile.get("status_text", ""),
            "cover_theme": profile.get("cover_theme", linked_store["theme"] if linked_store else "graphite"),
            "persona_tags": tags,
            "avatar_path": profile.get("avatar_path", ""),
            "avatar_url": image_url(profile.get("avatar_path", "")),
            "cover_path": profile.get("cover_path", ""),
            "cover_url": image_url(profile.get("cover_path", "")),
        },
        "stats": {
            **stats,
            "completed_orders": display_completed_orders,
            "total_orders": display_total_orders,
            "avg_rating": display_avg_rating,
            "active_orders": display_active_orders,
            "completion_rate": display_completion_rate,
            "recommendation_score": recommendation_score,
        },
        "price_value": price_value,
        "avatar_text": user["username"][:1].upper(),
    }


def filter_and_rank_boosters(filters=None, limit=None):
    filters = filters or {}
    boosters = [
        build_booster_card(user)
        for user in all_users()
        if user["role"] == "booster" and not user.get("banned")
    ]

    game = (filters.get("game") or "").strip().lower()
    rank = (filters.get("rank") or "").strip().lower()
    availability = (filters.get("availability") or "").strip().lower()
    max_price = safe_float(filters.get("max_price"), default=0)
    sort_by = filters.get("sort") or "recommended"

    def matched(booster):
        profile = booster["profile"]
        if game and game not in profile.get("games", "").lower():
            return False
        if rank and rank not in profile.get("rank", "").lower():
            return False
        if availability and availability not in profile.get("available_time", "").lower():
            return False
        if max_price and safe_float(profile.get("price"), default=999999) > max_price:
            return False
        return True

    boosters = [booster for booster in boosters if matched(booster)]

    if sort_by == "price_asc":
        boosters.sort(key=lambda item: (item["price_value"], -item["stats"]["completed_orders"]))
    elif sort_by == "rating_desc":
        boosters.sort(key=lambda item: (-(item["stats"]["avg_rating"] or 0), item["price_value"]))
    else:
        boosters.sort(
            key=lambda item: (
                -item["stats"]["recommendation_score"],
                item["price_value"],
                -item["stats"]["completed_orders"],
            )
        )

    return boosters[:limit] if limit else boosters


def get_player_stats(username):
    orders = get_orders_for_player(username)
    completed_orders = [order for order in orders if order["status"] == "已完成"]
    complaint_orders = [order for order in orders if order["complaint_status"] in {"待处理", "处理中"}]
    pending_orders = [order for order in orders if order["status"] in {"待接单", "已接单", "待确认完成"}]
    total_spend = round(sum(safe_float(order["price"]) for order in completed_orders), 2)
    return {
        "total_orders": len(orders),
        "pending_orders": len(pending_orders),
        "completed_orders": len(completed_orders),
        "complaint_orders": len(complaint_orders),
        "total_spend": total_spend,
    }


def get_admin_stats():
    users = all_users()
    orders = get_all_orders()
    boosters = [user for user in users if user["role"] == "booster"]
    players = [user for user in users if user["role"] == "player"]
    merchants = [user for user in users if user["role"] == "merchant"]
    stores = get_all_stores()
    completed_orders = [order for order in orders if order["status"] == "已完成"]
    pending_complaints = [order for order in orders if order["complaint_status"] in {"待处理", "处理中"}]
    ratings = [parse_rating(order["rating"]) for order in completed_orders]
    ratings = [rating for rating in ratings if rating is not None]
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0
    return {
        "users_count": len(users),
        "players_count": len(players),
        "boosters_count": len(boosters),
        "merchants_count": len(merchants),
        "stores_count": len(stores),
        "orders_count": len(orders),
        "completed_orders_count": len(completed_orders),
        "pending_complaints_count": len(pending_complaints),
        "avg_rating": avg_rating,
        "conversion_rate": round((len(completed_orders) / len(orders)) * 100, 1) if orders else 0,
    }


def recent_complaints(limit=5):
    complaints = [order for order in get_all_orders() if order["complaint"]]
    complaints.sort(key=lambda item: item["id"], reverse=True)
    return complaints[:limit]


def get_top_boosters(limit=5):
    return filter_and_rank_boosters({"sort": "recommended"}, limit=limit)


def get_featured_stores(limit=None):
    stores = get_all_stores(featured_only=True)
    if not stores:
        stores = get_all_stores()
    stores = [build_store_card(store) for store in stores]
    return stores[:limit] if limit else stores


def profile_completion(profile):
    required_keys = ["games", "rank", "price", "available_time", "play_style", "intro"]
    completed = sum(1 for key in required_keys if str(profile.get(key, "")).strip())
    return round((completed / len(required_keys)) * 100)


def has_order_relationship(user_a, user_b):
    if not user_a or not user_b:
        return False
    role_a = user_a["role"]
    role_b = user_b["role"]
    if {role_a, role_b} != {"player", "booster"}:
        return False
    if role_a == "player":
        player_name, booster_name = user_a["username"], user_b["username"]
    else:
        player_name, booster_name = user_b["username"], user_a["username"]
    row = execute_query(
        f"""
        SELECT * FROM orders
        WHERE player = {placeholder()} AND booster = {placeholder()}
        ORDER BY id DESC
        """,
        (player_name, booster_name),
        fetchone=True,
    )
    return row is not None


def has_store_contact_relationship(user_a, user_b):
    if not user_a or not user_b:
        return False
    role_pair = {user_a["role"], user_b["role"]}
    if role_pair != {"player", "merchant"}:
        return False

    if user_a["role"] == "player":
        player_user, merchant_user = user_a, user_b
    else:
        player_user, merchant_user = user_b, user_a

    store = get_store_by_owner(merchant_user["username"])
    if not store:
        return False

    contacted_store_slugs = get_contacted_store_slugs(player_user.get("profile", {}))
    if store["slug"] in contacted_store_slugs:
        return True

    return bool(get_messages_between(player_user["username"], merchant_user["username"]))


def can_users_chat(user_a, user_b):
    return has_order_relationship(user_a, user_b) or has_store_contact_relationship(user_a, user_b)


def chat_partner_label(user):
    if not user:
        return ""
    if user["role"] == "merchant":
        store = get_store_by_owner(user["username"])
        if store:
            return store["name"]
    return user["username"]


def chat_partner_store_slug(user):
    if not user or user["role"] != "merchant":
        return ""
    store = get_store_by_owner(user["username"])
    return store["slug"] if store else ""


def build_order_payload(player_username, booster_username, booster_profile, source):
    quote = helpers_calculate_time_based_quote(
        source.get("start_time", "").strip(),
        source.get("end_time", "").strip(),
        booster_profile.get("price", ""),
        safe_float=safe_float,
        stringify_price=stringify_price,
    )
    service_type = source.get("service_type", "").strip()
    target_rank = source.get("target_rank", "").strip() if service_type == "技术上分" else ""
    return {
        "player": player_username,
        "booster": booster_username,
        "game": source.get("game", "").strip(),
        "detail": source.get("detail", "").strip(),
        "service_type": service_type,
        "target_rank": target_rank,
        "duration": quote.get("duration_text", ""),
        "preferred_time": quote.get("time_range_text", ""),
        "price": quote.get("price", ""),
        "hourly_rate": quote.get("hourly_rate", stringify_price(booster_profile.get("price", ""))),
        "start_time": source.get("start_time", "").strip(),
        "end_time": source.get("end_time", "").strip(),
        "pricing_valid": quote.get("valid", False),
        "pricing_error": quote.get("error", ""),
    }


def create_order_notifications(order, sender=None):
    notify_user(
        order["booster"],
        f"你收到来自 {order['player']} 的新订单，游戏：{order['game']}，请尽快处理。",
        sender=sender or order["player"],
    )
    notify_user(
        order["player"],
        f"订单 #{order['id']} 已创建，当前状态：{order['status']}，你可以在“我的订单”中查看进展。",
        sender=sender or SYSTEM_USERNAME,
    )
    notify_merchant_for_order(
        order,
        f"店铺收到新订单：#{order['id']}，玩家 {order['player']} 下单给 {order['booster']}。",
        sender=sender or order["player"],
    )


def migrate_json_to_db():
    if os.path.exists(USER_FILE):
        try:
            with open(USER_FILE, "r", encoding="utf-8") as file:
                users = json.load(file)
            for username, user in users.items():
                if username.lower() in RESERVED_USERNAMES:
                    continue
                if get_user(username) is None:
                    add_user(
                        username,
                        user.get("password", "123456"),
                        user.get("role", "player"),
                        user.get("banned", False),
                        user.get("profile", {}),
                    )
        except Exception as exc:
            print(f"[DEBUG] Failed to migrate users.json: {exc}", file=sys.stderr)

    if os.path.exists(ORDER_FILE):
        try:
            with open(ORDER_FILE, "r", encoding="utf-8") as file:
                orders = json.load(file)
            for order in orders:
                if get_matching_legacy_order(order):
                    continue
                add_order(
                    {
                        "player": order.get("player", ""),
                        "booster": order.get("booster", ""),
                        "game": order.get("game", ""),
                        "detail": order.get("detail", ""),
                        "status": order.get("status", "已完成"),
                        "price": order.get("price", ""),
                        "rating": order.get("rating", ""),
                        "comment": order.get("comment", ""),
                        "complaint": order.get("complaint", ""),
                        "complaint_status": "待处理" if order.get("complaint") else "无投诉",
                        "payment_status": "已支付",
                        "created_at": now_text(),
                    }
                )
        except Exception as exc:
            print(f"[DEBUG] Failed to migrate orders.json: {exc}", file=sys.stderr)


def seed_showcase_boosters():
    for booster in SEED_BOOSTERS:
        username = booster["username"]
        booster_password = (booster.get("password") or "").strip()
        existing_user = get_user(username)
        store = None
        managed_by = booster["profile"].get("managed_by")
        if managed_by:
            store = get_store_by_owner(managed_by)
        if existing_user is None:
            profile = dict(booster["profile"])
            if store:
                profile["store_id"] = store["id"]
                profile["store_name"] = store["name"]
                profile["managed_by"] = store["owner_username"]
                profile["cover_theme"] = profile.get("cover_theme") or store["theme"]
            add_user(username, booster["password"], booster["role"], profile=profile)
            continue
        if existing_user["role"] != "booster":
            continue
        if booster_password and SYNC_SEED_PASSWORDS_ON_BOOT and not password_matches(existing_user.get("password", ""), booster_password):
            update_user(username, {"password": booster_password})
        merged_profile = dict(existing_user.get("profile", {}))
        changed = False
        for key, value in booster["profile"].items():
            if not str(merged_profile.get(key, "")).strip():
                merged_profile[key] = value
                changed = True
        if store:
            for key, value in {
                "store_id": store["id"],
                "store_name": store["name"],
                "managed_by": store["owner_username"],
            }.items():
                if str(merged_profile.get(key, "")).strip() != str(value):
                    merged_profile[key] = value
                    changed = True
            if not str(merged_profile.get("cover_theme", "")).strip():
                merged_profile["cover_theme"] = store["theme"]
                changed = True
        if changed:
            update_user(username, {"profile": merged_profile})


def seed_merchants_and_stores():
    def is_placeholder_text(value):
        text = str(value or "").strip()
        if not text:
            return True
        filtered = []
        for ch in text:
            if ch.isspace() or ch in {"/", "\\", "|", "-", "—", "_", ",", "，", ".", "。", "·", "•"}:
                continue
            filtered.append(ch)
        return bool(filtered) and all(ch == "?" for ch in filtered)

    for merchant in SEED_MERCHANTS:
        existing_user = get_user(merchant["username"])
        merchant_password = (merchant.get("password") or "").strip()
        merchant_profile = {"display_name": merchant["display_name"]}
        if existing_user is None:
            add_user(merchant["username"], merchant["password"], "merchant", profile=merchant_profile)
            continue
        if existing_user["role"] != "merchant":
            continue
        if merchant_password and SYNC_SEED_PASSWORDS_ON_BOOT and not password_matches(existing_user.get("password", ""), merchant_password):
            update_user(merchant["username"], {"password": merchant_password})
        merged_profile = dict(existing_user.get("profile", {}))
        changed = False
        for key, value in merchant_profile.items():
            if not str(merged_profile.get(key, "")).strip():
                merged_profile[key] = value
                changed = True
        if changed:
            update_user(merchant["username"], {"profile": merged_profile})

    for store_seed in SHOWCASE_STORES:
        owner_username = store_seed["owner_username"]
        if not get_user(owner_username):
            continue
        payload = {
            "owner_username": owner_username,
            "name": store_seed["name"],
            "slug": unique_store_slug(store_seed.get("slug") or store_seed["name"]),
            "tagline": store_seed.get("headline", ""),
            "description": store_seed.get("description", ""),
            "games": ",".join(store_seed.get("games", [])),
            "city": store_seed.get("city", "线上接单"),
            "min_price": "".join(char for char in str(store_seed.get("price_text", "")) if char.isdigit() or char == "."),
            "logo_path": store_seed.get("logo_path", ""),
            "theme": store_seed.get("theme", "graphite"),
            "badge": store_seed.get("badge", "认证店铺"),
            "contact_note": store_seed.get("contact_note", "在线客服 / 快速派单"),
            "is_featured": True,
            "approval_status": "approved",
            "review_note": "系统预置示例店铺，默认已审核通过。",
            "reviewed_at": now_text(),
            "reviewed_by": SYSTEM_USERNAME,
            "updated_at": now_text(),
        }
        existing_store = get_store_by_owner(owner_username)
        if existing_store is None:
            payload["created_at"] = now_text()
            add_store(payload)
            continue
        fields = {
            "is_featured": True,
            "approval_status": "approved",
            "review_note": "系统预置示例店铺，默认已审核通过。",
            "reviewed_at": now_text(),
            "reviewed_by": SYSTEM_USERNAME,
            "updated_at": now_text(),
        }
        for key in [
            "name",
            "slug",
            "tagline",
            "description",
            "games",
            "city",
            "min_price",
            "logo_path",
            "theme",
            "badge",
            "contact_note",
        ]:
            if is_placeholder_text(existing_store.get(key, "")):
                fields[key] = payload[key]
        if len(fields) > 2:
            update_store(existing_store["id"], fields)


def sync_store_boosters(store):
    if not store:
        return
    for booster in get_store_boosters(owner_username=store["owner_username"]):
        user = get_user(booster["username"])
        if not user:
            continue
        profile = dict(user.get("profile", {}))
        changed = False
        sync_fields = {
            "store_id": store["id"],
            "store_name": store["name"],
            "managed_by": store["owner_username"],
        }
        for key, value in sync_fields.items():
            if str(profile.get(key, "")).strip() != str(value):
                profile[key] = value
                changed = True
        if not str(profile.get("cover_theme", "")).strip():
            profile["cover_theme"] = store["theme"]
            changed = True
        if changed:
            update_user(user["username"], {"profile": profile})


@app.route("/")
def home():
    return home_storefront()


@app.route("/register", methods=["GET", "POST"])
def register():
    return register_view()


@app.route("/login", methods=["GET", "POST"])
def login():
    return login_view()


@app.route("/social-login/<provider>")
def social_login(provider):
    return social_login_disabled(provider)


@app.route("/choose-role", methods=["GET", "POST"])
def choose_role():
    return choose_role_view()


@app.route("/logout")
def logout():
    return routes_logout_view(misc_route_deps())


@app.route("/merchant-application-status", methods=["GET", "POST"])
def merchant_application_status():
    return routes_merchant_application_status_view(misc_route_deps())


@app.route("/wallet", methods=["GET", "POST"])
@role_required("player", "booster", "merchant")
def wallet():
    username = session["username"]
    role = session["role"]
    user = get_user(username)
    if not user:
        flash("账号不存在，请重新登录。", "warning")
        return redirect(url_for("login"))

    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        amount = round_coin(request.form.get("amount", "0"))

        if action == "recharge":
            if role != "player":
                flash("只有玩家可进行充值。", "warning")
                return redirect(url_for("wallet"))
            ok, message, checkout_url = create_wallet_recharge_checkout_session(username, amount)
            if not ok:
                flash(message or "充值失败。", "warning")
                return redirect(url_for("wallet"))
            flash("正在跳转到 Stripe 充值页面。", "info")
            return redirect(checkout_url)

        if action == "withdraw":
            ok, payout_or_message = withdraw_buddy_coin_via_stripe(username, amount, note="用户提现", role_hint=role)
            if not ok:
                flash(payout_or_message or "提现失败。", "warning")
                return redirect(url_for("wallet"))
            flash(
                f"提现成功：{stringify_price(amount)} 巴迪币，平台通过 Stripe 已发起打款（Payout: {payout_or_message or 'N/A'}）。",
                "success",
            )
            return redirect(url_for("wallet"))

        flash("不支持的操作。", "warning")
        return redirect(url_for("wallet"))

    wallet_data = get_wallet_snapshot(user)
    transactions = get_wallet_transactions(username, limit=30)
    return render_template(
        "wallet.html",
        wallet=wallet_data,
        transactions=transactions,
        role=role,
        withdraw_rate=WITHDRAW_CASH_PER_COIN,
        coin_to_cash_rate=BUDDY_COIN_TO_CASH_RATE,
        share_rate=BOOSTER_REVENUE_SHARE,
    )


@app.route("/wallet/recharge/success")
@role_required("player")
def wallet_recharge_success():
    def _stripe_value(payload, key, default=None):
        if payload is None:
            return default
        if isinstance(payload, dict):
            return payload.get(key, default)
        try:
            return getattr(payload, key)
        except Exception:
            pass
        try:
            return payload[key]
        except Exception:
            return default

    session_id = (request.args.get("session_id") or "").strip()
    username = session.get("username", "").strip()
    if not session_id:
        flash("充值会话无效。", "warning")
        return redirect(url_for("wallet"))
    if not username:
        flash("请先登录后再查看充值结果。", "warning")
        return redirect(url_for("login"))

    if wallet_recharge_processed(username, session_id):
        flash("该充值已处理完成。", "info")
        return redirect(url_for("wallet"))

    try:
        if stripe is None:
            raise RuntimeError("Stripe SDK 未安装，请先安装并配置。")
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        payment_status = str(_stripe_value(checkout_session, "payment_status", "") or "").strip()
        if payment_status != "paid":
            flash("充值尚未完成。", "warning")
            return redirect(url_for("wallet"))

        metadata = _stripe_value(checkout_session, "metadata", {}) or {}
        target_user = str(_stripe_value(metadata, "username", "") or "").strip()
        coins = round_coin(_stripe_value(metadata, "coin_amount", "0"))
        if target_user != username:
            raise RuntimeError("充值用户与当前登录账号不一致。")
        if coins <= 0:
            raise RuntimeError("充值金额无效。")
        ok, message = recharge_buddy_coin(
            username,
            coins,
            note=f"Stripe充值 stripe_session:{session_id}",
        )
        if not ok:
            raise RuntimeError(message or "充值入账失败。")
        flash(f"充值成功，已增加 {stringify_price(coins)} 巴迪币。", "success")
    except Exception as exc:
        flash(f"充值验证失败：{exc}", "danger")

    return redirect(url_for("wallet"))


@app.route("/wallet/recharge/cancel")
@role_required("player")
def wallet_recharge_cancel():
    flash("充值已取消，你可以稍后重试。", "info")
    return redirect(url_for("wallet"))


@app.route("/player")
@role_required("player")
def player_home():
    return player_home_storefront()


@app.route("/boosters")
def boosters_list():
    return boosters_list_storefront()


@app.route("/order/<booster>", methods=["GET", "POST"])
@role_required("player")
def create_order(booster):
    return create_order_storefront(booster)


@app.route("/player/orders", methods=["GET", "POST"])
@role_required("player")
def player_orders():
    return player_orders_storefront()


@app.route("/booster")
@role_required("booster")
def booster_home():
    return booster_home_storefront()


@app.route("/booster/orders", methods=["GET", "POST"])
@role_required("booster")
def booster_orders():
    return booster_orders_storefront()


@app.route("/booster/apply-store", methods=["GET", "POST"])
@role_required("booster")
def booster_apply_store():
    username = session["username"]

    current_application = find_pending_booster_application_by_username(username)
    if not current_application:
        latest_application = find_latest_booster_application_by_username(username)
        if latest_application and latest_application.get("status") == "rejected":
            current_application = latest_application

    stores = get_all_stores()
    if request.method == "POST":
        store_id = request.form.get("store_id", "").strip()
        store = get_store(store_id)
        if not store:
            flash("请选择有效的店铺。", "warning")
            return redirect(url_for("booster_apply_store"))

        # 同一时间只允许 1 个待审核申请；若首次提交尚未选店，则允许补充店铺信息。
        pending_application = find_pending_booster_application_by_username(username)
        if pending_application:
            if pending_application.get("store_id"):
                flash("你有一个待审核的申请，请等待审核结果。", "warning")
                return redirect(url_for("booster_apply_store"))

            update_booster_application(
                pending_application["id"],
                {
                    "store_id": store["id"],
                    "store_owner_username": store["owner_username"],
                    "store_name": store["name"],
                },
            )
            flash("入驻申请已提交，等待店铺审核。", "success")
            return redirect(url_for("booster_apply_store"))

        latest_application = find_latest_booster_application_by_username(username)
        if latest_application and latest_application.get("status") == "rejected":
            add_booster_application(
                username=username,
                password=latest_application.get("password", ""),
                email=latest_application.get("email", ""),
                phone=latest_application.get("phone", ""),
                auth_provider=latest_application.get("auth_provider", "local"),
                social_id=latest_application.get("social_id", ""),
                game_account=latest_application.get("game_account", ""),
                proof_image_path=latest_application.get("proof_image_path", ""),
                store_id=store["id"],
                store_owner_username=store["owner_username"],
                store_name=store["name"],
                display_name=latest_application.get("display_name", username),
                profile=latest_application.get("profile", {}),
            )
            flash("入驻申请已提交，等待店铺审核。", "success")
            return redirect(url_for("booster_apply_store"))

        user = get_user(username)
        if not user:
            flash("未找到打手资料，请重新登录后再试。", "warning")
            return redirect(url_for("login"))

        profile = dict(user.get("profile") or {})
        add_booster_application(
            username=username,
            password=user.get("password", ""),
            email=user.get("email", ""),
            game_account=profile.get("game_account", ""),
            proof_image_path=profile.get("proof_image_path", ""),
            store_id=store["id"],
            store_owner_username=store["owner_username"],
            store_name=store["name"],
            display_name=profile.get("display_name", username),
            profile=profile,
        )
        flash("入驻申请已提交，等待店铺审核。", "success")
        return redirect(url_for("booster_apply_store"))

    return render_template(
        "booster_apply_store.html",
        stores=stores,
        current_application=current_application,
    )


@app.route("/booster/profile", methods=["GET", "POST"])
@role_required("booster")
def booster_profile():
    return booster_profile_storefront()


@app.route("/merchant")
@role_required("merchant")
def merchant_home():
    return merchant_home_storefront()


@app.route("/merchant/store", methods=["GET", "POST"])
@role_required("merchant")
def merchant_store():
    return merchant_store_storefront()


@app.route("/merchant/talents", methods=["GET", "POST"])
@role_required("merchant")
def merchant_talents():
    return merchant_talents_storefront()


@app.route("/store/<store_slug>")
def store_detail(store_slug):
    return store_detail_storefront(store_slug)


@app.route("/store/<store_slug>/contact")
@role_required("player")
def contact_store(store_slug):
    return contact_store_storefront(store_slug)


@app.route("/admin")
@role_required("admin")
def admin_home():
    return routes_admin_home_view(misc_route_deps())


@app.route("/admin/users", methods=["GET", "POST"])
@role_required("admin")
def admin_users():
    return admin_users_view()


@app.route("/admin/orders", methods=["GET", "POST"])
@role_required("admin")
def admin_orders():
    return routes_admin_orders_view(misc_route_deps())


@app.route("/admin/send_notification", methods=["GET", "POST"])
@role_required("admin")
def admin_send_notification():
    return routes_admin_send_notification_view(misc_route_deps())


@app.route("/player/chats")
@role_required("player")
def player_chats():
    return routes_player_chats_view(misc_route_deps())


@app.route("/booster/chats")
@role_required("booster")
def booster_chats():
    return routes_booster_chats_view(misc_route_deps())


@app.route("/chat/<partner>")
@role_required("player", "booster")
def chat(partner):
    return chat_view(partner)


@app.route("/send_message", methods=["POST"])
@role_required("player", "booster")
def send_message():
    return send_message_view()


def conversation_summaries(username, role):
    current_user = get_user(username)
    if not current_user:
        return []

    partner_names = []

    def add_partner(partner_name):
        if partner_name and partner_name not in partner_names:
            partner_names.append(partner_name)

    if role == "player":
        for order in get_orders_for_player(username):
            add_partner(order["booster"])
        for store_slug in get_contacted_store_slugs(current_user.get("profile", {})):
            store = get_store_by_slug(store_slug)
            if store:
                add_partner(store["owner_username"])
    elif role == "booster":
        for order in get_orders_for_booster(username):
            add_partner(order["player"])

    for partner_name in get_chat_partner_names(username):
        add_partner(partner_name)

    allowed_partner_roles = {
        "player": {"booster", "merchant"},
        "booster": {"player"},
        "merchant": {"player"},
        "admin": set(),
    }.get(role, set())

    summaries = []
    for partner_name in partner_names:
        partner_user = get_user(partner_name)
        if not partner_user or partner_user["role"] not in allowed_partner_roles:
            continue
        if not can_users_chat(current_user, partner_user):
            continue

        messages = get_messages_between(username, partner_name)
        last_message = messages[-1] if messages else None
        summaries.append(
            {
                "partner": partner_name,
                "partner_label": chat_partner_label(partner_user),
                "partner_store_slug": chat_partner_store_slug(partner_user),
                "last_message": last_message["message"] if last_message else "还没有聊天记录，发一条消息开始吧。",
                "timestamp": last_message["timestamp"] if last_message else "刚刚建立会话",
            }
        )

    summaries.sort(key=lambda item: item["timestamp"], reverse=True)
    return summaries


@app.route("/merchant/chats")
@role_required("merchant")
def merchant_chats():
    return routes_merchant_chats_view(misc_route_deps())


@role_required("player", "booster", "merchant")
def chat_view(partner):
    return routes_chat_view(misc_route_deps(), partner)


@role_required("player", "booster", "merchant")
def send_message_view():
    return routes_send_message_view(misc_route_deps())

# 旧版 auth/admin 参考实现已移除（此前为大段注释代码，不参与运行）。


def register_view():
    return auth_register_view(
        redirect_to_dashboard=redirect_to_dashboard,
        normalize_email=normalize_email,
        normalize_phone=normalize_phone,
        looks_like_email=looks_like_email,
        validate_password_policy=validate_password_policy,
        get_user_by_email=get_user_by_email,
        looks_like_phone=looks_like_phone,
        get_user_by_phone=get_user_by_phone,
        reserved_usernames=RESERVED_USERNAMES,
        get_user=get_user,
        start_auth_onboarding=start_auth_onboarding,
        hash_password=hash_password,
        render_auth_gateway=render_auth_gateway,
    )


def login_view():
    return auth_login_view(
        redirect_to_dashboard=redirect_to_dashboard,
        resolve_user_for_login=resolve_user_for_login,
        find_application_for_status_lookup=find_application_for_status_lookup,
        admin_password_matches=admin_password_matches,
        password_is_hashed=password_is_hashed,
        update_user=update_user,
        get_user=get_user,
        record_failed_login_attempt=record_failed_login_attempt,
        max_login_attempts=MAX_LOGIN_ATTEMPTS,
        clear_failed_login_attempts=clear_failed_login_attempts,
        clear_auth_onboarding=clear_auth_onboarding,
        log_user_in=log_user_in,
        render_auth_gateway=render_auth_gateway,
    )


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    return auth_forgot_password(
        normalize_email=normalize_email,
        validate_email_address=validate_email_address,
        get_user=get_user,
        mail_is_configured=mail_is_configured,
        send_password_reset_email=send_password_reset_email,
        validate_password_policy=validate_password_policy,
        verify_password_reset_code=verify_password_reset_code,
        clear_password_reset_state=clear_password_reset_state,
        update_user=update_user,
    )


def choose_role_view():
    return auth_choose_role_view(
        redirect_to_dashboard=redirect_to_dashboard,
        get_auth_onboarding=get_auth_onboarding,
        normalize_email=normalize_email,
        normalize_phone=normalize_phone,
        reserved_usernames=RESERVED_USERNAMES,
        get_user=get_user,
        find_pending_booster_application_by_username=find_pending_booster_application_by_username,
        looks_like_email=looks_like_email,
        looks_like_phone=looks_like_phone,
        get_user_by_email=get_user_by_email,
        get_user_by_phone=get_user_by_phone,
        find_pending_booster_application_by_email=find_pending_booster_application_by_email,
        save_uploaded_image=save_uploaded_image,
        add_booster_application=add_booster_application,
        clear_auth_onboarding=clear_auth_onboarding,
        add_user=add_user,
        log_user_in=log_user_in,
        unique_username_from_seed=unique_username_from_seed,
        social_provider_labels=SOCIAL_PROVIDER_LABELS,
    )


@role_required("admin")
def admin_users_view():
    return admin_users_handler(
        safe_int=safe_int,
        get_booster_application=get_booster_application,
        get_user=get_user,
        find_user_by_email=find_user_by_email,
        get_user_by_phone=get_user_by_phone,
        add_user=add_user,
        update_booster_application=update_booster_application,
        now_text=now_text,
        notify_user=notify_user,
        send_booster_application_review_email=send_booster_application_review_email,
        clear_failed_login_attempts=clear_failed_login_attempts,
        update_user=update_user,
        validate_password_policy=validate_password_policy,
        delete_user=delete_user,
        all_users=all_users,
        get_booster_applications=get_booster_applications,
        system_username=SYSTEM_USERNAME,
    )


def social_login_disabled(provider):
    return social_login_disabled_handler(provider)


app.view_functions["chat"] = chat_view
app.view_functions["send_message"] = send_message_view
app.view_functions["register"] = register_view
app.view_functions["login"] = login_view
app.view_functions["social_login"] = social_login_disabled


@app.route("/create-checkout-session", methods=["POST"])
@role_required("player")
def create_checkout_session():
    return payments_create_checkout_session(
        stripe_is_configured=stripe_is_configured,
        stripe_obj=stripe,
        resolve_store_for_order_target=resolve_store_for_order_target,
        build_store_card=build_store_card,
        build_store_order_payload=build_store_order_payload,
        build_order_payload=build_order_payload,
        get_user=get_user,
    )


@app.route("/payment-success")
@role_required("player")
def payment_success():
    return payments_payment_success(
        stripe_obj=stripe,
        get_order_by_payment_session_id=get_order_by_payment_session_id,
        add_order=add_order,
        now_text=now_text,
        create_order_notifications=create_order_notifications,
    )


@app.route("/payment-cancel")
@role_required("player")
def payment_cancel():
    return payments_payment_cancel()


def bootstrap_application_data():
    with app.app_context():
        init_db()
        ensure_upload_dirs()
        ensure_system_user()
        migrate_json_to_db()
        seed_merchants_and_stores()
        seed_showcase_boosters()
        for seeded_store in get_all_stores():
            sync_store_boosters(seeded_store)


if (os.environ.get("APP_BOOTSTRAP_ON_IMPORT") or "").strip().lower() in {"1", "true", "yes", "on"}:
    bootstrap_application_data()


def get_order_store(order):
    return helpers_get_order_store(
        order,
        get_store=get_store,
        get_store_by_owner=get_store_by_owner,
        get_all_stores=get_all_stores,
    )


def build_booster_card(user):
    return market_build_booster_card(user, market_deps())


def get_store_boosters(store_id=None, owner_username=None):
    return market_get_store_boosters(store_id, owner_username, market_deps())


def build_store_card(store):
    return market_build_store_card(store, market_deps())


def get_merchant_orders(owner_username):
    return market_get_merchant_orders(owner_username, market_deps())


def get_merchant_stats(owner_username):
    return market_get_merchant_stats(owner_username, market_deps())


def filter_and_rank_boosters(filters=None, limit=None):
    return market_filter_and_rank_boosters(filters, limit, market_deps())


def get_top_boosters(limit=5):
    return market_get_top_boosters(limit, market_deps())


def filter_and_rank_stores(filters=None, limit=None, include_pending=False, owner_username=None):
    return market_filter_and_rank_stores(filters, limit, include_pending, owner_username, market_deps())


def get_featured_stores(limit=None):
    return market_get_featured_stores(limit, market_deps())


def get_player_stats(username):
    return market_get_player_stats(username, market_deps())


def notify_merchant_for_booster(booster_username, message, sender=None):
    booster = get_user((booster_username or "").strip())
    if not booster or booster.get("role") != "booster":
        return
    owner_username = (booster.get("profile") or {}).get("managed_by", "").strip()
    if owner_username:
        notify_user(owner_username, message, sender=sender or SYSTEM_USERNAME)


def notify_merchant_for_order(order, message, sender=None):
    return market_notify_merchant_for_order(order, message, sender, market_deps())


def create_order_notifications(order, sender=None):
    return market_create_order_notifications(order, sender, market_deps())


def decorate_order_for_view(order):
    return helpers_decorate_order_for_view(
        order,
        get_order_store=get_order_store,
        build_store_card=build_store_card,
        get_user=get_user,
        build_booster_card=build_booster_card,
    )


def build_store_order_payload(player_username, store, source):
    return helpers_build_store_order_payload(
        player_username,
        store,
        source,
        safe_float=safe_float,
        stringify_price=stringify_price,
        get_booster_orders=get_orders_for_booster,
    )


def calculate_time_based_quote(start_time, end_time, hourly_rate):
    return helpers_calculate_time_based_quote(
        start_time,
        end_time,
        hourly_rate,
        safe_float=safe_float,
        stringify_price=stringify_price,
    )


def resolve_store_for_order_target(target):
    return helpers_resolve_store_for_order_target(
        target,
        get_store_by_slug=get_store_by_slug,
        get_user=get_user,
        get_store_for_profile=get_store_for_profile,
    )


def get_store_applications_for_owner(owner_username, status=None):
    return helpers_get_store_applications_for_owner(
        owner_username,
        status=status,
        get_booster_applications=get_booster_applications,
    )


def public_store_access_allowed(store):
    return helpers_public_store_access_allowed(
        store,
        store_is_approved=store_is_approved,
    )


def api_route_deps():
    return select_dependencies(globals(), API_ROUTE_DEP_KEYS)


def market_deps():
    return select_dependencies(globals(), MARKET_DEP_KEYS)


def misc_route_deps():
    return select_dependencies(globals(), MISC_ROUTE_DEP_KEYS)


def storefront_deps():
    return select_dependencies(globals(), STOREFRONT_DEP_KEYS)


def redirect_non_player_away_from_discovery():
    if session.get("role") in {"booster", "merchant", "admin"}:
        return redirect_to_dashboard()
    return None


def home_storefront():
    role_redirect = redirect_non_player_away_from_discovery()
    if role_redirect is not None:
        return role_redirect
    return sf_home_storefront(storefront_deps())


@role_required("player")
def player_home_storefront():
    return redirect(url_for("home"))


def boosters_list_storefront():
    role_redirect = redirect_non_player_away_from_discovery()
    if role_redirect is not None:
        return role_redirect
    return sf_boosters_list_storefront(storefront_deps())


def store_detail_storefront(store_slug):
    return sf_store_detail_storefront(store_slug, storefront_deps())


@role_required("player")
def contact_store_storefront(store_slug):
    return sf_contact_store_storefront(store_slug, storefront_deps())


@role_required("player")
def create_order_storefront(booster):
    return sf_create_order_storefront(booster, storefront_deps())


@role_required("player")
def player_orders_storefront():
    return sf_player_orders_storefront(storefront_deps())


@role_required("booster")
def booster_home_storefront():
    return sf_booster_home_storefront(storefront_deps())


@role_required("booster")
def booster_orders_storefront():
    return sf_booster_orders_storefront(storefront_deps())


@role_required("booster")
def booster_profile_storefront():
    return sf_booster_profile_storefront(storefront_deps())


@role_required("merchant")
def merchant_home_storefront():
    return sf_merchant_home_storefront(storefront_deps())


@role_required("merchant")
def merchant_store_storefront():
    return sf_merchant_store_storefront(storefront_deps())


@role_required("merchant")
def merchant_talents_storefront():
    return sf_merchant_talents_storefront(storefront_deps())


@role_required("admin")
def admin_users_storefront():
    return sf_admin_users_storefront(storefront_deps())


def payment_success_storefront():
    return payments_payment_success_storefront(
        stripe_obj=stripe,
        get_order_by_payment_session_id=get_order_by_payment_session_id,
        add_order=add_order,
        now_text=now_text,
        create_order_notifications=create_order_notifications,
    )


def payment_cancel_storefront():
    return payments_payment_cancel_storefront()


def create_checkout_redirect_url(*, product_name, amount, metadata, cancel_params=None):
    return payments_create_checkout_redirect_url(
        stripe_is_configured=stripe_is_configured,
        stripe_obj=stripe,
        product_name=product_name,
        amount=amount,
        metadata=metadata,
        success_url=url_for("payment_success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=url_for("payment_cancel", _external=True, **(cancel_params or {})),
    )


def choose_role_storefront():
    return sf_choose_role_storefront(storefront_deps())


app.register_blueprint(create_service_system_blueprint(api_route_deps))
app.view_functions["home"] = home_storefront
app.view_functions["player_home"] = player_home_storefront
app.view_functions["boosters_list"] = boosters_list_storefront
app.view_functions["store_detail"] = store_detail_storefront
app.view_functions["contact_store"] = contact_store_storefront
app.view_functions["create_order"] = create_order_storefront
app.view_functions["player_orders"] = player_orders_storefront
app.view_functions["booster_home"] = booster_home_storefront
app.view_functions["booster_orders"] = booster_orders_storefront
app.view_functions["booster_profile"] = booster_profile_storefront
app.view_functions["merchant_home"] = merchant_home_storefront
app.view_functions["merchant_store"] = merchant_store_storefront
app.view_functions["merchant_talents"] = merchant_talents_storefront
app.view_functions["admin_users"] = admin_users_storefront
app.view_functions["payment_success"] = payment_success_storefront
app.view_functions["payment_cancel"] = payment_cancel_storefront
app.view_functions["choose_role"] = choose_role_storefront
app.add_url_rule("/merchant", endpoint="merchant_home_post", view_func=merchant_home_storefront, methods=["POST"])
if __name__ == "__main__":
    print("[DEBUG] 进入主入口 if __name__ == '__main__'")
    print(f"[DEBUG] 当前数据库目标: {'PostgreSQL' if DATABASE_URL else DATABASE}")
    debug_mode = (os.environ.get("FLASK_DEBUG") or "1").strip().lower() in {"1", "true", "yes", "on"}
    debugger_attached = (sys.gettrace() is not None) or ("debugpy" in sys.modules)
    is_reloader_child = (os.environ.get("WERKZEUG_RUN_MAIN") or "").strip().lower() == "true"
    should_bootstrap = (not debug_mode) or is_reloader_child
    if should_bootstrap:
        bootstrap_application_data()
        print("[DEBUG] bootstrap_application_data() 执行完毕")
    else:
        print("[DEBUG] 跳过一次 bootstrap（Werkzeug reloader 父进程）。")
    port = int(os.environ.get("PORT", 5000))
    print(f"[DEBUG] 即将启动 Flask，监听端口: {port}")
    # Windows + VS Code debugpy 下，reloader/threaded 组合可能触发 WinError 10038。
    # 调试会话中关闭 reloader 和 threaded，避免套接字关闭阶段的异常。
    use_reloader = debug_mode and not debugger_attached
    use_threaded = not debugger_attached
    if socketio is not None:
        socketio.run(app, host="0.0.0.0", port=port, debug=debug_mode, use_reloader=use_reloader)
    else:
        app.run(host="0.0.0.0", port=port, debug=debug_mode, use_reloader=use_reloader, threaded=use_threaded)
