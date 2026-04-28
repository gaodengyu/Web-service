from flask import flash, redirect, request, session, url_for


def _read_value(payload, key, default=None):
    if payload is None:
        return default
    if isinstance(payload, dict):
        return payload.get(key, default)
    try:
        return getattr(payload, key)
    except AttributeError:
        pass
    try:
        return payload[key]
    except Exception:
        return default


def _to_coin_amount(raw_value):
    try:
        value = round(float(raw_value), 2)
    except (TypeError, ValueError):
        value = 0.0
    return max(value, 0.0)


def _resolve_coin_fields(metadata):
    order_amount = _to_coin_amount(_read_value(metadata, "coin_amount", ""))
    if order_amount <= 0:
        order_amount = _to_coin_amount(_read_value(metadata, "price", ""))

    booster_coin_share = _to_coin_amount(_read_value(metadata, "booster_coin_share", ""))
    if booster_coin_share <= 0 and order_amount > 0:
        booster_coin_share = round(order_amount * 0.8, 2)

    return order_amount, booster_coin_share


def create_checkout_redirect_url(
    *,
    stripe_is_configured,
    stripe_obj,
    product_name,
    amount,
    metadata,
    success_url,
    cancel_url,
):
    if stripe_obj is None:
        raise RuntimeError("Stripe SDK 未安装，请先安装并配置。")
    if not stripe_is_configured():
        raise RuntimeError("Stripe 未配置：请设置有效的 STRIPE_SECRET_KEY。")

    unit_amount = int(float(amount) * 100)
    if unit_amount <= 0:
        raise RuntimeError("订单金额无效。")

    checkout_session = stripe_obj.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": product_name},
                    "unit_amount": unit_amount,
                },
                "quantity": 1,
            }
        ],
        mode="payment",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={key: str(value) for key, value in (metadata or {}).items()},
    )

    checkout_url = (_read_value(checkout_session, "url", "") or "").strip()
    if not checkout_url:
        raise RuntimeError("Stripe 返回的支付会话缺少跳转地址。")
    return checkout_url


def create_checkout_session(
    *,
    stripe_is_configured,
    stripe_obj,
    resolve_store_for_order_target,
    build_store_card,
    build_store_order_payload,
    build_order_payload,
    get_user,
):
    try:
        if stripe_obj is None:
            raise RuntimeError("Stripe SDK 未安装，请先安装并配置。")
        if not stripe_is_configured():
            raise RuntimeError("Stripe 未配置：请设置有效的 STRIPE_SECRET_KEY。")
        data = request.get_json(force=True)

        metadata = data.get("metadata") or {}
        store_slug = (data.get("store_slug") or metadata.get("store_slug") or "").strip()
        booster_username = (data.get("booster") or metadata.get("booster") or "").strip()
        product_name = "GameBuddy 订单"
        order_payload = None

        if store_slug:
            store = resolve_store_for_order_target(store_slug)
            if not store:
                raise RuntimeError("下单目标店铺不存在。")
            store_card = build_store_card(store)
            order_payload = build_store_order_payload(
                session.get("username", ""),
                store_card,
                {
                    "service_type": data.get("service_type") or metadata.get("service_type", ""),
                    "game": data.get("game") or metadata.get("game", ""),
                    "target_rank": data.get("target_rank") or metadata.get("target_rank", ""),
                    "detail": data.get("detail") or metadata.get("detail", ""),
                    "start_time": data.get("start_time") or metadata.get("start_time", ""),
                    "end_time": data.get("end_time") or metadata.get("end_time", ""),
                },
            )
            product_name = f"GameBuddy - {store_card['name']} 接待大厅"
        elif booster_username:
            booster_user = get_user(booster_username)
            if not booster_user or booster_user.get("role") != "booster":
                raise RuntimeError("下单目标陪玩师不存在。")
            order_payload = build_order_payload(session.get("username", ""), booster_username, booster_user.get("profile", {}), data)
            product_name = f"GameBuddy - {booster_username} 服务订单"
        else:
            raise RuntimeError("缺少可计价的下单目标。")

        if not order_payload.get("pricing_valid"):
            raise RuntimeError(order_payload.get("pricing_error") or "无法根据预约时间计算订单金额。")

        checkout_url = create_checkout_redirect_url(
            stripe_is_configured=stripe_is_configured,
            stripe_obj=stripe_obj,
            product_name=product_name,
            amount=order_payload["price"],
            metadata={
                **{key: str(value) for key, value in metadata.items()},
                **{key: str(value) for key, value in order_payload.items() if key not in {"pricing_valid", "pricing_error"}},
            },
            success_url=url_for("payment_success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=url_for("payment_cancel", _external=True),
        )
        return {"checkout_url": checkout_url}, 200
    except Exception as exc:
        return {"error": str(exc)}, 400


def payment_success(
    *,
    stripe_obj,
    get_order_by_payment_session_id,
    add_order,
    now_text,
    create_order_notifications,
):
    session_id = request.args.get("session_id", "").strip()
    if not session_id:
        flash("支付会话无效。", "warning")
        return redirect(url_for("player_orders"))

    if get_order_by_payment_session_id(session_id):
        flash("该支付已处理完成。", "info")
        return redirect(url_for("player_orders"))

    try:
        if stripe_obj is None:
            raise RuntimeError("Stripe SDK 未安装，请先安装并配置。")
        checkout_session = stripe_obj.checkout.Session.retrieve(session_id)
        if _read_value(checkout_session, "payment_status") != "paid":
            flash("支付尚未完成。", "warning")
            return redirect(url_for("player_orders"))
        metadata = _read_value(checkout_session, "metadata") or {}
        player_username = (_read_value(metadata, "player", "") or session.get("username") or "").strip()
        if not player_username:
            raise RuntimeError("支付元数据缺少玩家信息（player）。")
        order_amount, booster_coin_share = _resolve_coin_fields(metadata)
        order_payload = {
            "player": player_username,
            "booster": _read_value(metadata, "booster", ""),
            "game": _read_value(metadata, "game", ""),
            "detail": _read_value(metadata, "detail", ""),
            "service_type": _read_value(metadata, "service_type", ""),
            "target_rank": _read_value(metadata, "target_rank", ""),
            "duration": _read_value(metadata, "duration", ""),
            "preferred_time": _read_value(metadata, "preferred_time", ""),
            "price": _read_value(metadata, "price", ""),
            "status": "待接单",
            "payment_status": "已支付",
            "payment_session_id": session_id,
            "coin_amount": str(order_amount),
            "booster_coin_share": str(booster_coin_share),
            "booster_coin_settled": 0,
            "created_at": now_text(),
        }
        add_order(order_payload)
        created_order = get_order_by_payment_session_id(session_id)
        if created_order:
            create_order_notifications(created_order, sender=created_order["player"])
        flash("支付成功，订单已创建。", "success")
    except Exception as exc:
        flash(f"支付验证失败：{exc}", "danger")

    return redirect(url_for("player_orders"))


def payment_cancel():
    booster = request.args.get("booster", "").strip()
    flash("支付已取消，你可以继续修改需求后重新下单。", "info")
    if booster:
        return redirect(url_for("create_order", booster=booster))
    return redirect(url_for("boosters_list"))


def payment_success_storefront(
    *,
    stripe_obj,
    get_order_by_payment_session_id,
    add_order,
    now_text,
    create_order_notifications,
):
    session_id = request.args.get("session_id", "").strip()
    if not session_id:
        flash("支付会话无效。", "warning")
        return redirect(url_for("player_orders"))

    if get_order_by_payment_session_id(session_id):
        flash("该支付已处理完成。", "info")
        return redirect(url_for("player_orders"))

    try:
        if stripe_obj is None:
            raise RuntimeError("Stripe SDK 未安装，请先安装并配置。")
        checkout_session = stripe_obj.checkout.Session.retrieve(session_id)
        if _read_value(checkout_session, "payment_status") != "paid":
            flash("支付尚未完成。", "warning")
            return redirect(url_for("player_orders"))
        metadata = _read_value(checkout_session, "metadata") or {}
        player_username = (_read_value(metadata, "player", "") or session.get("username") or "").strip()
        if not player_username:
            raise RuntimeError("支付元数据缺少玩家信息（player）。")
        order_amount, booster_coin_share = _resolve_coin_fields(metadata)
        order_payload = {
            "player": player_username,
            "booster": _read_value(metadata, "booster", ""),
            "store_id": _read_value(metadata, "store_id", ""),
            "store_owner": _read_value(metadata, "store_owner", ""),
            "store_name": _read_value(metadata, "store_name", ""),
            "assigned_booster": _read_value(metadata, "assigned_booster", ""),
            "assigned_booster_name": _read_value(metadata, "assigned_booster_name", ""),
            "game": _read_value(metadata, "game", ""),
            "detail": _read_value(metadata, "detail", ""),
            "service_type": _read_value(metadata, "service_type", ""),
            "target_rank": _read_value(metadata, "target_rank", ""),
            "duration": _read_value(metadata, "duration", ""),
            "preferred_time": _read_value(metadata, "preferred_time", ""),
            "price": _read_value(metadata, "price", ""),
            "status": "待接待" if _read_value(metadata, "store_id", "") or _read_value(metadata, "store_owner", "") else "待接单",
            "payment_status": "已支付",
            "payment_session_id": session_id,
            "coin_amount": str(order_amount),
            "booster_coin_share": str(booster_coin_share),
            "booster_coin_settled": 0,
            "created_at": now_text(),
        }
        add_order(order_payload)
        created_order = get_order_by_payment_session_id(session_id)
        if created_order:
            create_order_notifications(created_order, sender=created_order["player"])
        flash("支付成功，订单已创建。", "success")
    except Exception as exc:
        flash(f"支付验证失败：{exc}", "danger")

    return redirect(url_for("player_orders"))


def payment_cancel_storefront():
    store_slug = request.args.get("store_slug", "").strip()
    booster = request.args.get("booster", "").strip()
    flash("支付已取消，你可以继续调整需求后重新下单。", "info")
    if store_slug:
        return redirect(url_for("create_order", booster=store_slug))
    if booster:
        return redirect(url_for("create_order", booster=booster))
    return redirect(url_for("boosters_list"))
