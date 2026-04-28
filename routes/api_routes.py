from __future__ import annotations

from flask import jsonify

from service_system.database import (
    build_admin_orders_snapshot,
    build_admin_users_snapshot,
    build_chat_list_snapshot,
    build_chat_thread_snapshot,
    build_dashboard_snapshot,
    build_discovery_snapshot,
    build_orders_snapshot,
    build_wallet_snapshot,
    get_public_store_snapshot,
)
from service_system.actions import (
    ServiceActionError,
    apply_admin_user_action,
    review_booster_application,
    review_merchant_application,
    review_store_application,
    update_admin_order,
)
from service_system.serializers import (
    serialize_admin_orders,
    serialize_admin_users,
    serialize_chat_message,
    serialize_chat_thread,
    serialize_chats,
    serialize_dashboard,
    serialize_discovery,
    serialize_order,
    serialize_orders,
    serialize_store_detail,
    serialize_user,
    serialize_wallet,
)


def _ok(payload=None, status=200):
    body = {"ok": True}
    if payload:
        body.update(payload)
    return jsonify(body), status


def _error(message, status=400, code="bad_request", **extra):
    body = {
        "ok": False,
        "error": {
            "message": message,
            "code": code,
        },
    }
    if extra:
        body.update(extra)
    return jsonify(body), status


def _action_error(exc):
    return _error(exc.message, status=exc.status, code=exc.code)


def _require_user(deps, roles=None):
    user = deps["current_user"]()
    if not user:
        return None, _error("请先登录后再继续。", status=401, code="unauthenticated")
    if roles and user.get("role") not in roles:
        return None, _error("你没有权限执行此操作。", status=403, code="forbidden")
    return user, None


def api_bootstrap(deps):
    user = deps["current_user"]()
    return _ok(
        {
            "csrfToken": deps["get_csrf_token"](),
            "systemTime": deps["now_text"](),
            "session": serialize_user(user, deps),
            "serviceRoutes": {
                "home": "/service",
                "login": "/service/login",
                "dashboard": "/service/dashboard",
                "orders": "/service/orders",
                "wallet": "/service/wallet",
                "chats": "/service/chats",
                "adminUsers": "/service/admin/users",
                "adminOrders": "/service/admin/orders",
            },
            "constants": {
                "discoveryGames": list(deps["DISCOVERY_GAMES"]),
                "discoveryTags": list(deps["DISCOVERY_FILTER_TAGS"]),
                "serviceTypeOptions": list(deps["SERVICE_TYPE_OPTIONS"]),
            },
        }
    )


def api_login(deps):
    payload = deps["request"].get_json(silent=True) or {}
    identifier = (payload.get("identifier") or payload.get("username") or "").strip()
    password = (payload.get("password") or payload.get("pwd") or "").strip()
    if not identifier or not password:
        return _error("请输入账号和密码。", status=400, code="missing_credentials")

    user = deps["resolve_user_for_login"](identifier)
    if not user:
        pending = deps["find_application_for_status_lookup"](identifier, password)
        if pending:
            application = pending.get("application") or {}
            return _error(
                "该账号当前仍在审核流程中。",
                status=409,
                code="application_pending",
                pendingApplication={
                    "role": pending.get("role", ""),
                    "applicationId": application.get("id"),
                    "status": application.get("status", ""),
                    "reviewNote": application.get("review_note", ""),
                },
            )
        return _error("账号或密码错误。", status=401, code="invalid_credentials")

    if user.get("banned"):
        if user.get("lock_reason") == "too_many_failed_password_attempts":
            return _error("账号因多次输错密码被锁定，请先重置密码。", status=423, code="account_locked")
        return _error("账号已被封禁。", status=403, code="account_banned")

    stored_password = user.get("password", "")
    if user.get("role") == "admin":
        password_ok = deps["admin_password_matches"](password)
    else:
        password_ok = deps["password_matches"](stored_password, password)
    if not password_ok:
        attempts, locked = deps["record_failed_login_attempt"](user["username"])
        if locked:
            return _error("密码连续错误次数过多，账号已被锁定。", status=423, code="account_locked")
        remaining = max(deps["MAX_LOGIN_ATTEMPTS"] - attempts, 0)
        return _error(
            f"密码错误，再输错 {remaining} 次将锁定账号。",
            status=401,
            code="invalid_credentials",
            remainingAttempts=remaining,
        )

    if user.get("role") != "admin" and not deps["password_is_hashed"](stored_password):
        deps["update_user"](user["username"], {"password": password})
        user = deps["get_user"](user["username"])

    deps["clear_failed_login_attempts"](user["username"])
    deps["clear_auth_onboarding"]()
    deps["log_user_in"](user)
    user = deps["get_user"](user["username"])

    return _ok(
        {
            "csrfToken": deps["get_csrf_token"](),
            "session": serialize_user(user, deps),
            "pendingApproval": bool(user.get("role") == "merchant" and (user.get("profile") or {}).get("status") == "pending"),
        }
    )


def api_logout(deps):
    deps["session"].clear()
    return _ok({"csrfToken": deps["get_csrf_token"]()})


def api_discovery(deps):
    filters = {
        "q": deps["request"].args.get("q", ""),
        "game": deps["request"].args.get("game", ""),
        "max_price": deps["request"].args.get("max_price", ""),
        "sort": deps["request"].args.get("sort", "recommended"),
    }
    snapshot = build_discovery_snapshot(filters, deps)
    return _ok(serialize_discovery(snapshot))


def api_store_detail(store_slug, deps):
    store = get_public_store_snapshot(store_slug, deps)
    if not store:
        return _error("店铺不存在，或当前不可访问。", status=404, code="store_not_found")
    return _ok(serialize_store_detail(store, deps))


def api_dashboard(deps):
    user, error = _require_user(deps)
    if error:
        return error
    snapshot = build_dashboard_snapshot(user, deps)
    return _ok(serialize_dashboard(snapshot, deps))


def api_orders(deps):
    user, error = _require_user(deps)
    if error:
        return error
    snapshot = build_orders_snapshot(user, deps)
    return _ok(serialize_orders(snapshot))


def api_wallet(deps):
    user, error = _require_user(deps, roles={"player", "booster", "merchant"})
    if error:
        return error
    snapshot = build_wallet_snapshot(user, deps)
    return _ok(serialize_wallet(snapshot))


def api_wallet_recharge(deps):
    user, error = _require_user(deps, roles={"player"})
    if error:
        return error
    payload = deps["request"].get_json(silent=True) or {}
    amount = deps["round_coin"](deps["safe_float"](payload.get("amount"), 0.0))
    if amount <= 0:
        return _error("Recharge amount must be greater than 0.", status=400, code="invalid_amount")
    ok, message, checkout_url = deps["create_wallet_recharge_checkout_session"](user["username"], amount)
    if not ok:
        return _error(message or "Failed to create recharge checkout session.", status=400, code="recharge_failed")
    return _ok({"checkoutUrl": checkout_url, "message": "Redirecting to Stripe recharge checkout."})


def api_wallet_withdraw(deps):
    user, error = _require_user(deps, roles={"booster", "merchant"})
    if error:
        return error
    payload = deps["request"].get_json(silent=True) or {}
    amount = deps["round_coin"](deps["safe_float"](payload.get("amount"), 0.0))
    if amount <= 0:
        return _error("Withdrawal amount must be greater than 0.", status=400, code="invalid_amount")
    ok, payout_or_message = deps["withdraw_buddy_coin_via_stripe"](user["username"], amount, note="用户提现", role_hint=user["role"])
    if not ok:
        return _error(payout_or_message or "Withdrawal failed.", status=400, code="withdraw_failed")
    refreshed_user = deps["get_user"](user["username"])
    snapshot = build_wallet_snapshot(refreshed_user, deps)
    return _ok(
        {
            "message": f"Withdrawal submitted successfully. Stripe payout: {payout_or_message or 'N/A'}",
            "payoutId": payout_or_message or "",
            "walletSnapshot": serialize_wallet(snapshot),
        }
    )


def api_chats(deps):
    user, error = _require_user(deps, roles={"player", "booster", "merchant"})
    if error:
        return error
    snapshot = build_chat_list_snapshot(user, deps)
    return _ok(serialize_chats(snapshot, deps))


def api_chat_thread(partner, deps):
    user, error = _require_user(deps, roles={"player", "booster", "merchant"})
    if error:
        return error
    partner_user = deps["get_user"]((partner or "").strip())
    if not partner_user:
        return _error("Chat partner does not exist.", status=404, code="partner_not_found")
    if not deps["can_users_chat"](user, partner_user):
        return _error("You are not allowed to chat with this user yet.", status=403, code="chat_not_allowed")
    snapshot = build_chat_thread_snapshot(user, partner_user, deps)
    return _ok(serialize_chat_thread(snapshot, deps))


def api_chat_send(partner, deps):
    user, error = _require_user(deps, roles={"player", "booster", "merchant"})
    if error:
        return error
    partner_user = deps["get_user"]((partner or "").strip())
    if not partner_user:
        return _error("Chat partner does not exist.", status=404, code="partner_not_found")
    if not deps["can_users_chat"](user, partner_user):
        return _error("You are not allowed to chat with this user yet.", status=403, code="chat_not_allowed")
    payload = deps["request"].get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    if not message:
        return _error("Message cannot be empty.", status=400, code="missing_message")
    deps["add_message"](user["username"], partner_user["username"], message, "chat")
    created_message = deps["get_messages_between"](user["username"], partner_user["username"])[-1]
    return _ok(
        {
            "message": "Message sent.",
            "chatMessage": serialize_chat_message(created_message),
        },
        status=201,
    )


def api_admin_users(deps):
    user, error = _require_user(deps, roles={"admin"})
    if error:
        return error
    snapshot = build_admin_users_snapshot(deps)
    return _ok(serialize_admin_users(snapshot, deps))


def api_admin_store_review(store_id, deps):
    user, error = _require_user(deps, roles={"admin"})
    if error:
        return error
    payload = deps["request"].get_json(silent=True) or {}
    action = (payload.get("action") or "").strip()
    if action not in {"approve_store", "reject_store"}:
        return _error("Unsupported store review action.", status=400, code="unsupported_action")
    try:
        result = review_store_application(store_id, action, (payload.get("reviewNote") or "").strip(), user["username"], deps)
    except ServiceActionError as exc:
        return _action_error(exc)
    return _ok(result)


def api_admin_booster_review(application_id, deps):
    user, error = _require_user(deps, roles={"admin"})
    if error:
        return error
    payload = deps["request"].get_json(silent=True) or {}
    action = (payload.get("action") or "").strip()
    if action not in {"approve_booster_application", "reject_booster_application"}:
        return _error("Unsupported booster review action.", status=400, code="unsupported_action")
    try:
        result = review_booster_application(
            application_id,
            action,
            (payload.get("reviewNote") or "").strip(),
            user["username"],
            deps,
        )
    except ServiceActionError as exc:
        return _action_error(exc)
    return _ok(result)


def api_admin_merchant_review(application_id, deps):
    user, error = _require_user(deps, roles={"admin"})
    if error:
        return error
    payload = deps["request"].get_json(silent=True) or {}
    action = (payload.get("action") or "").strip()
    if action not in {"approve_merchant_application", "reject_merchant_application"}:
        return _error("Unsupported merchant review action.", status=400, code="unsupported_action")
    try:
        result = review_merchant_application(
            application_id,
            action,
            (payload.get("reviewNote") or "").strip(),
            user["username"],
            deps,
        )
    except ServiceActionError as exc:
        return _action_error(exc)
    return _ok(result)


def api_admin_user_action(deps):
    user, error = _require_user(deps, roles={"admin"})
    if error:
        return error
    payload = deps["request"].get_json(silent=True) or {}
    try:
        result = apply_admin_user_action(
            (payload.get("username") or "").strip(),
            (payload.get("action") or "").strip(),
            user["username"],
            deps,
            new_password=(payload.get("newPassword") or "").strip(),
        )
    except ServiceActionError as exc:
        return _action_error(exc)
    return _ok(result)


def api_admin_orders(deps):
    user, error = _require_user(deps, roles={"admin"})
    if error:
        return error
    snapshot = build_admin_orders_snapshot(
        {
            "keyword": deps["request"].args.get("keyword", ""),
            "status": deps["request"].args.get("status", ""),
            "complaint": deps["request"].args.get("complaint", ""),
        },
        deps,
    )
    return _ok(serialize_admin_orders(snapshot))


def api_admin_order_action(order_id, deps):
    user, error = _require_user(deps, roles={"admin"})
    if error:
        return error
    payload = deps["request"].get_json(silent=True) or {}
    try:
        result = update_admin_order(
            order_id,
            (payload.get("action") or "").strip(),
            (payload.get("complaintStatus") or "").strip(),
            (payload.get("complaintReply") or "").strip(),
            (payload.get("adminNote") or "").strip(),
            user["username"],
            deps,
        )
    except ServiceActionError as exc:
        return _action_error(exc)
    if result.get("order"):
        result["order"] = serialize_order(deps["decorate_order_for_view"](result["order"]))
    return _ok(result)


def api_create_store_order(store_slug, deps):
    user, error = _require_user(deps, roles={"player"})
    if error:
        return error

    store = deps["get_store_by_slug"](store_slug)
    if not store or not deps["store_is_approved"](store):
        return _error("该店铺当前不可下单。", status=404, code="store_not_available")

    payload = deps["request"].get_json(silent=True) or {}
    store_card = deps["build_store_card"](store)
    order_payload = deps["build_store_order_payload"](
        user["username"],
        store_card,
        {
            "selected_booster": payload.get("selected_booster", ""),
            "service_type": payload.get("service_type", ""),
            "game": payload.get("game", ""),
            "target_rank": payload.get("target_rank", ""),
            "detail": payload.get("detail", ""),
            "start_time": payload.get("start_time", ""),
            "end_time": payload.get("end_time", ""),
            "start_time_mode": payload.get("start_time_mode", ""),
            "order_hours": payload.get("order_hours", ""),
        },
    )

    if not order_payload["game"] or not order_payload["detail"] or not order_payload["service_type"]:
        return _error("请补全游戏、服务类型和需求描述。", status=400, code="missing_order_fields")
    if order_payload["service_type"] == "技术上分" and not order_payload["target_rank"]:
        return _error("选择技术上分时，请填写目标段位。", status=400, code="missing_target_rank")
    if not order_payload.get("pricing_valid"):
        return _error(order_payload.get("pricing_error") or "无法根据时间生成有效报价。", status=400, code="invalid_quote")
    if not order_payload["price"]:
        return _error("该店铺尚未配置有效的每小时单价。", status=400, code="missing_price")

    order_amount = deps["round_coin"](deps["safe_float"](order_payload["price"], 0.0))
    if order_amount <= 0:
        return _error("订单金额无效。", status=400, code="invalid_price")

    payment_method = (payload.get("payment_method") or "stripe").strip().lower()
    if payment_method == "buddy_coin":
        charge_ok, charge_message = deps["collect_order_payment_in_buddy_coin"](
            user["username"],
            store["owner_username"],
            order_amount,
        )
        if not charge_ok:
            return _error(charge_message or "巴迪币扣款失败。", status=400, code="wallet_charge_failed")

        order_payload.update(
            {
                "status": "待接待",
                "payment_status": "巴迪币已支付",
                "coin_amount": deps["stringify_price"](order_amount),
                "booster_coin_share": deps["stringify_price"](
                    deps["round_coin"](order_amount * deps["BOOSTER_REVENUE_SHARE"])
                ),
                "booster_coin_settled": 0,
                "created_at": deps["now_text"](),
            }
        )
        deps["add_order"](order_payload)
        created_order = deps["decorate_order_for_view"](deps["get_orders_for_player"](user["username"])[0])
        deps["create_order_notifications"](created_order, sender=user["username"])
        return _ok(
            {
                "paymentMode": "buddy_coin",
                "message": "已使用巴迪币完成支付，订单已进入店铺接待大厅。",
                "order": serialize_order(created_order),
            },
            status=201,
        )

    try:
        stripe_metadata = {
            key: str(value)
            for key, value in order_payload.items()
            if key not in {"pricing_valid", "pricing_error"}
        }
        stripe_metadata.update(
            {
                "coin_amount": deps["stringify_price"](order_amount),
                "booster_coin_share": deps["stringify_price"](
                    deps["round_coin"](order_amount * deps["BOOSTER_REVENUE_SHARE"])
                ),
            }
        )
        checkout_url = deps["create_checkout_redirect_url"](
            product_name=f"GameBuddy - {store_card['name']} 接待大厅",
            amount=order_payload["price"],
            metadata=stripe_metadata,
            cancel_params={"store_slug": store["slug"]},
        )
    except Exception as exc:
        return _error(f"创建支付会话失败：{exc}", status=400, code="checkout_failed")

    return _ok(
        {
            "paymentMode": "stripe",
            "checkoutUrl": checkout_url,
            "orderPreview": {
                "price": order_payload["price"],
                "duration": order_payload.get("duration", ""),
                "preferredTime": order_payload.get("preferred_time", ""),
                "selectedBooster": order_payload.get("selected_booster_name") or order_payload.get("booster", ""),
            },
        }
    )
