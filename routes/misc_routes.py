def logout_view(deps):
    deps["session"].clear()
    deps["flash"]("你已退出登录。", "info")
    return deps["redirect"](deps["url_for"]("home"))


def admin_home_view(deps):
    stats = deps["get_admin_stats"]()
    top_boosters = deps["get_top_boosters"](limit=5)
    complaints = deps["recent_complaints"](limit=5)
    recent_orders = deps["get_all_orders"]()[:6]
    return deps["render_template"](
        "admin_dashboard.html",
        stats=stats,
        top_boosters=top_boosters,
        complaints=complaints,
        recent_orders=recent_orders,
    )


def admin_orders_view(deps):
    if deps["request"].method == "POST":
        order_id = deps["safe_int"](deps["request"].form.get("order_id"), default=-1)
        action = deps["request"].form.get("action", "").strip()
        order = deps["get_order"](order_id)
        if not order:
            deps["flash"]("订单不存在。", "warning")
            return deps["redirect"](deps["url_for"]("admin_orders"))

        if action == "handle_complaint":
            complaint_status = deps["request"].form.get("complaint_status", "处理中").strip()
            complaint_reply = deps["request"].form.get("complaint_reply", "").strip()
            admin_note = deps["request"].form.get("admin_note", "").strip()
            fields = {
                "complaint_status": complaint_status,
                "complaint_reply": complaint_reply,
                "admin_note": admin_note,
            }
            if complaint_status == "已退款":
                refund_ok, refund_message = deps["refund_order_buddy_coin"](
                    order,
                    reason="管理员投诉处理退款",
                    operator_username=deps["session"]["username"],
                )
                if not refund_ok:
                    deps["flash"](refund_message or "退款失败，请检查店铺余额。", "warning")
                    return deps["redirect"](deps["url_for"]("admin_orders"))
                fields["status"] = "已退款"
                fields["payment_status"] = "巴迪币已退款"
            deps["update_order"](order_id, fields)
            deps["notify_merchant_for_order"](order, f"订单 #{order_id} 的投诉状态已更新为“{complaint_status}”。", sender=deps["session"]["username"])
            deps["notify_user"](
                order["player"],
                f"订单 #{order_id} 的投诉状态已更新为“{complaint_status}”。{complaint_reply}",
                sender=deps["session"]["username"],
            )
            deps["notify_user"](
                order["booster"],
                f"订单 #{order_id} 的投诉状态已更新为“{complaint_status}”。{complaint_reply}",
                sender=deps["session"]["username"],
            )
            deps["flash"]("投诉处理结果已更新。", "success")

        elif action == "mark_refunded":
            refund_ok, refund_message = deps["refund_order_buddy_coin"](
                order,
                reason="管理员手动标记退款",
                operator_username=deps["session"]["username"],
            )
            if not refund_ok:
                deps["flash"](refund_message or "退款失败，请检查店铺余额。", "warning")
                return deps["redirect"](deps["url_for"]("admin_orders"))
            deps["update_order"](order_id, {"status": "已退款", "payment_status": "巴迪币已退款", "complaint_status": "已退款"})
            deps["notify_merchant_for_order"](order, f"店内订单 #{order_id} 已被管理员标记为退款。", sender=deps["session"]["username"])
            deps["notify_user"](order["player"], f"订单 #{order_id} 已由管理员标记为退款。", sender=deps["session"]["username"])
            deps["notify_user"](order["booster"], f"订单 #{order_id} 已由管理员标记为退款。", sender=deps["session"]["username"])
            deps["flash"]("订单已标记退款。", "success")

        return deps["redirect"](deps["url_for"]("admin_orders"))

    keyword = deps["request"].args.get("keyword", "").strip().lower()
    status_filter = deps["request"].args.get("status", "").strip()
    complaint_filter = deps["request"].args.get("complaint", "").strip()

    orders = deps["get_all_orders"]()
    if keyword:
        orders = [
            order
            for order in orders
            if keyword in order["player"].lower()
            or keyword in order["booster"].lower()
            or keyword in order["game"].lower()
        ]
    if status_filter:
        orders = [order for order in orders if order["status"] == status_filter]
    if complaint_filter:
        orders = [order for order in orders if order["complaint_status"] == complaint_filter]

    filters = {"keyword": deps["request"].args.get("keyword", ""), "status": status_filter, "complaint": complaint_filter}
    return deps["render_template"](
        "admin_orders.html",
        orders=orders,
        filters=filters,
        order_status_options=deps["ORDER_STATUS_OPTIONS"],
        complaint_status_options=deps["COMPLAINT_STATUS_OPTIONS"],
    )


def admin_send_notification_view(deps):
    if deps["request"].method == "POST":
        receiver = deps["request"].form.get("receiver", "").strip()
        message = deps["request"].form.get("message", "").strip()
        if not receiver or not message:
            deps["flash"]("接收者和消息内容不能为空。", "warning")
            return deps["redirect"](deps["url_for"]("admin_send_notification"))
        if not deps["get_user"](receiver):
            deps["flash"]("接收者不存在。", "warning")
            return deps["redirect"](deps["url_for"]("admin_send_notification"))
        deps["notify_user"](receiver, message, sender=deps["session"]["username"])
        deps["flash"]("通知已发送。", "success")
        return deps["redirect"](deps["url_for"]("admin_send_notification"))
    users = deps["all_users"]()
    return deps["render_template"]("admin_send_notification.html", users=users)


def player_chats_view(deps):
    username = deps["session"]["username"]
    chats = deps["conversation_summaries"](username, "player")
    notifications = deps["get_notifications_for_user"](username, limit=8)
    return deps["render_template"]("player_chats.html", chats=chats, notifications=notifications)


def booster_chats_view(deps):
    username = deps["session"]["username"]
    chats = deps["conversation_summaries"](username, "booster")
    notifications = deps["get_notifications_for_user"](username, limit=8)
    return deps["render_template"]("booster_chats.html", chats=chats, notifications=notifications)


def merchant_chats_view(deps):
    username = deps["session"]["username"]
    chats = deps["conversation_summaries"](username, "merchant")
    notifications = deps["get_notifications_for_user"](username, limit=8)
    return deps["render_template"]("merchant_chats.html", chats=chats, notifications=notifications)


def chat_view(deps, partner):
    username = deps["session"]["username"]
    role = deps["session"]["role"]
    current_user = deps["get_user"](username)
    partner_user = deps["get_user"](partner)
    if not partner_user:
        deps["flash"]("用户不存在。", "warning")
        return deps["redirect_to_dashboard"]()
    if not deps["can_users_chat"](current_user, partner_user):
        deps["flash"]("只有建立订单关系或联系店铺后才能聊天。", "warning")
        return deps["redirect_to_dashboard"]()

    messages = deps["get_messages_between"](username, partner)
    notifications = deps["get_notifications_for_user"](username, limit=6)
    chats = deps["conversation_summaries"](username, role)
    return deps["render_template"](
        "chat.html",
        partner=partner,
        partner_label=deps["chat_partner_label"](partner_user),
        partner_store_slug=deps["chat_partner_store_slug"](partner_user) if role == "player" else "",
        messages=messages,
        notifications=notifications,
        chats=chats,
        chats_endpoint=deps["message_center_endpoint_for_role"](role),
    )


def send_message_view(deps):
    sender = deps["session"]["username"]
    receiver = deps["request"].form.get("receiver", "").strip()
    message = deps["request"].form.get("message", "").strip()
    sender_user = deps["get_user"](sender)
    receiver_user = deps["get_user"](receiver)
    if not receiver_user:
        deps["flash"]("接收者不存在。", "warning")
        return deps["redirect_to_dashboard"]()
    if not message:
        deps["flash"]("消息不能为空。", "warning")
        return deps["redirect"](deps["url_for"]("chat", partner=receiver))
    if not deps["can_users_chat"](sender_user, receiver_user):
        deps["flash"]("你们之间还没有可聊天的关系。", "warning")
        return deps["redirect_to_dashboard"]()

    timestamp = deps["add_message"](sender, receiver, message, "chat")
    deps["emit_chat_message"](sender, receiver, message, timestamp)
    return deps["redirect"](deps["url_for"]("chat", partner=receiver))


def merchant_application_status_view(deps):
    form_state = {
        "username": deps["request"].form.get("username", "").strip() if deps["request"].method == "POST" else deps["request"].args.get("username", "").strip(),
        "password": deps["request"].form.get("password", "").strip() if deps["request"].method == "POST" else "",
        "email": deps["normalize_email"](deps["request"].form.get("email", "")) if deps["request"].method == "POST" else deps["normalize_email"](deps["request"].args.get("email", "")),
    }
    application = None
    application_role = ""

    query_role = deps["request"].args.get("application_role", "").strip()
    query_application_id = deps["safe_int"](deps["request"].args.get("application_id"), default=0)
    if query_role in {"merchant", "booster"} and query_application_id > 0:
        if query_role == "merchant":
            application = deps["get_merchant_application"](query_application_id)
        else:
            application = deps["get_booster_application"](query_application_id)
        if application:
            application_role = query_role
            form_state["username"] = form_state["username"] or application.get("username", "")

    if deps["request"].method == "POST":
        if not form_state["username"]:
            deps["flash"]("请输入注册时使用的用户名/ID。", "warning")
        else:
            lookup = deps["find_application_for_status_lookup"](form_state["username"], form_state["password"])
            if lookup:
                application = lookup["application"]
                application_role = lookup["role"]
                if application.get("status") == "rejected":
                    deps["flash"]("审核失败账号已注销。", "danger")
            elif form_state["email"]:
                application = deps["find_latest_merchant_application"](form_state["username"], form_state["email"])
                application_role = "merchant" if application else ""
                if not application:
                    deps["flash"]("未找到匹配申请，请确认信息后重试。", "warning")
            else:
                deps["flash"]("请输入用户名/ID 与密码，或使用用户名与邮箱查询。", "warning")
    elif form_state["username"] and form_state["email"] and not application:
        application = deps["find_latest_merchant_application"](form_state["username"], form_state["email"])
        application_role = "merchant" if application else ""

    return deps["render_template"](
        "merchant_application_status.html",
        application=application,
        application_role=application_role,
        form_state=form_state,
    )
