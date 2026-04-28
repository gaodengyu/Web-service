import sys

from flask import flash, redirect, render_template, request, session, url_for


def admin_users_view(
    *,
    safe_int,
    get_booster_application,
    get_user,
    find_user_by_email,
    get_user_by_phone,
    add_user,
    update_booster_application,
    now_text,
    notify_user,
    send_booster_application_review_email,
    clear_failed_login_attempts,
    update_user,
    validate_password_policy,
    delete_user,
    all_users,
    get_booster_applications,
    system_username,
):
    if request.method == "POST":
        action = request.form.get("action", "").strip()

        if action in {"approve_booster_application", "reject_booster_application"}:
            application_id = safe_int(request.form.get("application_id"), default=-1)
            review_note = request.form.get("review_note", "").strip()
            application = get_booster_application(application_id)

            if not application:
                flash("打手申请不存在。", "warning")
                return redirect(url_for("admin_users"))
            if application["status"] != "pending":
                flash("这条申请已经处理过了。", "warning")
                return redirect(url_for("admin_users"))
            if application.get("store_id") or application.get("store_owner_username"):
                flash("店铺侧入驻申请应由店铺自行审核，无需平台复核。", "warning")
                return redirect(url_for("admin_users"))

            if action == "approve_booster_application":
                if get_user(application["username"]):
                    flash("该用户名已被占用，无法通过审核。", "warning")
                    return redirect(url_for("admin_users"))

                existing_email_owner = find_user_by_email(application["email"]) if application.get("email") else None
                if existing_email_owner and existing_email_owner["username"] != application["username"]:
                    flash("该邮箱已绑定其他账号，无法通过审核。", "warning")
                    return redirect(url_for("admin_users"))

                existing_phone_owner = get_user_by_phone(application["phone"]) if application.get("phone") else None
                if existing_phone_owner and existing_phone_owner["username"] != application["username"]:
                    flash("该手机号已绑定其他账号，无法通过审核。", "warning")
                    return redirect(url_for("admin_users"))

                approval_note = review_note or "资料完整，审核通过。"
                profile = {
                    "display_name": application["username"],
                    "email": application["email"],
                    "game_account": application["game_account"],
                    "proof_image_path": application["proof_image_path"],
                    "approval_status": "approved",
                    "approval_review_note": approval_note,
                    "auth_provider": application.get("auth_provider", "local"),
                }
                add_user(
                    application["username"],
                    application["password"],
                    "booster",
                    profile=profile,
                    email=application["email"],
                    phone=application.get("phone", ""),
                    auth_provider=application.get("auth_provider", "local"),
                    social_id=application.get("social_id", ""),
                )
                update_booster_application(
                    application_id,
                    {
                        "status": "approved",
                        "review_note": approval_note,
                        "reviewed_at": now_text(),
                        "reviewed_by": session.get("username", "admin"),
                    },
                )
                notify_user(
                    application["username"],
                    "你的打手申请已审核通过，账号现已开通。",
                    sender=session["username"],
                )
                try:
                    send_booster_application_review_email(application, True, approval_note)
                except Exception as exc:
                    print(f"[DEBUG] Failed to send booster approval email: {exc}", file=sys.stderr)
                flash("打手申请已审核通过，账号已创建。", "success")
            else:
                rejection_note = review_note or "资料不完整或截图不清晰。"
                update_booster_application(
                    application_id,
                    {
                        "status": "rejected",
                        "review_note": rejection_note,
                        "reviewed_at": now_text(),
                        "reviewed_by": session.get("username", "admin"),
                    },
                )
                try:
                    send_booster_application_review_email(application, False, rejection_note)
                except Exception as exc:
                    print(f"[DEBUG] Failed to send booster rejection email: {exc}", file=sys.stderr)
                flash("打手申请已驳回。", "success")
            return redirect(url_for("admin_users"))

        username = request.form.get("username", "").strip()
        user = get_user(username)

        if not user or user["username"] == system_username:
            flash("目标账号不存在。", "warning")
            return redirect(url_for("admin_users"))
        if user["role"] == "admin":
            flash("不能对管理员账号执行这个操作。", "warning")
            return redirect(url_for("admin_users"))

        if action == "ban":
            update_user(username, {"banned": True})
            notify_user(username, "你的账号已被管理员封禁，如有疑问请联系客服。", sender=session["username"])
            flash("账号已封禁。", "success")
        elif action == "unban":
            clear_failed_login_attempts(username, unlock_account=True)
            notify_user(username, "你的账号已被管理员解封，可以重新登录。", sender=session["username"])
            flash("账号已解封，失败登录次数已清零。", "success")
        elif action == "reset_password":
            new_password = request.form.get("new_password", "").strip()
            if not new_password:
                flash("请输入新密码。", "warning")
            else:
                password_error = validate_password_policy(new_password)
                if password_error:
                    flash(password_error, "warning")
                else:
                    clear_failed_login_attempts(username, unlock_account=True)
                    update_user(username, {"password": new_password})
                    notify_user(
                        username,
                        "管理员已为你重置密码，请尽快重新登录并修改。",
                        sender=session["username"],
                    )
                    flash("密码已重置，账号已解封。", "success")
        elif action == "delete":
            delete_user(username)
            flash("账号已删除。", "success")
        else:
            flash("不支持的操作。", "warning")

        return redirect(url_for("admin_users"))

    users = all_users()
    pending_booster_applications = [
        application
        for application in get_booster_applications(status="pending")
        if not application.get("store_id") and not application.get("store_owner_username")
    ]
    reviewed_booster_applications = [
        application
        for application in get_booster_applications()
        if application["status"] != "pending" and not application.get("store_id") and not application.get("store_owner_username")
    ][:10]
    return render_template(
        "admin_users.html",
        users=users,
        pending_booster_applications=pending_booster_applications,
        reviewed_booster_applications=reviewed_booster_applications,
    )


def social_login_disabled(provider):
    flash("微信和 QQ 登录已下线，请使用邮箱或手机号登录。", "warning")
    return redirect(url_for("login"))
