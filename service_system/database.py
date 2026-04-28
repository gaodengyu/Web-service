from __future__ import annotations


def build_discovery_snapshot(filters, deps):
    active_filters = {
        "q": (filters or {}).get("q", ""),
        "game": (filters or {}).get("game", ""),
        "max_price": (filters or {}).get("max_price", ""),
        "sort": (filters or {}).get("sort", "recommended"),
    }
    return {
        "filters": active_filters,
        "stores": deps["filter_and_rank_stores"](filters=active_filters),
        "featured": deps["get_featured_stores"](limit=4),
    }


def get_public_store_snapshot(store_slug, deps):
    store = deps["get_store_by_slug"](store_slug)
    if not store or not deps["public_store_access_allowed"](store):
        return None
    return deps["build_store_card"](store)


def build_dashboard_snapshot(user, deps):
    username = user["username"]
    role = user["role"]

    if role == "player":
        return {
            "role": role,
            "stats": deps["get_player_stats"](username),
            "orders": [deps["decorate_order_for_view"](order) for order in deps["get_orders_for_player"](username)[:6]],
            "recommended_stores": deps["get_featured_stores"](limit=4),
            "notifications": deps["get_notifications_for_user"](username, limit=8),
        }

    if role == "booster":
        profile = user.get("profile", {})
        store = deps["get_store_for_profile"](profile)
        return {
            "role": role,
            "stats": deps["booster_order_stats"](username),
            "orders": [deps["decorate_order_for_view"](order) for order in deps["get_orders_for_booster"](username)[:6]],
            "notifications": deps["get_notifications_for_user"](username, limit=8),
            "profile_completion": deps["profile_completion"](profile),
            "store": deps["build_store_card"](store) if store else None,
        }

    if role == "merchant":
        stats = deps["get_merchant_stats"](username)
        return {
            "role": role,
            "stats": stats,
            "store": deps["build_store_card"](stats["store"]) if stats.get("store") else None,
            "orders": [deps["decorate_order_for_view"](order) for order in deps["get_merchant_orders"](username)[:8]],
            "notifications": deps["get_notifications_for_user"](username, limit=8),
            "pending_applications": deps["get_store_applications_for_owner"](username, status="pending"),
        }

    return {
        "role": "admin",
        "stats": deps["get_admin_stats"](),
        "top_boosters": deps["get_top_boosters"](limit=6),
        "complaints": [deps["decorate_order_for_view"](order) for order in deps["recent_complaints"](limit=6)],
        "orders": [deps["decorate_order_for_view"](order) for order in deps["get_all_orders"]()[:8]],
    }


def build_orders_snapshot(user, deps):
    username = user["username"]
    role = user["role"]
    if role == "player":
        orders = deps["get_orders_for_player"](username)
    elif role == "booster":
        orders = deps["get_orders_for_booster"](username)
    elif role == "merchant":
        orders = deps["get_merchant_orders"](username)
    else:
        orders = deps["get_all_orders"]()

    return {
        "role": role,
        "orders": [deps["decorate_order_for_view"](order) for order in orders],
    }


def build_wallet_snapshot(user, deps):
    return {
        "role": user["role"],
        "wallet": deps["get_wallet_snapshot"](user),
        "transactions": deps["get_wallet_transactions"](user["username"], limit=80),
        "coin_to_cash_rate": deps["BUDDY_COIN_TO_CASH_RATE"],
        "withdraw_rate": deps["WITHDRAW_CASH_PER_COIN"],
        "share_rate": deps["BOOSTER_REVENUE_SHARE"],
    }


def build_chat_list_snapshot(user, deps):
    username = user["username"]
    return {
        "role": user["role"],
        "conversations": deps["conversation_summaries"](username, user["role"]),
        "notifications": deps["get_notifications_for_user"](username, limit=8),
    }


def build_chat_thread_snapshot(user, partner_user, deps):
    username = user["username"]
    return {
        "role": user["role"],
        "partner": partner_user,
        "messages": deps["get_messages_between"](username, partner_user["username"]),
        "notifications": deps["get_notifications_for_user"](username, limit=6),
    }


def build_admin_users_snapshot(deps):
    stores = deps["get_all_stores"]()
    booster_applications = deps["get_booster_applications"]()
    merchant_applications = deps["get_merchant_applications"]()
    return {
        "users": deps["all_users"](),
        "pending_store_applications": [
            deps["build_store_card"](store)
            for store in stores
            if (store.get("approval_status") or "pending") == "pending"
        ],
        "reviewed_store_applications": [
            deps["build_store_card"](store)
            for store in stores
            if (store.get("approval_status") or "pending") != "pending"
        ][:10],
        "pending_booster_applications": [item for item in booster_applications if item["status"] == "pending"],
        "reviewed_booster_applications": [item for item in booster_applications if item["status"] != "pending"][:10],
        "pending_merchant_applications": [item for item in merchant_applications if item["status"] == "pending"],
        "reviewed_merchant_applications": [item for item in merchant_applications if item["status"] != "pending"][:10],
    }


def build_admin_orders_snapshot(filters, deps):
    keyword = ((filters or {}).get("keyword") or "").strip().lower()
    status_filter = ((filters or {}).get("status") or "").strip()
    complaint_filter = ((filters or {}).get("complaint") or "").strip()

    orders = deps["get_all_orders"]()
    if keyword:
        orders = [
            order
            for order in orders
            if keyword in order.get("player", "").lower()
            or keyword in order.get("booster", "").lower()
            or keyword in order.get("game", "").lower()
        ]
    if status_filter:
        orders = [order for order in orders if order.get("status") == status_filter]
    if complaint_filter:
        orders = [order for order in orders if order.get("complaint_status") == complaint_filter]

    return {
        "filters": {
            "keyword": (filters or {}).get("keyword", ""),
            "status": status_filter,
            "complaint": complaint_filter,
        },
        "orders": [deps["decorate_order_for_view"](order) for order in orders],
        "order_status_options": list(deps["ORDER_STATUS_OPTIONS"]),
        "complaint_status_options": list(deps["COMPLAINT_STATUS_OPTIONS"]),
    }
