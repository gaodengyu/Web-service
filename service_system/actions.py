from __future__ import annotations


class ServiceActionError(Exception):
    def __init__(self, message, *, status=400, code="bad_request"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def _require_pending(item, label):
    if not item:
        raise ServiceActionError(f"{label}不存在。", status=404, code="not_found")
    if item.get("status") != "pending":
        raise ServiceActionError(f"这条{label}已经处理过了。", status=409, code="already_reviewed")


def review_store_application(store_id, action, review_note, actor_username, deps):
    store = deps["get_store"](store_id)
    if not store:
        raise ServiceActionError("店铺不存在。", status=404, code="store_not_found")

    fields = {
        "approval_status": "approved" if action == "approve_store" else "rejected",
        "review_note": review_note or ("资料合规，允许上架。" if action == "approve_store" else "资料需补充，请修改后重新提交。"),
        "reviewed_at": deps["now_text"](),
        "reviewed_by": actor_username,
        "updated_at": deps["now_text"](),
    }
    deps["update_store"](store_id, fields)
    updated_store = deps["get_store"](store_id)
    deps["notify_user"](
        updated_store["owner_username"],
        f"店铺 {updated_store['name']} 的审核结果：{deps['store_review_label'](updated_store)}。{fields['review_note']}",
        sender=actor_username,
    )
    return {
        "message": "店铺审核结果已保存。",
        "store": deps["build_store_card"](updated_store),
    }


def review_booster_application(application_id, action, review_note, actor_username, deps):
    application = deps["get_booster_application"](application_id)
    _require_pending(application, "陪玩师申请")

    has_store_binding = bool(application.get("store_id") or application.get("store_owner_username"))
    store = deps["get_store"](application["store_id"]) if application.get("store_id") else None
    if has_store_binding and not store and application.get("store_owner_username"):
        store = deps["get_store_by_owner"](application["store_owner_username"])
    if has_store_binding and not store:
        raise ServiceActionError("该申请没有有效的归属店铺，暂时不能处理。", status=400, code="missing_store")
    if has_store_binding and action == "approve_booster_application" and not deps["store_is_approved"](store):
        raise ServiceActionError("请先完成店铺合规审核，再审核店内陪玩师。", status=409, code="store_pending_review")

    if action == "approve_booster_application":
        if deps["get_user"](application["username"]):
            raise ServiceActionError("该用户名已被占用，无法通过审核。", status=409, code="username_taken")

        existing_email_owner = (
            deps["find_user_by_email"](application["email"])
            if application.get("email") and not application["email"].endswith("@pending.local")
            else None
        )
        if existing_email_owner and existing_email_owner["username"] != application["username"]:
            raise ServiceActionError("该邮箱已绑定其他账号，无法通过审核。", status=409, code="email_taken")

        existing_phone_owner = deps["get_user_by_phone"](application["phone"]) if application.get("phone") else None
        if existing_phone_owner and existing_phone_owner["username"] != application["username"]:
            raise ServiceActionError("该手机号已绑定其他账号，无法通过审核。", status=409, code="phone_taken")

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
                "reviewed_by": actor_username,
            },
        )
        deps["notify_user"](
            application["username"],
            f"你的陪玩师申请已通过平台审核{'，现已归属 ' + store['name'] if has_store_binding else ''}并开通账号。",
            sender=actor_username,
        )
        if has_store_binding:
            deps["notify_user"](store["owner_username"], f"店内陪玩师 {profile['display_name']} 已通过平台审核。", sender=actor_username)
        try:
            if application.get("email") and not application["email"].endswith("@pending.local"):
                deps["send_booster_application_review_email"](application, True, approval_note)
        except Exception:
            pass
        return {"message": "陪玩师申请已审核通过，账号已创建。"}

    rejection_note = review_note or "资料不完整或需补充说明，请修改后重新提交。"
    deps["update_booster_application"](
        application_id,
        {
            "status": "rejected",
            "review_note": rejection_note,
            "reviewed_at": deps["now_text"](),
            "reviewed_by": actor_username,
        },
    )
    if has_store_binding:
        deps["notify_user"](
            store["owner_username"],
            f"店内陪玩师申请 {application.get('display_name') or application['username']} 未通过审核：{rejection_note}",
            sender=actor_username,
        )
    try:
        if application.get("email") and not application["email"].endswith("@pending.local"):
            deps["send_booster_application_review_email"](application, False, rejection_note)
    except Exception:
        pass
    return {"message": "陪玩师申请已驳回。"}


def review_merchant_application(application_id, action, review_note, actor_username, deps):
    application = deps["get_merchant_application"](application_id)
    _require_pending(application, "商家申请")

    if action == "approve_merchant_application":
        if deps["get_user"](application["username"]):
            raise ServiceActionError("该用户名已被占用，无法通过审核。", status=409, code="username_taken")

        existing_email_owner = deps["find_user_by_email"](application["email"]) if application.get("email") else None
        if existing_email_owner and existing_email_owner["username"] != application["username"]:
            raise ServiceActionError("该邮箱已绑定其他账号，无法通过审核。", status=409, code="email_taken")

        existing_phone_owner = deps["get_user_by_phone"](application["phone"]) if application.get("phone") else None
        if existing_phone_owner and existing_phone_owner["username"] != application["username"]:
            raise ServiceActionError("该手机号已绑定其他账号，无法通过审核。", status=409, code="phone_taken")

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
                "reviewed_by": actor_username,
            },
        )
        try:
            deps["send_merchant_application_review_email"](application, True, approval_note)
        except Exception:
            pass
        return {"message": "商家申请已审核通过，账号已创建。"}

    rejection_note = review_note or "资质资料不完整或不清晰，请补充后重试。"
    deps["update_merchant_application"](
        application_id,
        {
            "status": "rejected",
            "review_note": rejection_note,
            "reviewed_at": deps["now_text"](),
            "reviewed_by": actor_username,
        },
    )
    try:
        deps["send_merchant_application_review_email"](application, False, rejection_note)
    except Exception:
        pass
    return {"message": "商家申请已驳回。"}


def apply_admin_user_action(username, action, actor_username, deps, *, new_password=""):
    user = deps["get_user"](username)
    if not user or user["username"] == deps["SYSTEM_USERNAME"]:
        raise ServiceActionError("目标账号不存在。", status=404, code="user_not_found")
    if user["role"] == "admin":
        raise ServiceActionError("不能对管理员账号执行这个操作。", status=403, code="protected_admin")

    if action == "ban":
        deps["update_user"](username, {"banned": True})
        deps["notify_user"](username, "你的账号已被管理员封禁，如有疑问请联系客服。", sender=actor_username)
        return {"message": "账号已封禁。"}

    if action == "unban":
        deps["clear_failed_login_attempts"](username, unlock_account=True)
        deps["notify_user"](username, "你的账号已被管理员解封，可以重新登录。", sender=actor_username)
        return {"message": "账号已解封，失败登录次数已清零。"}

    if action == "reset_password":
        if not new_password:
            raise ServiceActionError("请输入新密码。", status=400, code="missing_password")
        password_error = deps["validate_password_policy"](new_password)
        if password_error:
            raise ServiceActionError(password_error, status=400, code="invalid_password")
        deps["clear_failed_login_attempts"](username, unlock_account=True)
        deps["update_user"](username, {"password": new_password})
        deps["notify_user"](username, "管理员已为你重置密码，请尽快重新登录并修改。", sender=actor_username)
        return {"message": "密码已重置，账号已解封。"}

    if action == "delete":
        deps["delete_user"](username)
        return {"message": "账号已删除。"}

    raise ServiceActionError("不支持的操作。", status=400, code="unsupported_action")


def update_admin_order(order_id, action, complaint_status, complaint_reply, admin_note, actor_username, deps):
    order = deps["get_order"](order_id)
    if not order:
        raise ServiceActionError("订单不存在。", status=404, code="order_not_found")

    if action == "handle_complaint":
        fields = {
            "complaint_status": complaint_status,
            "complaint_reply": complaint_reply,
            "admin_note": admin_note,
        }
        if complaint_status == "已退款":
            refund_ok, refund_message = deps["refund_order_buddy_coin"](
                order,
                reason="管理员投诉处理退款",
                operator_username=actor_username,
            )
            if not refund_ok:
                raise ServiceActionError(refund_message or "退款失败，请检查店铺余额。", status=400, code="refund_failed")
            fields["status"] = "已退款"
            fields["payment_status"] = "巴迪币已退款"
        deps["update_order"](order_id, fields)
        updated_order = deps["get_order"](order_id)
        deps["notify_merchant_for_order"](updated_order, f"订单 #{order_id} 的投诉状态已更新为“{complaint_status}”。", sender=actor_username)
        deps["notify_user"](
            updated_order["player"],
            f"订单 #{order_id} 的投诉状态已更新为“{complaint_status}”。{complaint_reply}",
            sender=actor_username,
        )
        deps["notify_user"](
            updated_order["booster"],
            f"订单 #{order_id} 的投诉状态已更新为“{complaint_status}”。{complaint_reply}",
            sender=actor_username,
        )
        return {"message": "投诉处理结果已更新。", "order": updated_order}

    if action == "mark_refunded":
        refund_ok, refund_message = deps["refund_order_buddy_coin"](
            order,
            reason="管理员手动标记退款",
            operator_username=actor_username,
        )
        if not refund_ok:
            raise ServiceActionError(refund_message or "退款失败，请检查店铺余额。", status=400, code="refund_failed")
        deps["update_order"](order_id, {"status": "已退款", "payment_status": "巴迪币已退款", "complaint_status": "已退款"})
        updated_order = deps["get_order"](order_id)
        deps["notify_merchant_for_order"](updated_order, f"店内订单 #{order_id} 已被管理员标记为退款。", sender=actor_username)
        deps["notify_user"](updated_order["player"], f"订单 #{order_id} 已由管理员标记为退款。", sender=actor_username)
        deps["notify_user"](updated_order["booster"], f"订单 #{order_id} 已由管理员标记为退款。", sender=actor_username)
        return {"message": "订单已标记退款。", "order": updated_order}

    raise ServiceActionError("不支持的投诉处理动作。", status=400, code="unsupported_action")
