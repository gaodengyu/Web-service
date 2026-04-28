import sys

def home_storefront(deps):
    if not deps["session"].get("username"):
        return deps["render_auth_gateway"](active_panel="login")
    filters = {
        "q": deps["request"].args.get("q", ""),
        "game": deps["request"].args.get("game", ""),
        "min_price": deps["request"].args.get("min_price", ""),
        "max_price": deps["request"].args.get("max_price", ""),
        "price_bucket": deps["request"].args.get("price_bucket", ""),
        "sort": deps["request"].args.get("sort", "recommended"),
    }

    all_public_stores = deps["filter_and_rank_stores"](
        filters={"sort": "price_asc"},
        limit=None,
    )
    prices = [
        deps["safe_float"](store.get("min_price_value"), 0)
        for store in all_public_stores
        if deps["safe_float"](store.get("min_price_value"), 0) > 0
    ]
    max_prices = [
        deps["safe_float"](store.get("max_price_value"), 0)
        for store in all_public_stores
        if deps["safe_float"](store.get("max_price_value"), 0) > 0
    ]
    price_min = int(min(prices)) if prices else 30
    price_max = int(max(max_prices)) if max_prices else 200

    showcase_stores = deps["filter_and_rank_stores"](filters=filters, limit=6)
    stats = deps["get_admin_stats"]()
    return deps["render_template"](
        "home.html",
        showcase_stores=showcase_stores,
        discovery_games=deps["DISCOVERY_GAMES"],
        discovery_tags=deps["DISCOVERY_FILTER_TAGS"],
        stats=stats,
        filters=filters,
        price_min=price_min,
        price_max=price_max,
    )


def player_home_storefront(deps):
    username = deps["session"]["username"]
    orders = [deps["decorate_order_for_view"](order) for order in deps["get_orders_for_player"](username)[:4]]
    stats = deps["get_player_stats"](username)
    recommended_stores = deps["get_featured_stores"](limit=3)
    notifications = deps["get_notifications_for_user"](username, limit=4)
    return deps["render_template"](
        "player_dashboard.html",
        stats=stats,
        orders=orders,
        recommended_stores=recommended_stores,
        notifications=notifications,
    )


def boosters_list_storefront(deps):
    filters = {
        "q": deps["request"].args.get("q", ""),
        "game": deps["request"].args.get("game", ""),
        "min_price": deps["request"].args.get("min_price", ""),
        "max_price": deps["request"].args.get("max_price", ""),
        "price_bucket": deps["request"].args.get("price_bucket", ""),
        "sort": deps["request"].args.get("sort", "recommended"),
    }

    all_public_stores = deps["filter_and_rank_stores"](
        filters={"sort": "price_asc"},
        limit=None,
    )
    prices = [
        deps["safe_float"](store.get("min_price_value"), 0)
        for store in all_public_stores
        if deps["safe_float"](store.get("min_price_value"), 0) > 0
    ]
    max_prices = [
        deps["safe_float"](store.get("max_price_value"), 0)
        for store in all_public_stores
        if deps["safe_float"](store.get("max_price_value"), 0) > 0
    ]
    price_min = int(min(prices)) if prices else 30
    price_max = int(max(max_prices)) if max_prices else 200

    stores = deps["filter_and_rank_stores"](filters=filters)
    return deps["render_template"](
        "boosters_list.html",
        stores=stores,
        filters=filters,
        discovery_games=deps["DISCOVERY_GAMES"],
        discovery_tags=deps["DISCOVERY_FILTER_TAGS"],
        price_min=price_min,
        price_max=price_max,
    )


def store_detail_storefront(store_slug, deps):
    store = deps["get_store_by_slug"](store_slug)
    if not store or not deps["public_store_access_allowed"](store):
        deps["flash"]("店铺不存在，或暂未通过平台审核。", "warning")
        return deps["redirect"](deps["url_for"]("home"))
    store_card = deps["build_store_card"](store)
    recommended_stores = [item for item in deps["get_featured_stores"](limit=6) if item["slug"] != store_card["slug"]][:3]
    return deps["render_template"]("store_detail.html", store=store_card, boosters=store_card["boosters"], recommended_stores=recommended_stores)


def contact_store_storefront(store_slug, deps):
    store = deps["get_store_by_slug"](store_slug)
    if not store or not deps["store_is_approved"](store):
        deps["flash"]("店铺不存在，或暂未通过平台审核。", "warning")
        return deps["redirect"](deps["url_for"]("home"))

    username = deps["session"]["username"]
    user = deps["get_user"](username)
    owner_username = store["owner_username"]
    owner_user = deps["get_user"](owner_username)
    if not user or not owner_user:
        deps["flash"]("暂时无法建立联系，请稍后重试。", "warning")
        return deps["redirect"](deps["url_for"]("store_detail", store_slug=store_slug))

    deps["update_user"](username, {"profile": deps["remember_contacted_store"](user.get("profile", {}), store["slug"])})

    if not deps["get_messages_between"](username, owner_username):
        deps["add_message"](username, owner_username, f"你好，我想进入 {store['name']} 的接待大厅咨询陪玩安排。", "chat")

    deps["flash"](f"已进入 {store['name']} 接待大厅。", "success")
    return deps["redirect"](deps["url_for"]("chat", partner=owner_username))


def create_order_storefront(booster, deps):
    store = deps["resolve_store_for_order_target"](booster)
    if not store or not deps["store_is_approved"](store):
        deps["flash"]("该店铺当前不可下单。", "warning")
        return deps["redirect"](deps["url_for"]("boosters_list"))

    store_card = deps["build_store_card"](store)
    player_username = deps["session"]["username"]

    def resolve_wallet_available():
        player_user = deps["get_user"](player_username)
        profile = dict((player_user or {}).get("profile") or {})
        balance = max(deps["round_coin"](deps["safe_float"](profile.get("buddy_coin_balance", 0.0), 0.0)), 0.0)
        locked = max(deps["round_coin"](deps["safe_float"](profile.get("buddy_coin_locked", 0.0), 0.0)), 0.0)
        locked = min(locked, balance)
        return max(deps["round_coin"](balance - locked), 0.0)

    if deps["request"].method == "POST":
        order_payload = deps["build_store_order_payload"](player_username, store_card, deps["request"].form)
        if not order_payload["game"] or not order_payload["detail"] or not order_payload["service_type"]:
            deps["flash"]("请补全游戏、服务类型和需求描述。", "warning")
            return deps["redirect"](deps["url_for"]("create_order", booster=store["slug"]))
        if order_payload["service_type"] == "技术上分" and not order_payload["target_rank"]:
            deps["flash"]("选择技术上分时，请填写目标段位。", "warning")
            return deps["redirect"](deps["url_for"]("create_order", booster=store["slug"]))
        if not order_payload.get("pricing_valid"):
            deps["flash"](order_payload.get("pricing_error") or "请选择陪玩师并填写有效的开始和结束时间。", "warning")
            return deps["redirect"](deps["url_for"]("create_order", booster=store["slug"]))
        if not order_payload["price"]:
            deps["flash"]("该店铺尚未配置有效的每小时单价，暂时无法下单。", "warning")
            return deps["redirect"](deps["url_for"]("create_order", booster=store["slug"]))
        payment_method = (deps["request"].form.get("payment_method") or "").strip().lower()
        if payment_method not in {"buddy_coin", "stripe"}:
            payment_method = ""
        order_amount = deps["round_coin"](deps["safe_float"](order_payload["price"], 0.0))
        if order_amount <= 0:
            deps["flash"]("订单金额无效，无法发起支付。", "warning")
            return deps["redirect"](deps["url_for"]("create_order", booster=store["slug"]))

        if not payment_method:
            payment_method = "buddy_coin" if resolve_wallet_available() >= order_amount else "stripe"

        if payment_method == "buddy_coin":
            charge_ok, charge_message = deps["collect_order_payment_in_buddy_coin"](
                player_username,
                store["owner_username"],
                order_amount,
            )
            if not charge_ok:
                deps["flash"](charge_message or "巴迪币扣款失败。", "warning")
                return deps["redirect"](deps["url_for"]("create_order", booster=store["slug"]))

            order_payload.update(
                {
                    "status": "待接待",
                    "payment_status": "巴迪币已支付",
                    "coin_amount": deps["stringify_price"](order_amount),
                    "booster_coin_share": deps["stringify_price"](deps["round_coin"](order_amount * deps["BOOSTER_REVENUE_SHARE"])),
                    "booster_coin_settled": 0,
                    "created_at": deps["now_text"](),
                }
            )
            deps["add_order"](order_payload)
            created_order = deps["get_orders_for_player"](player_username)[0]
            deps["create_order_notifications"](created_order, sender=player_username)
            deps["flash"](f"已扣除 {deps['stringify_price'](order_amount)} 巴迪币，订单已进入店铺接待大厅。", "success")
            return deps["redirect"](deps["url_for"]("player_orders"))

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
            deps["flash"](f"创建支付会话失败：{exc}", "warning")
            return deps["redirect"](deps["url_for"]("create_order", booster=store["slug"]))

        return deps["redirect"](checkout_url)

    wallet_available = resolve_wallet_available()
    return deps["render_template"](
        "create_order.html",
        store=store_card,
        service_type_options=deps["SERVICE_TYPE_OPTIONS"],
        wallet_available=wallet_available,
        wallet_available_text=deps["stringify_price"](wallet_available),
    )


def player_orders_storefront(deps):
    username = deps["session"]["username"]
    if deps["request"].method == "POST":
        order_id = deps["safe_int"](deps["request"].form.get("order_id"), default=-1)
        action = deps["request"].form.get("action", "").strip()
        order = deps["get_order"](order_id)
        if not order or order["player"] != username:
            deps["flash"]("订单不存在或无权操作。", "warning")
            return deps["redirect"](deps["url_for"]("player_orders"))

        if action == "confirm_complete":
            if order["status"] != "待确认完成":
                deps["flash"]("当前订单还不能确认完成。", "warning")
            else:
                assigned_booster = order.get("assigned_booster") or order.get("booster")
                payment_status = (order.get("payment_status") or "").strip()
                requires_revenue_settlement = payment_status in {"巴迪币已支付", "已支付"}
                if assigned_booster and requires_revenue_settlement:
                    settled_ok, settled_message = deps["settle_order_booster_share"](
                        order,
                        assigned_booster,
                        reviewer_username=username,
                    )
                    if not settled_ok:
                        deps["flash"](settled_message or "订单分账失败，请稍后再试。", "warning")
                        return deps["redirect"](deps["url_for"]("player_orders"))
                deps["update_order"](order_id, {"status": "已完成"})
                if assigned_booster:
                    deps["notify_user"](assigned_booster, f"订单 #{order_id} 已由玩家确认完成。", sender=username)
                deps["notify_merchant_for_order"](order, f"订单 #{order_id} 已由玩家确认完成。", sender=username)
                deps["flash"]("订单已确认完成。", "success")

        elif action == "rate":
            rating = deps["request"].form.get("rating", "").strip()
            comment = deps["request"].form.get("comment", "").strip()
            if order["status"] != "已完成":
                deps["flash"]("只有已完成订单才能评价。", "warning")
            elif order.get("rating"):
                deps["flash"]("该订单已经评价过了。", "warning")
            elif rating not in {"1", "2", "3", "4", "5"}:
                deps["flash"]("请选择 1-5 星评分。", "warning")
            else:
                deps["update_order"](order_id, {"rating": rating, "comment": comment})
                assigned_booster = order.get("assigned_booster") or order.get("booster")
                if assigned_booster:
                    deps["notify_user"](assigned_booster, f"订单 #{order_id} 收到新的 {rating} 星评价。", sender=username)
                deps["notify_merchant_for_order"](order, f"店内订单 #{order_id} 收到新的 {rating} 星评价。", sender=username)
                deps["flash"]("评价提交成功。", "success")

        elif action == "complain":
            complaint = deps["request"].form.get("complaint", "").strip()
            if not complaint:
                deps["flash"]("投诉内容不能为空。", "warning")
            elif order.get("complaint"):
                deps["flash"]("该订单已经提交过投诉。", "warning")
            else:
                deps["update_order"](order_id, {"complaint": complaint, "complaint_status": "待处理"})
                assigned_booster = order.get("assigned_booster") or order.get("booster")
                if assigned_booster:
                    deps["notify_user"](assigned_booster, f"订单 #{order_id} 收到玩家投诉，请留意处理结果。", sender=username)
                deps["notify_merchant_for_order"](order, f"店内订单 #{order_id} 收到投诉，请尽快介入处理。", sender=username)
                deps["notify_admins"](
                    f"新的投诉待处理：订单 #{order_id}，玩家 {order['player']}，店铺 {order.get('store_name') or '未命名店铺'}。",
                    sender=username,
                )
                deps["flash"]("投诉已提交，管理员会尽快处理。", "success")

        elif action == "cancel":
            if order["status"] != "待接待":
                deps["flash"]("只有待接待订单才能取消。", "warning")
            else:
                refund_ok, refund_message = deps["refund_order_buddy_coin"](
                    order,
                    reason="玩家主动取消订单",
                    operator_username=username,
                )
                if not refund_ok:
                    deps["flash"](refund_message or "退款失败，请联系平台处理。", "warning")
                    return deps["redirect"](deps["url_for"]("player_orders"))
                deps["update_order"](order_id, {"status": "已取消", "payment_status": "巴迪币已退款"})
                deps["notify_merchant_for_order"](order, f"订单 #{order_id} 已被玩家取消。", sender=username)
                deps["flash"]("订单已取消。", "success")

        return deps["redirect"](deps["url_for"]("player_orders"))

    orders = [deps["decorate_order_for_view"](order) for order in deps["get_orders_for_player"](username)]
    return deps["render_template"]("player_orders.html", orders=orders)


def booster_home_storefront(deps):
    username = deps["session"]["username"]
    user = deps["get_user"](username)
    store = deps["build_store_card"](deps["get_store_for_profile"](user.get("profile", {}))) if user else None
    orders = [deps["decorate_order_for_view"](order) for order in deps["get_orders_for_booster"](username)[:4]]
    stats = deps["booster_order_stats"](username)
    notifications = deps["get_notifications_for_user"](username, limit=4)
    return deps["render_template"](
        "booster_dashboard.html",
        profile=user.get("profile", {}) if user else {},
        store=store,
        stats=stats,
        orders=orders,
        completion=deps["profile_completion"](user.get("profile", {}) if user else {}),
        notifications=notifications,
    )


def booster_orders_storefront(deps):
    username = deps["session"]["username"]
    if deps["request"].method == "POST":
        order_id = deps["safe_int"](deps["request"].form.get("order_id"), default=-1)
        action = deps["request"].form.get("action", "").strip()
        order = deps["get_order"](order_id)
        assigned_booster = (order or {}).get("assigned_booster") or (order or {}).get("booster")
        if not order or assigned_booster != username:
            deps["flash"]("订单不存在或无权操作。", "warning")
            return deps["redirect"](deps["url_for"]("booster_orders"))

        if action == "reject":
            if order["status"] != "已接单":
                deps["flash"]("当前订单还不能退回接待大厅。", "warning")
            else:
                deps["update_order"](order_id, {"booster": "", "assigned_booster": "", "assigned_booster_name": "", "status": "待接待"})
                deps["notify_user"](order["player"], f"订单 #{order_id} 已回到店铺接待大厅，店铺会重新为你安排陪玩师。", sender=username)
                deps["notify_merchant_for_order"](order, f"订单 #{order_id} 已被陪玩师退回接待大厅，请重新安排。", sender=username)
                deps["flash"]("订单已退回店铺接待大厅。", "success")
        elif action == "finish":
            if order["status"] != "已接单":
                deps["flash"]("当前订单还不能标记完成。", "warning")
            else:
                deps["update_order"](order_id, {"status": "待确认完成"})
                deps["notify_user"](order["player"], f"订单 #{order_id} 已完成服务，请确认并评价。", sender=username)
                deps["notify_merchant_for_order"](order, f"店内订单 #{order_id} 已完成服务，等待玩家确认。", sender=username)
                deps["flash"]("已标记为待确认完成。", "success")

        return deps["redirect"](deps["url_for"]("booster_orders"))

    orders = [deps["decorate_order_for_view"](order) for order in deps["get_orders_for_booster"](username)]
    return deps["render_template"]("booster_orders.html", orders=orders)


def booster_profile_storefront(deps):
    deps["flash"]("陪玩资料由所属店铺统一维护，如需修改请联系店长。", "info")
    return deps["redirect"](deps["url_for"]("booster_home"))


def merchant_home_storefront(deps):
    username = deps["session"]["username"]
    store = deps["get_store_by_owner"](username)
    if deps["request"].method == "POST":
        if not store:
            deps["flash"]("请先完善店铺资料。", "warning")
            return deps["redirect"](deps["url_for"]("merchant_store"))

        action = deps["request"].form.get("action", "").strip()
        order_id = deps["safe_int"](deps["request"].form.get("order_id"), default=-1)
        order = deps["get_order"](order_id)
        if not order or str(order.get("store_owner") or "") != username:
            deps["flash"]("订单不存在，或不属于当前店铺。", "warning")
            return deps["redirect"](deps["url_for"]("merchant_home"))

        if action == "assign_booster":
            booster_username = deps["request"].form.get("booster_username", "").strip()
            booster_user = deps["get_user"](booster_username)
            booster_profile = booster_user.get("profile", {}) if booster_user else {}
            if not booster_user or booster_user["role"] != "booster" or booster_profile.get("managed_by") != username:
                deps["flash"]("请选择当前店铺下已通过审核的陪玩师。", "warning")
                return deps["redirect"](deps["url_for"]("merchant_home"))
            if (booster_profile.get("approval_status") or "approved") != "approved":
                deps["flash"]("该陪玩师尚未通过平台审核。", "warning")
                return deps["redirect"](deps["url_for"]("merchant_home"))
            booster_card = deps["build_booster_card"](booster_user)
            deps["update_order"](
                order_id,
                {
                    "booster": booster_username,
                    "assigned_booster": booster_username,
                    "assigned_booster_name": booster_card["display_name"],
                    "status": "已接单",
                },
            )
            deps["notify_user"](order["player"], f"{store['name']} 已为你的订单安排 {booster_card['display_name']} 开始服务。", sender=username)
            deps["notify_user"](booster_username, f"你被 {store['name']} 分配到订单 #{order_id}，请尽快开单。", sender=username)
            deps["flash"]("订单已分配给陪玩师。", "success")

        return deps["redirect"](deps["url_for"]("merchant_home"))

    stats = deps["get_merchant_stats"](username)
    store_card = deps["build_store_card"](stats["store"]) if stats["store"] else None
    boosters = deps["get_store_boosters"](owner_username=username)
    orders = [deps["decorate_order_for_view"](order) for order in deps["get_merchant_orders"](username)[:8]]
    notifications = deps["get_notifications_for_user"](username, limit=6)
    pending_applications = deps["get_store_applications_for_owner"](username, status="pending")
    return deps["render_template"](
        "merchant_dashboard.html",
        stats=stats,
        store=store_card,
        boosters=boosters[:6],
        orders=orders,
        notifications=notifications,
        pending_applications=pending_applications,
    )


def merchant_store_storefront(deps):
    username = deps["session"]["username"]
    store = deps["get_store_by_owner"](username)
    if deps["request"].method == "POST":
        name = deps["request"].form.get("name", "").strip()
        action = deps["request"].form.get("action", "save").strip() or "save"
        if not name:
            deps["flash"]("店铺名称不能为空。", "warning")
            return deps["redirect"](deps["url_for"]("merchant_store"))

        try:
            fields = {
                "name": name,
                "slug": deps["unique_store_slug"](deps["request"].form.get("slug", "").strip() or name, exclude_store_id=store["id"] if store else None),
                "tagline": deps["request"].form.get("tagline", "").strip(),
                "description": deps["request"].form.get("description", "").strip(),
                "games": deps["request"].form.get("games", "").strip(),
                "city": deps["request"].form.get("city", "").strip(),
                "min_price": deps["request"].form.get("min_price", "").strip(),
                "theme": deps["request"].form.get("theme", "graphite").strip() or "graphite",
                "badge": deps["request"].form.get("badge", "").strip() or "认证店铺",
                "contact_note": deps["request"].form.get("contact_note", "").strip() or "接待大厅在线 / 统一派单",
                "updated_at": deps["now_text"](),
            }
            logo = deps["request"].files.get("logo")
            cover = deps["request"].files.get("cover")
            if logo and logo.filename:
                fields["logo_path"] = deps["save_uploaded_image"](logo, "uploads", "stores", "logo", prefix=f"store_logo_{username}")
            if cover and cover.filename:
                fields["cover_path"] = deps["save_uploaded_image"](cover, "uploads", "stores", "cover", prefix=f"store_cover_{username}")
        except ValueError as exc:
            deps["flash"](str(exc), "warning")
            return deps["redirect"](deps["url_for"]("merchant_store"))

        if store is None:
            deps["add_store"]({"owner_username": username, "created_at": deps["now_text"](), "is_featured": False, "approval_status": "pending", **fields})
            store = deps["get_store_by_owner"](username)
            deps["flash"]("店铺资料已创建。", "success")
        else:
            deps["update_store"](store["id"], fields)
            store = deps["get_store"](store["id"])
            deps["flash"]("店铺资料已保存。", "success")

        deps["sync_store_boosters"](store)

        if action == "submit_for_review":
            deps["update_store"](
                store["id"],
                {
                    "approval_status": "pending",
                    "review_note": "",
                    "reviewed_at": "",
                    "reviewed_by": "",
                    "updated_at": deps["now_text"](),
                },
            )
            store = deps["get_store"](store["id"])
            deps["notify_admins"](f"店铺 {store['name']} 已提交合规审核。", sender=username)
            deps["flash"]("店铺资料已提交管理员审核。", "success")

        return deps["redirect"](deps["url_for"]("merchant_store"))

    store_card = deps["build_store_card"](store) if store else None
    return deps["render_template"]("merchant_store.html", store=store_card, theme_options=deps["STORE_THEME_OPTIONS"])


def merchant_talents_storefront(deps):
    owner_username = deps["session"]["username"]
    store = deps["get_store_by_owner"](owner_username)
    if not store:
        deps["flash"]("请先完善店铺资料，再处理入驻申请。", "warning")
        return deps["redirect"](deps["url_for"]("merchant_store"))

    if deps["request"].method == "POST":
        action = deps["request"].form.get("action", "").strip()

        if action == "submit_application":
            candidate_username = deps["request"].form.get("username", "").strip()
            candidate_password = deps["request"].form.get("password", "").strip()
            candidate_display_name = deps["request"].form.get("display_name", "").strip() or candidate_username
            candidate_email = deps["normalize_email"](deps["request"].form.get("email", ""))
            candidate_phone = deps["normalize_phone"](deps["request"].form.get("phone", ""))
            candidate_game_account = deps["request"].form.get("game_account", "").strip()
            candidate_games = deps["request"].form.get("games", "").strip()
            candidate_rank = deps["request"].form.get("rank", "").strip()
            candidate_price = deps["request"].form.get("price", "").strip()
            candidate_available_time = deps["request"].form.get("available_time", "").strip()
            candidate_play_style = deps["request"].form.get("play_style", "").strip()
            candidate_intro = deps["request"].form.get("intro", "").strip()
            proof_image = deps["request"].files.get("proof_image")

            if not candidate_username:
                deps["flash"]("请填写候选人的账号名。", "warning")
                return deps["redirect"](deps["url_for"]("merchant_talents"))
            if deps["get_user"](candidate_username):
                deps["flash"]("该账号名已经存在，不能重复提交。", "warning")
                return deps["redirect"](deps["url_for"]("merchant_talents"))
            if deps["find_pending_booster_application_by_username"](candidate_username):
                deps["flash"]("该账号名已经提交过陪玩师申请，请等待审核。", "warning")
                return deps["redirect"](deps["url_for"]("merchant_talents"))
            if not candidate_password:
                deps["flash"]("请先为候选人设置登录密码。", "warning")
                return deps["redirect"](deps["url_for"]("merchant_talents"))
            if candidate_email and not deps["looks_like_email"](candidate_email):
                deps["flash"]("请输入有效的邮箱地址。", "warning")
                return deps["redirect"](deps["url_for"]("merchant_talents"))
            if candidate_email and deps["get_user_by_email"](candidate_email):
                deps["flash"]("该邮箱已经绑定其他账号。", "warning")
                return deps["redirect"](deps["url_for"]("merchant_talents"))
            if candidate_email:
                pending_email_application = deps["find_pending_booster_application_by_email"](candidate_email)
                if pending_email_application and pending_email_application["username"] != candidate_username:
                    deps["flash"]("该邮箱已经提交过陪玩师申请，请等待审核。", "warning")
                    return deps["redirect"](deps["url_for"]("merchant_talents"))
            if candidate_phone and not deps["looks_like_phone"](candidate_phone):
                deps["flash"]("请输入有效的手机号。", "warning")
                return deps["redirect"](deps["url_for"]("merchant_talents"))
            if candidate_phone and deps["get_user_by_phone"](candidate_phone):
                deps["flash"]("该手机号已经绑定其他账号。", "warning")
                return deps["redirect"](deps["url_for"]("merchant_talents"))
            if not candidate_game_account:
                deps["flash"]("请填写候选人的游戏账号。", "warning")
                return deps["redirect"](deps["url_for"]("merchant_talents"))
            if not proof_image or not getattr(proof_image, "filename", ""):
                deps["flash"]("请上传候选人的实力截图。", "warning")
                return deps["redirect"](deps["url_for"]("merchant_talents"))

            try:
                proof_image_path = deps["save_uploaded_image"](
                    proof_image,
                    "uploads",
                    "boosters",
                    "proof",
                    prefix=f"booster_proof_{candidate_username}",
                )
            except ValueError as exc:
                deps["flash"](str(exc), "warning")
                return deps["redirect"](deps["url_for"]("merchant_talents"))

            candidate_profile = {
                "display_name": candidate_display_name,
                "games": candidate_games,
                "rank": candidate_rank,
                "price": candidate_price,
                "available_time": candidate_available_time,
                "play_style": candidate_play_style,
                "intro": candidate_intro,
                "approval_status": "pending",
                "store_id": store["id"],
                "store_slug": store["slug"],
                "store_name": store["name"],
                "managed_by": owner_username,
            }
            deps["add_booster_application"](
                candidate_username,
                candidate_password,
                email=candidate_email,
                phone=candidate_phone,
                auth_provider="local",
                social_id="",
                game_account=candidate_game_account,
                proof_image_path=proof_image_path,
                store_id=store["id"],
                store_owner_username=owner_username,
                store_name=store["name"],
                display_name=candidate_display_name,
                profile=candidate_profile,
            )
            deps["notify_admins"](
                f"店铺 {store['name']} 提交了新的店内陪玩师候选申请：{candidate_display_name or candidate_username}。",
                sender=owner_username,
            )
            deps["flash"]("候选人资料已提交平台审核，审核通过后会自动开通店内陪玩账号。", "success")
            return deps["redirect"](deps["url_for"]("merchant_talents"))

        application_id = deps["safe_int"](deps["request"].form.get("application_id"), default=-1)
        review_note = deps["request"].form.get("review_note", "").strip()
        price_value_raw = deps["request"].form.get("price", "").strip()
        intro_text = deps["request"].form.get("intro", "").strip()

        if action not in {"approve_store_booster_application", "reject_store_booster_application"}:
            deps["flash"]("不支持的操作。", "warning")
            return deps["redirect"](deps["url_for"]("merchant_talents"))

        application = deps["get_booster_application"](application_id)
        if not application:
            deps["flash"]("申请不存在。", "warning")
            return deps["redirect"](deps["url_for"]("merchant_talents"))
        if application.get("status") != "pending":
            deps["flash"]("这条申请已经处理过了。", "warning")
            return deps["redirect"](deps["url_for"]("merchant_talents"))
        if application.get("store_owner_username") != owner_username:
            deps["flash"]("你无权处理该申请。", "warning")
            return deps["redirect"](deps["url_for"]("merchant_talents"))

        applicant = deps["get_user"](application.get("username", ""))
        if not applicant or applicant.get("role") != "booster":
            deps["flash"]("这条申请正在等待平台开通账号，请到“平台审核队列”查看进度。", "warning")
            return deps["redirect"](deps["url_for"]("merchant_talents"))

        applicant_profile = dict(applicant.get("profile") or {})

        if action == "approve_store_booster_application":
            try:
                parsed_price = float(price_value_raw)
            except (TypeError, ValueError):
                parsed_price = 0.0
            if parsed_price < 20:
                deps["flash"]("通过申请前，请填写有效单价（不低于 20）。", "warning")
                return deps["redirect"](deps["url_for"]("merchant_talents"))
            if not intro_text:
                deps["flash"]("通过申请前，请填写打手介绍。", "warning")
                return deps["redirect"](deps["url_for"]("merchant_talents"))
            if len(intro_text) < 15:
                deps["flash"]("通过申请前，打手介绍至少填写 15 个字。", "warning")
                return deps["redirect"](deps["url_for"]("merchant_talents"))

            approval_note = review_note or "店铺审核通过，已加入店内排班。"
            applicant_profile.update(
                {
                    "store_id": store["id"],
                    "store_slug": store["slug"],
                    "store_name": store["name"],
                    "managed_by": owner_username,
                    "approval_status": "approved",
                    "approval_review_note": approval_note,
                    "display_name": application.get("display_name") or applicant_profile.get("display_name") or applicant["username"],
                    "game_account": application.get("game_account") or applicant_profile.get("game_account", ""),
                    "proof_image_path": application.get("proof_image_path") or applicant_profile.get("proof_image_path", ""),
                    "price": f"{parsed_price:.2f}".rstrip("0").rstrip("."),
                    "intro": intro_text,
                }
            )
            if not applicant_profile.get("cover_theme"):
                applicant_profile["cover_theme"] = store.get("theme") or "graphite"

            deps["update_user"](applicant["username"], {"profile": applicant_profile})
            deps["update_booster_application"](
                application_id,
                {
                    "status": "approved",
                    "review_note": approval_note,
                    "reviewed_at": deps["now_text"](),
                    "reviewed_by": owner_username,
                },
            )
            deps["notify_user"](
                applicant["username"],
                f"你的入驻申请已被 {store['name']} 通过，可以开始在店内接单。",
                sender=owner_username,
            )
            deps["flash"]("已通过该打手入驻申请。", "success")
        else:
            rejection_note = review_note or "店铺当前不匹配你的接单方向，可调整资料后再申请。"
            deps["update_booster_application"](
                application_id,
                {
                    "status": "rejected",
                    "review_note": rejection_note,
                    "reviewed_at": deps["now_text"](),
                    "reviewed_by": owner_username,
                },
            )
            deps["notify_user"](
                application.get("username", ""),
                f"你的入驻申请被 {store['name']} 拒绝：{rejection_note}",
                sender=owner_username,
            )
            deps["flash"]("已拒绝该打手入驻申请。", "success")

        return deps["redirect"](deps["url_for"]("merchant_talents"))

    boosters = deps["get_store_boosters"](owner_username=owner_username)
    pending_store_review_applications = []
    pending_platform_review_applications = []
    for item in deps["get_store_applications_for_owner"](owner_username, status="pending"):
        applicant = deps["get_user"](item.get("username", ""))
        if applicant and applicant.get("role") == "booster":
            pending_store_review_applications.append(item)
        else:
            pending_platform_review_applications.append(item)
    reviewed_applications = [item for item in deps["get_store_applications_for_owner"](owner_username) if item["status"] != "pending"][:10]
    return deps["render_template"](
        "merchant_talents.html",
        store=deps["build_store_card"](store),
        boosters=boosters,
        pending_applications=pending_store_review_applications,
        pending_platform_review_applications=pending_platform_review_applications,
        reviewed_applications=reviewed_applications,
        theme_options=deps["STORE_THEME_OPTIONS"],
    )


def admin_users_storefront(deps):
    if deps["request"].method == "POST":
        action = deps["request"].form.get("action", "").strip()

        if action in {"approve_store", "reject_store"}:
            store_id = deps["safe_int"](deps["request"].form.get("store_id"), default=-1)
            review_note = deps["request"].form.get("review_note", "").strip()
            store = deps["get_store"](store_id)
            if not store:
                deps["flash"]("店铺不存在。", "warning")
                return deps["redirect"](deps["url_for"]("admin_users"))
            fields = {
                "approval_status": "approved" if action == "approve_store" else "rejected",
                "review_note": review_note or ("资料合规，允许上架。" if action == "approve_store" else "资料需补充，请修改后重新提交。"),
                "reviewed_at": deps["now_text"](),
                "reviewed_by": deps["session"].get("username", "admin"),
                "updated_at": deps["now_text"](),
            }
            deps["update_store"](store_id, fields)
            store = deps["get_store"](store_id)
            deps["notify_user"](
                store["owner_username"],
                f"店铺 {store['name']} 的审核结果：{deps['store_review_label'](store)}。{fields['review_note']}",
                sender=deps["session"]["username"],
            )
            deps["flash"]("店铺审核结果已保存。", "success")
            return deps["redirect"](deps["url_for"]("admin_users"))

        if action in {"approve_booster_application", "reject_booster_application"}:
            application_id = deps["safe_int"](deps["request"].form.get("application_id"), default=-1)
            review_note = deps["request"].form.get("review_note", "").strip()
            application = deps["get_booster_application"](application_id)

            if not application:
                deps["flash"]("陪玩师申请不存在。", "warning")
                return deps["redirect"](deps["url_for"]("admin_users"))
            if application["status"] != "pending":
                deps["flash"]("这条申请已经处理过了。", "warning")
                return deps["redirect"](deps["url_for"]("admin_users"))

            has_store_binding = bool(application.get("store_id") or application.get("store_owner_username"))
            store = deps["get_store"](application["store_id"]) if application.get("store_id") else None
            if has_store_binding and not store and application.get("store_owner_username"):
                store = deps["get_store_by_owner"](application["store_owner_username"])
            if has_store_binding and not store:
                deps["flash"]("该申请没有有效的归属店铺，暂时不能处理。", "warning")
                return deps["redirect"](deps["url_for"]("admin_users"))
            if has_store_binding and action == "approve_booster_application" and not deps["store_is_approved"](store):
                deps["flash"]("请先完成店铺合规审核，再审核店内陪玩师。", "warning")
                return deps["redirect"](deps["url_for"]("admin_users"))

            if action == "approve_booster_application":
                if deps["get_user"](application["username"]):
                    deps["flash"]("该用户名已被占用，无法通过审核。", "warning")
                    return deps["redirect"](deps["url_for"]("admin_users"))

                existing_email_owner = deps["find_user_by_email"](application["email"]) if application.get("email") and not application["email"].endswith("@pending.local") else None
                if existing_email_owner and existing_email_owner["username"] != application["username"]:
                    deps["flash"]("该邮箱已绑定其他账号，无法通过审核。", "warning")
                    return deps["redirect"](deps["url_for"]("admin_users"))

                existing_phone_owner = deps["get_user_by_phone"](application["phone"]) if application.get("phone") else None
                if existing_phone_owner and existing_phone_owner["username"] != application["username"]:
                    deps["flash"]("该手机号已绑定其他账号，无法通过审核。", "warning")
                    return deps["redirect"](deps["url_for"]("admin_users"))

                approval_note = review_note or ("店铺资料和陪玩实力信息完整，审核通过。" if has_store_binding else "资料完整，审核通过。")
                profile = dict(application.get("profile") or {})
                common_profile_fields = {
                    "display_name": application.get("display_name") or profile.get("display_name") or application["username"],
                    "email": "" if application["email"].endswith("@pending.local") else application["email"],
                    "phone": application.get("phone", ""),
                    "game_account": application["game_account"],
                    "proof_image_path": application["proof_image_path"],
                    "approval_status": "approved",
                    "approval_review_note": approval_note,
                    "auth_provider": application.get("auth_provider", "local"),
                }
                if has_store_binding:
                    common_profile_fields.update(
                        {
                            "store_id": store["id"],
                            "store_slug": store["slug"],
                            "store_name": store["name"],
                            "managed_by": store["owner_username"],
                        }
                    )
                    if not profile.get("cover_theme"):
                        profile["cover_theme"] = store.get("theme") or "graphite"
                else:
                    common_profile_fields.setdefault("store_id", "")
                    common_profile_fields.setdefault("store_slug", "")
                    common_profile_fields.setdefault("store_name", "")
                    common_profile_fields.setdefault("managed_by", "")
                profile.update(common_profile_fields)
                deps["add_user"](
                    application["username"],
                    application["password"],
                    "booster",
                    profile=profile,
                    email="" if application["email"].endswith("@pending.local") else application["email"],
                    phone=application.get("phone", ""),
                    auth_provider=application.get("auth_provider", "local"),
                    social_id=application.get("social_id", ""),
                )
                deps["update_booster_application"](
                    application_id,
                    {
                        "status": "approved",
                        "review_note": approval_note,
                        "reviewed_at": deps["now_text"](),
                        "reviewed_by": deps["session"].get("username", "admin"),
                    },
                )
                deps["notify_user"](
                    application["username"],
                    f"你的陪玩师申请已通过平台审核{'，现已归属 ' + store['name'] if has_store_binding else ''}并开通账号。",
                    sender=deps["session"]["username"],
                )
                if has_store_binding:
                    deps["notify_user"](store["owner_username"], f"店内陪玩师 {profile['display_name']} 已通过平台审核。", sender=deps["session"]["username"])
                try:
                    if application.get("email") and not application["email"].endswith("@pending.local"):
                        deps["send_booster_application_review_email"](application, True, approval_note)
                except Exception as exc:
                    print(f"[DEBUG] Failed to send booster approval email: {exc}", file=sys.stderr)
                deps["flash"]("陪玩师申请已审核通过，账号已创建。", "success")
            else:
                rejection_note = review_note or "资料不完整或需补充说明，请修改后重新提交。"
                deps["update_booster_application"](
                    application_id,
                    {
                        "status": "rejected",
                        "review_note": rejection_note,
                        "reviewed_at": deps["now_text"](),
                        "reviewed_by": deps["session"].get("username", "admin"),
                    },
                )
                if has_store_binding:
                    deps["notify_user"](
                        store["owner_username"],
                        f"店内陪玩师申请 {application.get('display_name') or application['username']} 未通过审核：{rejection_note}",
                        sender=deps["session"]["username"],
                    )
                try:
                    if application.get("email") and not application["email"].endswith("@pending.local"):
                        deps["send_booster_application_review_email"](application, False, rejection_note)
                except Exception as exc:
                    print(f"[DEBUG] Failed to send booster rejection email: {exc}", file=sys.stderr)
                deps["flash"]("陪玩师申请已驳回。", "success")
            return deps["redirect"](deps["url_for"]("admin_users"))

        if action in {"approve_merchant_application", "reject_merchant_application"}:
            application_id = deps["safe_int"](deps["request"].form.get("merchant_application_id"), default=-1)
            review_note = deps["request"].form.get("review_note", "").strip()
            application = deps["get_merchant_application"](application_id)

            if not application:
                deps["flash"]("商家申请不存在。", "warning")
                return deps["redirect"](deps["url_for"]("admin_users"))
            if application["status"] != "pending":
                deps["flash"]("这条商家申请已经处理过了。", "warning")
                return deps["redirect"](deps["url_for"]("admin_users"))

            if action == "approve_merchant_application":
                if deps["get_user"](application["username"]):
                    deps["flash"]("该用户名已被占用，无法通过审核。", "warning")
                    return deps["redirect"](deps["url_for"]("admin_users"))

                existing_email_owner = deps["find_user_by_email"](application["email"]) if application.get("email") else None
                if existing_email_owner and existing_email_owner["username"] != application["username"]:
                    deps["flash"]("该邮箱已绑定其他账号，无法通过审核。", "warning")
                    return deps["redirect"](deps["url_for"]("admin_users"))

                existing_phone_owner = deps["get_user_by_phone"](application["phone"]) if application.get("phone") else None
                if existing_phone_owner and existing_phone_owner["username"] != application["username"]:
                    deps["flash"]("该手机号已绑定其他账号，无法通过审核。", "warning")
                    return deps["redirect"](deps["url_for"]("admin_users"))

                approval_note = review_note or "资料齐全，允许商家入驻。"
                profile = dict(application.get("profile") or {})
                profile.update(
                    {
                        "display_name": profile.get("display_name") or application["username"],
                        "store_name": application.get("store_name", ""),
                        "store_city": application.get("store_city", ""),
                        "business_license_path": application.get("business_license_path", ""),
                        "id_proof_path": application.get("id_proof_path", ""),
                        "approval_status": "approved",
                        "approval_review_note": approval_note,
                        "auth_provider": application.get("auth_provider", "local"),
                    }
                )
                deps["add_user"](
                    application["username"],
                    application["password"],
                    "merchant",
                    profile=profile,
                    email=application["email"],
                    phone=application.get("phone", ""),
                    auth_provider=application.get("auth_provider", "local"),
                    social_id=application.get("social_id", ""),
                )
                deps["update_merchant_application"](
                    application_id,
                    {
                        "status": "approved",
                        "review_note": approval_note,
                        "reviewed_at": deps["now_text"](),
                        "reviewed_by": deps["session"].get("username", "admin"),
                    },
                )
                try:
                    deps["send_merchant_application_review_email"](application, True, approval_note)
                except Exception as exc:
                    print(f"[DEBUG] Failed to send merchant approval email: {exc}", file=sys.stderr)
                deps["flash"]("商家申请已审核通过，账号已创建。", "success")
            else:
                rejection_note = review_note or "资质资料不完整或不清晰，请补充后重试。"
                deps["update_merchant_application"](
                    application_id,
                    {
                        "status": "rejected",
                        "review_note": rejection_note,
                        "reviewed_at": deps["now_text"](),
                        "reviewed_by": deps["session"].get("username", "admin"),
                    },
                )
                try:
                    deps["send_merchant_application_review_email"](application, False, rejection_note)
                except Exception as exc:
                    print(f"[DEBUG] Failed to send merchant rejection email: {exc}", file=sys.stderr)
                deps["flash"]("商家申请已驳回。", "success")
            return deps["redirect"](deps["url_for"]("admin_users"))

        return deps["admin_users_view"]()

    users = deps["all_users"]()
    pending_store_applications = [deps["build_store_card"](store) for store in deps["get_all_stores"]() if (store.get("approval_status") or "pending") == "pending"]
    reviewed_store_applications = [deps["build_store_card"](store) for store in deps["get_all_stores"]() if (store.get("approval_status") or "pending") != "pending"][:10]
    pending_booster_applications = deps["get_booster_applications"](status="pending")
    reviewed_booster_applications = [application for application in deps["get_booster_applications"]() if application["status"] != "pending"][:10]
    pending_merchant_applications = deps["get_merchant_applications"](status="pending")
    reviewed_merchant_applications = [application for application in deps["get_merchant_applications"]() if application["status"] != "pending"][:10]
    return deps["render_template"](
        "admin_users.html",
        users=users,
        pending_store_applications=pending_store_applications,
        reviewed_store_applications=reviewed_store_applications,
        pending_booster_applications=pending_booster_applications,
        reviewed_booster_applications=reviewed_booster_applications,
        pending_merchant_applications=pending_merchant_applications,
        reviewed_merchant_applications=reviewed_merchant_applications,
    )


def choose_role_storefront(deps):
    if deps["session"].get("username"):
        return deps["redirect_to_dashboard"]()

    onboarding = deps["get_auth_onboarding"]()
    if not onboarding:
        deps["flash"]("请先完成登录或注册。", "warning")
        return deps["redirect"](deps["url_for"]("login"))

    form_username = deps["request"].form.get("username", "").strip() if deps["request"].method == "POST" else ""
    form_email = deps["normalize_email"](deps["request"].form.get("email", "")) if deps["request"].method == "POST" else ""
    form_phone = deps["normalize_phone"](deps["request"].form.get("phone", "")) if deps["request"].method == "POST" else ""
    selected_role = deps["request"].form.get("role", "").strip() if deps["request"].method == "POST" else "player"

    if deps["request"].method == "POST":
        role = selected_role
        username = form_username or (onboarding.get("preferred_username") or "").strip()
        email = form_email or deps["normalize_email"](onboarding.get("email", ""))
        phone = form_phone or deps["normalize_phone"](onboarding.get("phone", ""))
        auth_provider = onboarding.get("auth_provider", "local")
        social_id = onboarding.get("social_id", "")

        if role not in {"player", "booster", "merchant"}:
            deps["flash"]("请选择有效身份。", "warning")
        elif not username:
            deps["flash"]("请填写一个昵称。", "warning")
        elif username.lower() in deps["RESERVED_USERNAMES"]:
            deps["flash"]("这个昵称已被系统保留，请换一个。", "warning")
        elif deps["get_user"](username):
            deps["flash"]("这个昵称已经有人使用了，请换一个。", "warning")
        elif role == "booster" and deps["find_pending_booster_application_by_username"](username):
            deps["flash"]("该昵称已经提交过陪玩师申请，请等待审核。", "warning")
        elif email and not deps["looks_like_email"](email):
            deps["flash"]("请输入有效的邮箱地址。", "warning")
        elif phone and not deps["looks_like_phone"](phone):
            deps["flash"]("请输入有效的手机号。", "warning")
        else:
            existing_email_user = deps["get_user_by_email"](email) if email else None
            existing_phone_user = deps["get_user_by_phone"](phone) if phone else None

            if existing_email_user:
                deps["flash"]("这个邮箱已经绑定了其他账号。", "warning")
            elif existing_phone_user:
                deps["flash"]("这个手机号已经绑定了其他账号。", "warning")
            elif role == "booster":
                pending_email_application = deps["find_pending_booster_application_by_email"](email) if email else None
                if pending_email_application and pending_email_application["username"] != username:
                    deps["flash"]("该邮箱已提交过陪玩师申请，请等待审核。", "warning")
                    return deps["render_template"](
                        "choose_role.html",
                        onboarding=onboarding,
                        provider_label=("邮箱" if onboarding.get("auth_provider", "local") == "local" else deps["SOCIAL_PROVIDER_LABELS"].get(onboarding.get("auth_provider", "local"), onboarding.get("auth_provider", "local"))),
                        suggested_username=form_username or onboarding.get("preferred_username") or deps["unique_username_from_seed"](onboarding.get("auth_provider", "local"), onboarding.get("auth_provider", "local") or "gb"),
                        suggested_email=form_email or deps["normalize_email"](onboarding.get("email", "")),
                        suggested_phone=form_phone or deps["normalize_phone"](onboarding.get("phone", "")),
                        selected_role=selected_role or "player",
                        launch_image_url=deps["url_for"]("static", filename="images/gamebuddy-launch-source.png"),
                    )
                game_name = deps["request"].form.get("game_name", "").strip()
                game_id = deps["request"].form.get("game_id", "").strip()
                rank = deps["request"].form.get("rank", "").strip()
                intro = deps["request"].form.get("intro", "").strip()
                proof_image = deps["request"].files.get("proof_image")
                if not game_name:
                    deps["flash"]("请填写游戏名称。", "warning")
                elif not game_id:
                    deps["flash"]("请填写游戏 ID。", "warning")
                elif not proof_image or not getattr(proof_image, "filename", ""):
                    deps["flash"]("请上传段位或战绩截图。", "warning")
                else:
                    try:
                        proof_image_path = deps["save_uploaded_image"](
                            proof_image,
                            "uploads",
                            "boosters",
                            "proof",
                            prefix=f"booster_proof_{username}",
                        )
                    except ValueError as exc:
                        deps["flash"](str(exc), "warning")
                    else:
                        profile = {
                            "display_name": username,
                            "auth_provider": auth_provider,
                            "games": game_name,
                            "game_id": game_id,
                            "rank": rank,
                            "intro": intro,
                            "approval_status": "pending",
                        }
                        deps["add_booster_application"](
                            username,
                            onboarding.get("password", ""),
                            email=email,
                            phone=phone,
                            auth_provider=auth_provider,
                            social_id=social_id,
                            game_account=f"{game_name} / {game_id}",
                            proof_image_path=proof_image_path,
                            profile=profile,
                        )
                        deps["clear_auth_onboarding"]()
                        if email:
                            deps["flash"]("陪玩师资料已提交，管理员审核后会通过邮箱通知结果。", "success")
                        else:
                            deps["flash"]("陪玩师资料已提交，请使用用户名与密码在登录页查询审核进度。", "success")
                        return deps["redirect"](deps["url_for"]("login"))
            elif role == "merchant" and deps["find_pending_merchant_application_by_username"](username):
                deps["flash"]("该昵称已经提交过商家入驻申请，请等待审核。", "warning")
            elif role == "merchant" and email and deps["find_pending_merchant_application_by_email"](email):
                deps["flash"]("该邮箱已经提交过商家入驻申请，请等待审核。", "warning")
            elif role == "merchant":
                store_name = deps["request"].form.get("store_name", "").strip()
                store_city = deps["request"].form.get("store_city", "").strip()
                business_license = deps["request"].files.get("business_license")
                id_proof = deps["request"].files.get("id_proof")

                if not store_name:
                    deps["flash"]("请填写店铺名称。", "warning")
                elif not business_license or not getattr(business_license, "filename", ""):
                    deps["flash"]("请上传营业执照或经营资质图片。", "warning")
                elif not id_proof or not getattr(id_proof, "filename", ""):
                    deps["flash"]("请上传经营者身份资料图片。", "warning")
                else:
                    try:
                        business_license_path = deps["save_uploaded_image"](
                            business_license,
                            "uploads",
                            "stores",
                            "proof",
                            prefix=f"merchant_license_{username}",
                        )
                        id_proof_path = deps["save_uploaded_image"](
                            id_proof,
                            "uploads",
                            "stores",
                            "proof",
                            prefix=f"merchant_id_{username}",
                        )
                    except ValueError as exc:
                        deps["flash"](str(exc), "warning")
                    else:
                        profile = {
                            "display_name": username,
                            "auth_provider": auth_provider,
                        }
                        deps["add_merchant_application"](
                            username,
                            onboarding.get("password", ""),
                            email=email,
                            phone=phone,
                            auth_provider=auth_provider,
                            social_id=social_id,
                            store_name=store_name,
                            store_city=store_city,
                            business_license_path=business_license_path,
                            id_proof_path=id_proof_path,
                            profile=profile,
                        )
                        deps["clear_auth_onboarding"]()
                        if email:
                            deps["flash"]("商家入驻资料已提交，管理员审核后会通过邮箱通知结果。", "success")
                        else:
                            deps["flash"]("商家入驻资料已提交，请使用用户名与密码在登录页查询审核进度。", "success")
                        return deps["redirect"](deps["url_for"]("login"))
            else:
                profile = {"display_name": username, "auth_provider": auth_provider}
                deps["add_user"](
                    username,
                    onboarding.get("password", ""),
                    role,
                    profile=profile,
                    email=email,
                    phone=phone,
                    auth_provider=auth_provider,
                    social_id=social_id,
                )
                user = deps["get_user"](username)
                deps["clear_auth_onboarding"]()
                deps["log_user_in"](user)
                deps["flash"]("注册完成，欢迎来到 GameBuddy。", "success")
                return deps["redirect_to_dashboard"]()

    provider = onboarding.get("auth_provider", "local")
    provider_label = "邮箱" if provider == "local" else deps["SOCIAL_PROVIDER_LABELS"].get(provider, provider)
    suggested_username = form_username or onboarding.get("preferred_username") or deps["unique_username_from_seed"](provider, provider or "gb")
    suggested_email = form_email or deps["normalize_email"](onboarding.get("email", ""))
    suggested_phone = form_phone or deps["normalize_phone"](onboarding.get("phone", ""))
    return deps["render_template"](
        "choose_role.html",
        onboarding=onboarding,
        provider_label=provider_label,
        suggested_username=suggested_username,
        suggested_email=suggested_email,
        suggested_phone=suggested_phone,
        selected_role=selected_role or "player",
        launch_image_url=deps["url_for"]("static", filename="images/gamebuddy-launch-source.png"),
    )
