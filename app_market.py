def build_booster_card(user, deps):
    if not user:
        return None
    profile = dict(user.get("profile", {}) or {})
    linked_store = deps["get_store_for_profile"](profile)
    stats = deps["booster_order_stats"](user["username"])
    seed_completed_orders = deps["safe_int"](profile.get("display_completed_orders"), 0)
    seed_total_orders = deps["safe_int"](profile.get("display_total_orders"), seed_completed_orders)
    seed_avg_rating = deps["parse_rating"](profile.get("display_avg_rating"))
    display_completed_orders = max(stats["completed_orders"], seed_completed_orders)
    display_total_orders = max(stats["total_orders"], seed_total_orders, display_completed_orders)
    display_avg_rating = stats["avg_rating"] or seed_avg_rating
    display_active_orders = max(stats["active_orders"], deps["safe_int"](profile.get("display_active_orders"), 0))
    display_completion_rate = round((display_completed_orders / display_total_orders) * 100, 1) if display_total_orders else 0
    recommendation_score = (display_avg_rating or 4.6) * 20 + display_completed_orders * 2 - display_active_orders * 2
    tags = deps["split_tags"](profile.get("persona_tags"))
    price_value = deps["safe_float"](profile.get("price"), default=999999)
    display_name = (profile.get("display_name") or user["username"]).strip() or user["username"]
    approval_status = (profile.get("approval_status") or "approved").strip() or "approved"
    store_title = display_name if not linked_store else f"{linked_store['name']} · {display_name}"
    return {
        **user,
        "display_name": display_name,
        "store_title": store_title,
        "profile": {
            "display_name": display_name,
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
            "badge": profile.get("badge", "店铺认证陪玩" if linked_store else ""),
            "response_time": profile.get("response_time", ""),
            "status_text": profile.get("status_text", ""),
            "cover_theme": profile.get("cover_theme", linked_store["theme"] if linked_store else "graphite"),
            "persona_tags": tags,
            "avatar_path": profile.get("avatar_path", ""),
            "avatar_url": deps["image_url"](profile.get("avatar_path", "")),
            "cover_path": profile.get("cover_path", ""),
            "cover_url": deps["image_url"](profile.get("cover_path", "")),
            "approval_status": approval_status,
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
        "avatar_text": display_name[:1].upper(),
    }


def get_store_boosters(store_id, owner_username, deps):
    boosters = []
    for user in deps["all_users"]():
        if user["role"] != "booster" or user.get("banned"):
            continue
        booster = deps["build_booster_card"](user)
        if not booster:
            continue
        profile = booster["profile"]
        if profile.get("approval_status") != "approved":
            continue
        if not profile.get("store_id") and not profile.get("managed_by"):
            continue
        if store_id and str(profile.get("store_id", "")) != str(store_id):
            continue
        if owner_username and profile.get("managed_by") != owner_username:
            continue
        boosters.append(booster)
    boosters.sort(key=lambda item: (-item["stats"]["recommendation_score"], item["price_value"]))
    return boosters


def build_store_card(store, deps):
    if not store:
        return None
    boosters = deps["get_store_boosters"](store_id=store["id"], owner_username=store["owner_username"])
    ratings = [booster["stats"]["avg_rating"] for booster in boosters if booster["stats"]["avg_rating"]]
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None
    completed_orders = sum(deps["safe_int"](booster["stats"]["completed_orders"], 0) for booster in boosters)
    active_orders = sum(deps["safe_int"](booster["stats"]["active_orders"], 0) for booster in boosters)
    min_prices = [deps["safe_float"](booster["profile"].get("price"), 0) for booster in boosters if deps["safe_float"](booster["profile"].get("price"), 0) > 0]
    base_min_price = deps["safe_float"](store.get("min_price"), 0)
    if base_min_price > 0:
        min_prices.append(base_min_price)
    min_price_value = min(min_prices) if min_prices else 0
    max_price_value = max(min_prices) if min_prices else 0
    owner_user = deps["get_user"](store["owner_username"])
    owner_profile = owner_user.get("profile", {}) if owner_user else {}
    pending_talent_count = len([item for item in deps["get_booster_applications"](status="pending") if item["store_owner_username"] == store["owner_username"]])
    return {
        **store,
        "boosters": boosters,
        "booster_count": len(boosters),
        "avg_rating": avg_rating,
        "completed_orders": completed_orders,
        "active_orders": active_orders,
        "price_text": deps["format_price_text"](min_price_value or store.get("min_price")),
        "min_price_value": min_price_value,
        "max_price_value": max_price_value,
        "hero_text": store.get("tagline") or store.get("description") or "店铺接待统一派单，服务更稳定。",
        "logo_text": (store.get("name") or "店铺")[:2],
        "owner_display_name": owner_profile.get("display_name") or store["owner_username"],
        "review_label": deps["store_review_label"](store),
        "review_badge": deps["store_review_badge"](store),
        "is_public": deps["store_is_approved"](store),
        "pending_talent_count": pending_talent_count,
    }


def get_merchant_orders(owner_username, deps):
    orders = []
    for order in deps["get_all_orders"]():
        if order.get("store_owner") == owner_username:
            orders.append(order)
            continue
        booster_name = order.get("assigned_booster") or order.get("booster")
        if not booster_name:
            continue
        booster_user = deps["get_user"](booster_name)
        profile = booster_user.get("profile", {}) if booster_user else {}
        if profile.get("managed_by") == owner_username:
            orders.append(order)
    return orders


def get_merchant_stats(owner_username, deps):
    store = deps["get_store_by_owner"](owner_username)
    store_boosters = deps["get_store_boosters"](owner_username=owner_username)
    orders = deps["get_merchant_orders"](owner_username)
    completed_orders = [order for order in orders if order["status"] == "已完成"]
    pending_orders = [order for order in orders if order["status"] in {"待接待", "已接单", "待确认完成"}]
    gmv = round(sum(deps["safe_float"](order["price"]) for order in completed_orders), 2)
    ratings = [booster["stats"]["avg_rating"] for booster in store_boosters if booster["stats"]["avg_rating"]]
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None
    return {
        "store": store,
        "booster_count": len(store_boosters),
        "orders_count": len(orders),
        "completed_orders": len(completed_orders),
        "pending_orders": len(pending_orders),
        "gmv": gmv,
        "avg_rating": avg_rating,
    }


def filter_and_rank_boosters(filters, limit, deps):
    filters = filters or {}
    boosters = []
    for user in deps["all_users"]():
        if user["role"] != "booster" or user.get("banned"):
            continue
        booster = deps["build_booster_card"](user)
        if not booster or booster["profile"].get("approval_status") != "approved":
            continue
        if not booster["profile"].get("store_id"):
            continue
        linked_store = deps["get_store_for_profile"](booster["profile"])
        if not deps["store_is_approved"](linked_store):
            continue
        boosters.append(booster)

    game = (filters.get("game") or "").strip().lower()
    rank = (filters.get("rank") or "").strip().lower()
    availability = (filters.get("availability") or "").strip().lower()
    max_price = deps["safe_float"](filters.get("max_price"), default=0)
    sort_by = filters.get("sort") or "recommended"

    def matched(booster):
        profile = booster["profile"]
        if game and game not in profile.get("games", "").lower():
            return False
        if rank and rank not in profile.get("rank", "").lower():
            return False
        if availability and availability not in profile.get("available_time", "").lower():
            return False
        if max_price and deps["safe_float"](profile.get("price"), default=999999) > max_price:
            return False
        return True

    boosters = [booster for booster in boosters if matched(booster)]

    if sort_by == "price_asc":
        boosters.sort(key=lambda item: (item["price_value"], -item["stats"]["completed_orders"]))
    elif sort_by == "rating_desc":
        boosters.sort(key=lambda item: (-(item["stats"]["avg_rating"] or 0), item["price_value"]))
    else:
        boosters.sort(key=lambda item: (-item["stats"]["recommendation_score"], item["price_value"], -item["stats"]["completed_orders"]))

    return boosters[:limit] if limit else boosters


def get_top_boosters(limit, deps):
    return deps["filter_and_rank_boosters"]({"sort": "recommended"}, limit=limit)


def filter_and_rank_stores(filters, limit, include_pending, owner_username, deps):
    filters = filters or {}
    cards = []
    keyword = (filters.get("q") or filters.get("keyword") or "").strip().lower()
    game = (filters.get("game") or "").strip().lower()
    if game in {"其他游戏", "其它游戏"}:
        game = ""
    game_aliases = {
        "三角洲行动": ["三角洲行动", "绝地求生", "CS2", "APEX"],
    }
    game_terms = game_aliases.get(game, [game]) if game else []
    price_bucket = (filters.get("price_bucket") or "").strip()
    min_price = deps["safe_float"](filters.get("min_price"), default=0)
    max_price = deps["safe_float"](filters.get("max_price"), default=0)
    sort_by = (filters.get("sort") or "recommended").strip() or "recommended"

    if price_bucket == "under_30":
        max_price = 30
    elif price_bucket == "30_60":
        min_price = 30
        max_price = 60
    elif price_bucket == "over_60":
        min_price = 60

    keyword_aliases = {
        "上分": ["上分", "排位", "高分", "冲分"],
        "娱乐": ["娱乐", "陪伴", "开黑", "放松"],
        "女陪": ["女陪", "女队", "甜妹", "小姐姐"],
        "车队": ["车队", "开黑", "指挥", "枪男"],
    }
    keyword_terms = keyword_aliases.get(keyword, [keyword]) if keyword else []

    for store in deps["get_all_stores"]():
        if owner_username and store["owner_username"] != owner_username:
            continue
        if not include_pending and not deps["store_is_approved"](store):
            continue
        card = deps["build_store_card"](store)
        if not card:
            continue
        search_blob = " ".join(
            [
                card.get("name", ""),
                card.get("tagline", ""),
                card.get("description", ""),
                card.get("games_text", ""),
                card.get("city", ""),
            ]
        ).lower()
        if keyword_terms and not any(term in search_blob for term in keyword_terms):
            continue
        games_text = card.get("games_text", "").lower()
        if game_terms and not any(term.lower() in games_text for term in game_terms):
            continue
        store_min_price = deps["safe_float"](card.get("min_price_value"), 0)
        store_max_price = deps["safe_float"](card.get("max_price_value"), 0)
        if store_max_price <= 0:
            store_max_price = store_min_price

        # Use store price band overlap against selected range.
        if min_price and max_price:
            if store_max_price < min_price or store_min_price > max_price:
                continue
        elif min_price:
            if store_max_price < min_price:
                continue
        elif max_price:
            if store_min_price > max_price:
                continue
        cards.append(card)

    if sort_by == "price_asc":
        cards.sort(key=lambda item: (item["min_price_value"] or 999999, -(item["completed_orders"] or 0)))
    elif sort_by == "rating_desc":
        cards.sort(key=lambda item: (-(item["avg_rating"] or 0), item["min_price_value"] or 999999))
    else:
        cards.sort(
            key=lambda item: (
                -int(bool(item.get("is_featured"))),
                -(item["avg_rating"] or 0),
                -(item["booster_count"] or 0),
                -(item["completed_orders"] or 0),
                item["min_price_value"] or 999999,
            )
        )

    return cards[:limit] if limit else cards


def get_featured_stores(limit, deps):
    featured_cards = deps["filter_and_rank_stores"]({"sort": "recommended"}, include_pending=False)
    return featured_cards[:limit] if limit else featured_cards


def get_player_stats(username, deps):
    orders = deps["get_orders_for_player"](username)
    completed_orders = [order for order in orders if order["status"] == "已完成"]
    complaint_orders = [order for order in orders if order["complaint_status"] in {"待处理", "处理中"}]
    pending_orders = [order for order in orders if order["status"] in {"待接待", "已接单", "待确认完成"}]
    total_spend = round(sum(deps["safe_float"](order["price"]) for order in completed_orders), 2)
    return {
        "total_orders": len(orders),
        "pending_orders": len(pending_orders),
        "completed_orders": len(completed_orders),
        "complaint_orders": len(complaint_orders),
        "total_spend": total_spend,
    }


def notify_merchant_for_order(order, message, sender, deps):
    if not order:
        return
    owner_username = (order.get("store_owner") or "").strip()
    if owner_username:
        deps["notify_user"](owner_username, message, sender=sender)
        return
    booster_username = order.get("assigned_booster") or order.get("booster")
    if booster_username:
        deps["notify_merchant_for_booster"](booster_username, message, sender=sender)


def create_order_notifications(order, sender, deps):
    store_name = order.get("store_name") or "店铺"
    deps["notify_user"](
        order["player"],
        f"订单 #{order['id']} 已进入 {store_name} 接待大厅，店铺会尽快为你安排陪玩师。",
        sender=sender or deps["SYSTEM_USERNAME"],
    )
    assigned_booster = order.get("assigned_booster") or order.get("booster")
    if assigned_booster:
        deps["notify_user"](
            assigned_booster,
            f"你收到来自 {order['player']} 的新订单 #{order['id']}，请尽快响应。",
            sender=sender or order["player"],
        )
    deps["notify_merchant_for_order"](
        order,
        f"{store_name} 收到新订单 #{order['id']}，请尽快安排接待和分配陪玩师。",
        sender=sender or order["player"],
    )
