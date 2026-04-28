from __future__ import annotations


def serialize_notification(notification):
    return {
        "id": notification.get("id"),
        "sender": notification.get("sender", ""),
        "message": notification.get("message", ""),
        "timestamp": notification.get("timestamp", ""),
        "type": notification.get("type", ""),
    }


def serialize_booster_card(booster):
    if not booster:
        return None
    profile = booster.get("profile", {})
    stats = booster.get("stats", {})
    return {
        "username": booster.get("username", ""),
        "displayName": booster.get("display_name", ""),
        "storeTitle": booster.get("store_title", ""),
        "avatarText": booster.get("avatar_text", ""),
        "priceValue": booster.get("price_value", 0),
        "profile": {
            "games": profile.get("games", ""),
            "rank": profile.get("rank", ""),
            "price": profile.get("price", ""),
            "availableTime": profile.get("available_time", ""),
            "playStyle": profile.get("play_style", ""),
            "intro": profile.get("intro", ""),
            "storeName": profile.get("store_name", ""),
            "storeSlug": profile.get("store_slug", ""),
            "badge": profile.get("badge", ""),
            "responseTime": profile.get("response_time", ""),
            "statusText": profile.get("status_text", ""),
            "coverTheme": profile.get("cover_theme", ""),
            "personaTags": list(profile.get("persona_tags", [])),
            "avatarUrl": profile.get("avatar_url", ""),
            "coverUrl": profile.get("cover_url", ""),
        },
        "stats": {
            "totalOrders": stats.get("total_orders", 0),
            "completedOrders": stats.get("completed_orders", 0),
            "activeOrders": stats.get("active_orders", 0),
            "avgRating": stats.get("avg_rating"),
            "completionRate": stats.get("completion_rate", 0),
            "recommendationScore": stats.get("recommendation_score", 0),
        },
    }


def serialize_store_card(store):
    if not store:
        return None
    return {
        "id": store.get("id"),
        "slug": store.get("slug", ""),
        "name": store.get("name", ""),
        "tagline": store.get("tagline", ""),
        "description": store.get("description", ""),
        "games": list(store.get("games", [])),
        "gamesText": store.get("games_text", ""),
        "city": store.get("city", ""),
        "minPrice": store.get("min_price", ""),
        "minPriceValue": store.get("min_price_value", 0),
        "priceText": store.get("price_text", ""),
        "theme": store.get("theme", ""),
        "badge": store.get("badge", ""),
        "contactNote": store.get("contact_note", ""),
        "heroText": store.get("hero_text", ""),
        "logoText": store.get("logo_text", ""),
        "logoUrl": store.get("logo_url", ""),
        "coverUrl": store.get("cover_url", ""),
        "boosterCount": store.get("booster_count", 0),
        "avgRating": store.get("avg_rating"),
        "completedOrders": store.get("completed_orders", 0),
        "activeOrders": store.get("active_orders", 0),
        "ownerDisplayName": store.get("owner_display_name", ""),
        "reviewLabel": store.get("review_label", ""),
        "reviewBadge": store.get("review_badge", ""),
        "isPublic": bool(store.get("is_public", False)),
        "pendingTalentCount": store.get("pending_talent_count", 0),
        "boosters": [serialize_booster_card(booster) for booster in store.get("boosters", [])],
    }


def serialize_order(order):
    if not order:
        return None
    return {
        "id": order.get("id"),
        "player": order.get("player", ""),
        "booster": order.get("booster", ""),
        "assignedBooster": order.get("assigned_booster", ""),
        "assignedBoosterName": order.get("assigned_booster_name", ""),
        "game": order.get("game", ""),
        "detail": order.get("detail", ""),
        "status": order.get("status", ""),
        "price": order.get("price", ""),
        "rating": order.get("rating", ""),
        "comment": order.get("comment", ""),
        "complaint": order.get("complaint", ""),
        "complaintStatus": order.get("complaint_status", ""),
        "complaintReply": order.get("complaint_reply", ""),
        "adminNote": order.get("admin_note", ""),
        "serviceType": order.get("service_type", ""),
        "targetRank": order.get("target_rank", ""),
        "duration": order.get("duration", ""),
        "preferredTime": order.get("preferred_time", ""),
        "paymentStatus": order.get("payment_status", ""),
        "createdAt": order.get("created_at", ""),
        "storeLabel": order.get("store_label", order.get("store_name", "")),
        "boosterLabel": order.get("booster_label", ""),
        "store": serialize_store_card(order.get("store")),
        "assignedBoosterCard": serialize_booster_card(order.get("assigned_booster_card")),
    }


def serialize_user(user, deps):
    if not user:
        return None
    profile = user.get("profile", {})
    wallet = deps["get_wallet_snapshot"](user)
    return {
        "username": user.get("username", ""),
        "role": user.get("role", ""),
        "roleLabel": deps["ROLE_LABELS"].get(user.get("role", ""), user.get("role", "")),
        "displayName": profile.get("display_name") or user.get("username", ""),
        "email": user.get("email", ""),
        "phone": user.get("phone", ""),
        "dashboardPath": deps["service_dashboard_path"](user.get("role", "")),
        "wallet": {
            "balance": wallet.get("balance", 0),
            "locked": wallet.get("locked", 0),
            "available": wallet.get("available", 0),
        },
    }


def serialize_dashboard(snapshot, deps):
    role = snapshot.get("role", "")
    payload = {
        "role": role,
        "stats": snapshot.get("stats", {}),
    }

    if role == "player":
        payload["orders"] = [serialize_order(order) for order in snapshot.get("orders", [])]
        payload["recommendedStores"] = [serialize_store_card(store) for store in snapshot.get("recommended_stores", [])]
        payload["notifications"] = [serialize_notification(item) for item in snapshot.get("notifications", [])]
        return payload

    if role == "booster":
        payload["orders"] = [serialize_order(order) for order in snapshot.get("orders", [])]
        payload["notifications"] = [serialize_notification(item) for item in snapshot.get("notifications", [])]
        payload["profileCompletion"] = snapshot.get("profile_completion", 0)
        payload["store"] = serialize_store_card(snapshot.get("store"))
        return payload

    if role == "merchant":
        payload["orders"] = [serialize_order(order) for order in snapshot.get("orders", [])]
        payload["notifications"] = [serialize_notification(item) for item in snapshot.get("notifications", [])]
        payload["store"] = serialize_store_card(snapshot.get("store"))
        payload["pendingApplications"] = [
            {
                "id": item.get("id"),
                "username": item.get("username", ""),
                "displayName": item.get("display_name", "") or item.get("username", ""),
                "gameAccount": item.get("game_account", ""),
                "createdAt": item.get("created_at", ""),
            }
            for item in snapshot.get("pending_applications", [])
        ]
        return payload

    payload["orders"] = [serialize_order(order) for order in snapshot.get("orders", [])]
    payload["topBoosters"] = [serialize_booster_card(item) for item in snapshot.get("top_boosters", [])]
    payload["complaints"] = [serialize_order(order) for order in snapshot.get("complaints", [])]
    return payload


def serialize_discovery(snapshot):
    return {
        "filters": snapshot.get("filters", {}),
        "stores": [serialize_store_card(store) for store in snapshot.get("stores", [])],
        "featured": [serialize_store_card(store) for store in snapshot.get("featured", [])],
    }


def serialize_store_detail(store, deps):
    return {
        "store": serialize_store_card(store),
        "serviceTypeOptions": list(deps["SERVICE_TYPE_OPTIONS"]),
    }


def serialize_orders(snapshot):
    return {
        "role": snapshot.get("role", ""),
        "orders": [serialize_order(order) for order in snapshot.get("orders", [])],
    }


def serialize_wallet_transaction(transaction):
    return {
        "id": transaction.get("id"),
        "type": transaction.get("tx_type", ""),
        "coinAmount": transaction.get("coin_amount", 0),
        "cashAmount": transaction.get("cash_amount", 0),
        "relatedOrderId": transaction.get("related_order_id", 0),
        "status": transaction.get("status", ""),
        "note": transaction.get("note", ""),
        "createdAt": transaction.get("created_at", ""),
    }


def serialize_wallet(snapshot):
    wallet = snapshot.get("wallet", {})
    return {
        "role": snapshot.get("role", ""),
        "wallet": {
            "balance": wallet.get("balance", 0),
            "locked": wallet.get("locked", 0),
            "available": wallet.get("available", 0),
        },
        "transactions": [serialize_wallet_transaction(item) for item in snapshot.get("transactions", [])],
        "coinToCashRate": snapshot.get("coin_to_cash_rate", 0),
        "withdrawRate": snapshot.get("withdraw_rate", 0),
        "shareRate": snapshot.get("share_rate", 0),
    }


def serialize_chat_summary(summary):
    return {
        "partner": summary.get("partner", ""),
        "partnerLabel": summary.get("partner_label", ""),
        "partnerStoreSlug": summary.get("partner_store_slug", ""),
        "lastMessage": summary.get("last_message", ""),
        "timestamp": summary.get("timestamp", ""),
    }


def serialize_chat_message(message):
    return {
        "id": message.get("id"),
        "sender": message.get("sender", ""),
        "receiver": message.get("receiver", ""),
        "message": message.get("message", ""),
        "timestamp": message.get("timestamp", ""),
        "type": message.get("type", ""),
    }


def serialize_chat_partner(user, deps):
    if not user:
        return None
    profile = user.get("profile", {})
    return {
        "username": user.get("username", ""),
        "role": user.get("role", ""),
        "roleLabel": deps["ROLE_LABELS"].get(user.get("role", ""), user.get("role", "")),
        "displayName": profile.get("display_name") or user.get("username", ""),
    }


def serialize_chat_thread(snapshot, deps):
    partner = snapshot.get("partner")
    return {
        "role": snapshot.get("role", ""),
        "partner": serialize_chat_partner(partner, deps),
        "messages": [serialize_chat_message(item) for item in snapshot.get("messages", [])],
        "notifications": [serialize_notification(item) for item in snapshot.get("notifications", [])],
    }


def serialize_chats(snapshot, deps):
    return {
        "role": snapshot.get("role", ""),
        "conversations": [serialize_chat_summary(item) for item in snapshot.get("conversations", [])],
        "notifications": [serialize_notification(item) for item in snapshot.get("notifications", [])],
        "session": serialize_user(snapshot.get("session"), deps) if snapshot.get("session") else None,
    }


def serialize_admin_user(user, deps):
    payload = serialize_user(user, deps) or {}
    payload.update(
        {
            "banned": bool(user.get("banned")),
            "failedLoginAttempts": user.get("failed_login_attempts", 0),
            "lockReason": user.get("lock_reason", ""),
        }
    )
    return payload


def serialize_booster_application(application):
    return {
        "id": application.get("id"),
        "username": application.get("username", ""),
        "displayName": application.get("display_name") or application.get("username", ""),
        "email": application.get("email", ""),
        "phone": application.get("phone", ""),
        "gameAccount": application.get("game_account", ""),
        "storeId": application.get("store_id", ""),
        "storeOwnerUsername": application.get("store_owner_username", ""),
        "storeName": application.get("store_name", ""),
        "proofImageUrl": application.get("proof_image_url", ""),
        "status": application.get("status", ""),
        "reviewNote": application.get("review_note", ""),
        "createdAt": application.get("created_at", ""),
        "reviewedAt": application.get("reviewed_at", ""),
    }


def serialize_merchant_application(application):
    return {
        "id": application.get("id"),
        "username": application.get("username", ""),
        "email": application.get("email", ""),
        "phone": application.get("phone", ""),
        "storeName": application.get("store_name", ""),
        "storeCity": application.get("store_city", ""),
        "businessLicenseUrl": application.get("business_license_url", ""),
        "idProofUrl": application.get("id_proof_url", ""),
        "status": application.get("status", ""),
        "reviewNote": application.get("review_note", ""),
        "createdAt": application.get("created_at", ""),
        "reviewedAt": application.get("reviewed_at", ""),
    }


def serialize_admin_users(snapshot, deps):
    return {
        "users": [serialize_admin_user(user, deps) for user in snapshot.get("users", [])],
        "pendingStoreApplications": [serialize_store_card(item) for item in snapshot.get("pending_store_applications", [])],
        "reviewedStoreApplications": [serialize_store_card(item) for item in snapshot.get("reviewed_store_applications", [])],
        "pendingBoosterApplications": [serialize_booster_application(item) for item in snapshot.get("pending_booster_applications", [])],
        "reviewedBoosterApplications": [serialize_booster_application(item) for item in snapshot.get("reviewed_booster_applications", [])],
        "pendingMerchantApplications": [serialize_merchant_application(item) for item in snapshot.get("pending_merchant_applications", [])],
        "reviewedMerchantApplications": [serialize_merchant_application(item) for item in snapshot.get("reviewed_merchant_applications", [])],
    }


def serialize_admin_orders(snapshot):
    return {
        "filters": snapshot.get("filters", {}),
        "orders": [serialize_order(order) for order in snapshot.get("orders", [])],
        "orderStatusOptions": list(snapshot.get("order_status_options", [])),
        "complaintStatusOptions": list(snapshot.get("complaint_status_options", [])),
    }
