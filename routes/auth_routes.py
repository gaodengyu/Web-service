import sys

from flask import flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

# ==========================================
# 1. 新增：专属于商家和自定义审核等待的视图
# ==========================================
def waiting_approval_view():
    if not session.get("username"):
        return redirect(url_for("login"))
    return render_template("waiting_approval.html")


def register_view(
    *,
    redirect_to_dashboard,
    normalize_email,
    normalize_phone,
    looks_like_email,
    validate_password_policy,
    get_user_by_email,
    looks_like_phone,
    get_user_by_phone,
    reserved_usernames,
    get_user,
    start_auth_onboarding,
    hash_password,
    render_auth_gateway,
):
    if session.get("username"):
        return redirect_to_dashboard()
    if request.method == "POST":
        email = normalize_email(request.form.get("email", ""))
        phone = normalize_phone(request.form.get("phone", ""))
        password = request.form.get("pwd", "").strip()
        confirm_password = request.form.get("confirm_pwd", "").strip()
        preferred_username = request.form.get("username", "").strip()

        if not preferred_username:
            flash("请填写 ID。", "warning")
            return redirect(url_for("register"))

        if email and not looks_like_email(email):
            flash("请输入有效的邮箱地址。", "warning")
            return redirect(url_for("register"))

        password_error = validate_password_policy(password)
        if password_error:
            flash(password_error, "warning")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("两次输入的密码不一致。", "warning")
            return redirect(url_for("register"))
        if email and get_user_by_email(email):
            flash("这个邮箱已经注册过了，请直接登录。", "warning")
            return redirect(url_for("login"))
        if phone and not looks_like_phone(phone):
            flash("请输入有效的手机号。", "warning")
            return redirect(url_for("register"))
        if phone and get_user_by_phone(phone):
            flash("这个手机号已经绑定过账号了，请直接登录。", "warning")
            return redirect(url_for("login"))
        if preferred_username.lower() in reserved_usernames:
            flash("这个 ID 已被系统保留，请换一个。", "warning")
            return redirect(url_for("register"))
        if get_user(preferred_username):
            flash("这个 ID 已经有人使用了，请换一个。", "warning")
            return redirect(url_for("register"))

        start_auth_onboarding(
            {
                "flow": "email_signup",
                "email": email,
                "phone": phone,
                "password": hash_password(password),
                "auth_provider": "local",
                "social_id": "",
                "preferred_username": preferred_username,
            }
        )
        flash("账号信息已保存，下一步请选择你的入驻身份。", "info")
        return redirect(url_for("choose_role"))
    return render_auth_gateway(active_panel="register")


def login_view(
    *,
    redirect_to_dashboard,
    resolve_user_for_login,
    find_application_for_status_lookup,
    admin_password_matches,
    password_is_hashed,
    update_user,
    get_user,
    record_failed_login_attempt,
    max_login_attempts,
    clear_failed_login_attempts,
    clear_auth_onboarding,
    log_user_in,
    render_auth_gateway,
):
    if session.get("username"):
        return redirect_to_dashboard()
    if request.method == "POST":
        identifier = (request.form.get("identifier") or request.form.get("username") or "").strip()
        password = request.form.get("pwd", "").strip()
        user = resolve_user_for_login(identifier)
        if not user:
            # 这里的原生逻辑非常棒，完美处理了仍在审核中的“打手”
            pending_or_reviewed_application = find_application_for_status_lookup(identifier, password)
            if pending_or_reviewed_application:
                application = pending_or_reviewed_application["application"]
                role = pending_or_reviewed_application["role"]
                if application.get("status") == "rejected":
                    flash("审核失败账号已注销。", "danger")
                elif application.get("status") == "approved":
                    flash("审核已通过，账号正在开通中，请稍后重试登录。", "info")
                else:
                    flash("资料审核中，可在申请状态页查看最新进度。", "info")
                return redirect(
                    url_for(
                        "merchant_application_status",
                        application_role=role,
                        application_id=application.get("id", ""),
                        source="login",
                    )
                )
            flash("邮箱、手机号、用户名或密码错误。", "danger")
            return redirect(url_for("login"))
        if user.get("banned"):
            if user.get("lock_reason") == "too_many_failed_password_attempts":
                flash("账号已因多次输错密码被锁定，请先重置密码或联系管理员。", "danger")
            else:
                flash("账号已被封禁。", "danger")
            return redirect(url_for("login"))

        if user.get("role") == "admin":
            password_ok = admin_password_matches(password)
        else:
            stored_password = user.get("password", "")
            if password_is_hashed(stored_password):
                password_ok = check_password_hash(stored_password, password)
            else:
                password_ok = stored_password == password
                if password_ok:
                    update_user(user["username"], {"password": password})
                    user = get_user(user["username"])

        if not password_ok:
            attempts, locked = record_failed_login_attempt(user["username"])
            if locked:
                flash("密码连续输错 5 次，账号已被自动锁定，请重置密码后再登录。", "danger")
            else:
                remaining = max(max_login_attempts - attempts, 0)
                flash(f"密码错误，再输错 {remaining} 次将锁定账号。", "danger")
            return redirect(url_for("login"))

        clear_failed_login_attempts(user["username"])
        clear_auth_onboarding()
        log_user_in(user)
        
        # ==========================================
        # 2. 修改：登录成功后的精准路由分发
        # ==========================================
        role = user.get("role")
        profile = user.get("profile") or {}
        status = profile.get("status", "active")
        
        # 商家如果在审核中，拦截到审核页
        if role == "merchant" and status == "pending":
            return redirect(url_for("waiting_approval"))
            
        flash("登录成功。", "success")

        return redirect_to_dashboard()
        
    return render_auth_gateway(active_panel="login")


def forgot_password(
    *,
    normalize_email,
    validate_email_address,
    get_user,
    mail_is_configured,
    send_password_reset_email,
    validate_password_policy,
    verify_password_reset_code,
    clear_password_reset_state,
    update_user,
):
    # 此处逻辑保持不变，为节省空间已省略原样照搬你的代码
    stage = request.args.get("stage", "request")
    form_state = {"username": "", "email": ""}

    if request.method == "POST":
        action = request.form.get("action", "send_code").strip() or "send_code"
        username = request.form.get("username", "").strip()
        email = normalize_email(request.form.get("email", ""))
        form_state = {"username": username, "email": email}

        if not username or not email:
            flash("请先填写用户名和绑定邮箱。", "warning")
            return render_template("forgot_password.html", stage="request", form_state=form_state)

        email_error = validate_email_address(email)
        if email_error:
            flash(email_error, "warning")
            return render_template("forgot_password.html", stage="request", form_state=form_state)

        user = get_user(username)
        if not user:
            flash("账号或邮箱不匹配。", "danger")
            return render_template("forgot_password.html", stage="request", form_state=form_state)

        bound_email = normalize_email(user.get("email") or (user.get("profile") or {}).get("email", ""))
        if not bound_email:
            flash("该账号尚未绑定邮箱，请联系管理员处理。", "warning")
            return render_template("forgot_password.html", stage="request", form_state=form_state)
        if bound_email != email:
            flash("账号或邮箱不匹配。", "danger")
            return render_template("forgot_password.html", stage="request", form_state=form_state)

        if action == "send_code":
            if not mail_is_configured():
                flash("邮件服务未配置，当前无法发送验证码。", "warning")
                return render_template("forgot_password.html", stage="request", form_state=form_state)
            try:
                send_password_reset_email(username, bound_email)
            except Exception as exc:
                print(f"[DEBUG] Failed to send password reset email: {exc}", file=sys.stderr)
                flash("验证码邮件发送失败，请稍后再试。", "danger")
                return render_template("forgot_password.html", stage="request", form_state=form_state)

            flash(f"验证码已发送到 {bound_email}，请尽快完成验证。", "success")
            return render_template("forgot_password.html", stage="verify", form_state=form_state)

        verification_code = request.form.get("verification_code", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not verification_code or not new_password or not confirm_password:
            flash("请完整填写验证码和新密码。", "warning")
            return render_template("forgot_password.html", stage="verify", form_state=form_state)
        if new_password != confirm_password:
            flash("两次输入的新密码不一致。", "warning")
            return render_template("forgot_password.html", stage="verify", form_state=form_state)

        password_error = validate_password_policy(new_password)
        if password_error:
            flash(password_error, "warning")
            return render_template("forgot_password.html", stage="verify", form_state=form_state)

        code_ok, code_message = verify_password_reset_code(user, verification_code)
        if not code_ok:
            flash(code_message, "danger")
            return render_template("forgot_password.html", stage="verify", form_state=form_state)

        clear_password_reset_state(username)
        profile = dict(user.get("profile") or {})
        profile["email"] = bound_email
        profile["failed_login_attempts"] = 0
        profile.pop("lock_reason", None)
        update_user(
            username,
            {
                "password": new_password,
                "email": bound_email,
                "profile": profile,
                "banned": False,
            },
        )
        flash("密码已重置，请使用新密码登录。", "success")
        return redirect(url_for("login"))

    return render_template("forgot_password.html", stage=stage, form_state=form_state)


def choose_role_view(
    *,
    redirect_to_dashboard,
    get_auth_onboarding,
    normalize_email,
    normalize_phone,
    reserved_usernames,
    get_user,
    find_pending_booster_application_by_username,
    looks_like_email,
    looks_like_phone,
    get_user_by_email,
    get_user_by_phone,
    find_pending_booster_application_by_email,
    save_uploaded_image,
    add_booster_application,
    clear_auth_onboarding,
    add_user,
    log_user_in,
    unique_username_from_seed,
    social_provider_labels,
):
    if session.get("username"):
        return redirect_to_dashboard()

    onboarding = get_auth_onboarding()
    if not onboarding:
        flash("请先完成登录或注册。", "warning")
        return redirect(url_for("login"))

    form_username = request.form.get("username", "").strip() if request.method == "POST" else ""
    form_email = normalize_email(request.form.get("email", "")) if request.method == "POST" else ""
    form_phone = normalize_phone(request.form.get("phone", "")) if request.method == "POST" else ""
    form_game_account = request.form.get("game_account", "").strip() if request.method == "POST" else ""
    form_game_name = request.form.get("game_name", "").strip() if request.method == "POST" else ""
    form_game_id = request.form.get("game_id", "").strip() if request.method == "POST" else ""
    form_rank = request.form.get("rank", "").strip() if request.method == "POST" else ""
    form_intro = request.form.get("intro", "").strip() if request.method == "POST" else ""
    composed_game_account = form_game_account or form_game_id
    if not composed_game_account and form_game_name:
        composed_game_account = form_game_name
    elif form_game_name and form_game_id:
        composed_game_account = f"{form_game_name} / {form_game_id}"
    selected_role = request.form.get("role", "").strip() if request.method == "POST" else "player"

    if request.method == "POST":
        role = selected_role
        username = form_username or (onboarding.get("preferred_username") or "").strip()
        email = form_email or normalize_email(onboarding.get("email", ""))
        phone = form_phone or normalize_phone(onboarding.get("phone", ""))
        auth_provider = onboarding.get("auth_provider", "local")
        social_id = onboarding.get("social_id", "")

        if role not in {"player", "booster", "merchant"}:
            flash("请选择你的身份。", "warning")
        elif not username:
            flash("请填写一个昵称。", "warning")
        elif username.lower() in reserved_usernames:
            flash("这个昵称已被系统保留，请换一个。", "warning")
        elif get_user(username):
            flash("这个昵称已经有人使用了，请换一个。", "warning")
        elif find_pending_booster_application_by_username(username):
            flash("这个昵称已经提交过打手申请，请等待审核。", "warning")
        elif auth_provider == "local" and not looks_like_email(email):
            flash("邮箱注册需要填写有效邮箱。", "warning")
        elif email and not looks_like_email(email):
            flash("请输入有效的邮箱地址。", "warning")
        elif phone and not looks_like_phone(phone):
            flash("请输入有效的手机号。", "warning")
        else:
            existing_email_user = get_user_by_email(email) if email else None
            existing_phone_user = get_user_by_phone(phone) if phone else None
            pending_email_application = find_pending_booster_application_by_email(email) if email else None

            if existing_email_user:
                flash("这个邮箱已经绑定了其他账号。", "warning")
            elif existing_phone_user:
                flash("这个手机号已经绑定了其他账号。", "warning")
            elif pending_email_application and pending_email_application["username"] != username:
                flash("这个邮箱已经提交过打手申请，请等待审核。", "warning")
            
            # ==========================================
            # 打手逻辑：保持你们原有的高级申请表机制不变
            # ==========================================
            elif role == "booster":
                proof_image = request.files.get("proof_image")
                if not email:
                    flash("申请打手需要填写邮箱，方便审核通知。", "warning")
                elif not composed_game_account:
                    flash("申请打手需要填写游戏账号信息。", "warning")
                elif not proof_image or not getattr(proof_image, "filename", ""):
                    flash("申请打手需要上传资质截图。", "warning")
                else:
                    try:
                        proof_image_path = save_uploaded_image(
                            proof_image,
                            "uploads",
                            "boosters",
                            "proof",
                            prefix=f"booster_proof_{username}",
                        )
                    except ValueError as exc:
                        flash(str(exc), "warning")
                    else:
                        booster_profile = {
                            "display_name": username,
                            "auth_provider": auth_provider,
                            "game_name": form_game_name,
                            "game_id": form_game_id,
                            "rank": form_rank,
                            "intro": form_intro,
                        }
                        add_booster_application(
                            username,
                            onboarding.get("password", ""),
                            email=email,
                            phone=phone,
                            auth_provider=auth_provider,
                            social_id=social_id,
                            game_account=composed_game_account,
                            proof_image_path=proof_image_path,
                            profile=booster_profile,
                        )
                        pending_application = find_pending_booster_application_by_username(username)
                        clear_auth_onboarding()
                        flash("打手申请已提交，等待平台审核。", "success")
                        if pending_application:
                            # 继续跳转到你们原生的打手审核状态页
                            return redirect(
                                url_for(
                                    "merchant_application_status",
                                    application_role="booster",
                                    application_id=pending_application.get("id", ""),
                                    source="register",
                                )
                            )
                        return redirect(url_for("merchant_application_status"))
                        
            # ==========================================
            # 3. 修改：区分商家（进等待页）和玩家（进大厅）
            # ==========================================
            elif role == "merchant":
                profile = {
                    "display_name": username,
                    "auth_provider": auth_provider,
                    "status": "pending"  # 核心：为商家打上待审核标签
                }
                add_user(
                    username,
                    onboarding.get("password", ""),
                    role,
                    profile=profile,
                    email=email,
                    phone=phone,
                    auth_provider=auth_provider,
                    social_id=social_id,
                )
                user = get_user(username)
                clear_auth_onboarding()
                log_user_in(user)
                flash("商家申请已提交，等待平台审核。", "success")
                return redirect(url_for("waiting_approval"))

            else: # role == "player"
                profile = {
                    "display_name": username,
                    "auth_provider": auth_provider,
                    "status": "active"  # 核心：玩家直接激活
                }
                add_user(
                    username,
                    onboarding.get("password", ""),
                    role,
                    profile=profile,
                    email=email,
                    phone=phone,
                    auth_provider=auth_provider,
                    social_id=social_id,
                )
                user = get_user(username)
                clear_auth_onboarding()
                log_user_in(user)
                flash("注册完成，欢迎来到 GameBuddy。", "success")
                # 直接送玩家去大厅选店！
                return redirect(url_for("boosters_list"))

    provider = onboarding.get("auth_provider", "local")
    provider_label = "邮箱" if provider == "local" else social_provider_labels.get(provider, provider)
    suggested_username = form_username or onboarding.get("preferred_username") or unique_username_from_seed(provider, provider or "gb")
    suggested_email = form_email or normalize_email(onboarding.get("email", ""))
    suggested_phone = form_phone or normalize_phone(onboarding.get("phone", ""))
    return render_template(
        "choose_role.html",
        onboarding=onboarding,
        provider_label=provider_label,
        suggested_username=suggested_username,
        suggested_email=suggested_email,
        suggested_phone=suggested_phone,
        selected_role=selected_role or "player",
        launch_image_url=url_for("static", filename="images/gamebuddy-launch-source.png"),
    )
