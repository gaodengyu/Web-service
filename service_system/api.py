from __future__ import annotations

from routes.api_routes import (
    api_admin_booster_review as routes_api_admin_booster_review,
    api_admin_merchant_review as routes_api_admin_merchant_review,
    api_admin_order_action as routes_api_admin_order_action,
    api_admin_orders as routes_api_admin_orders,
    api_admin_store_review as routes_api_admin_store_review,
    api_admin_user_action as routes_api_admin_user_action,
    api_admin_users as routes_api_admin_users,
    api_bootstrap as routes_api_bootstrap,
    api_chat_send as routes_api_chat_send,
    api_chat_thread as routes_api_chat_thread,
    api_chats as routes_api_chats,
    api_create_store_order as routes_api_create_store_order,
    api_dashboard as routes_api_dashboard,
    api_discovery as routes_api_discovery,
    api_login as routes_api_login,
    api_logout as routes_api_logout,
    api_orders as routes_api_orders,
    api_store_detail as routes_api_store_detail,
    api_wallet as routes_api_wallet,
    api_wallet_recharge as routes_api_wallet_recharge,
    api_wallet_withdraw as routes_api_wallet_withdraw,
)


def register_service_api_routes(blueprint, api_deps_factory):
    @blueprint.route("/api/bootstrap")
    def api_bootstrap():
        return routes_api_bootstrap(api_deps_factory())

    @blueprint.route("/api/auth/login", methods=["POST"])
    def api_login():
        return routes_api_login(api_deps_factory())

    @blueprint.route("/api/auth/logout", methods=["POST"])
    def api_logout():
        return routes_api_logout(api_deps_factory())

    @blueprint.route("/api/stores")
    def api_stores():
        return routes_api_discovery(api_deps_factory())

    @blueprint.route("/api/stores/<store_slug>")
    def api_store(store_slug):
        return routes_api_store_detail(store_slug, api_deps_factory())

    @blueprint.route("/api/dashboard")
    def api_dashboard():
        return routes_api_dashboard(api_deps_factory())

    @blueprint.route("/api/orders")
    def api_orders():
        return routes_api_orders(api_deps_factory())

    @blueprint.route("/api/wallet")
    def api_wallet():
        return routes_api_wallet(api_deps_factory())

    @blueprint.route("/api/wallet/recharge", methods=["POST"])
    def api_wallet_recharge():
        return routes_api_wallet_recharge(api_deps_factory())

    @blueprint.route("/api/wallet/withdraw", methods=["POST"])
    def api_wallet_withdraw():
        return routes_api_wallet_withdraw(api_deps_factory())

    @blueprint.route("/api/chats")
    def api_chats():
        return routes_api_chats(api_deps_factory())

    @blueprint.route("/api/chats/<partner>")
    def api_chat_thread(partner):
        return routes_api_chat_thread(partner, api_deps_factory())

    @blueprint.route("/api/chats/<partner>", methods=["POST"])
    def api_chat_send(partner):
        return routes_api_chat_send(partner, api_deps_factory())

    @blueprint.route("/api/admin/users")
    def api_admin_users():
        return routes_api_admin_users(api_deps_factory())

    @blueprint.route("/api/admin/users/actions", methods=["POST"])
    def api_admin_user_action():
        return routes_api_admin_user_action(api_deps_factory())

    @blueprint.route("/api/admin/store-applications/<int:store_id>/review", methods=["POST"])
    def api_admin_store_review(store_id):
        return routes_api_admin_store_review(store_id, api_deps_factory())

    @blueprint.route("/api/admin/booster-applications/<int:application_id>/review", methods=["POST"])
    def api_admin_booster_review(application_id):
        return routes_api_admin_booster_review(application_id, api_deps_factory())

    @blueprint.route("/api/admin/merchant-applications/<int:application_id>/review", methods=["POST"])
    def api_admin_merchant_review(application_id):
        return routes_api_admin_merchant_review(application_id, api_deps_factory())

    @blueprint.route("/api/admin/orders")
    def api_admin_orders():
        return routes_api_admin_orders(api_deps_factory())

    @blueprint.route("/api/admin/orders/<int:order_id>/actions", methods=["POST"])
    def api_admin_order_action(order_id):
        return routes_api_admin_order_action(order_id, api_deps_factory())

    @blueprint.route("/api/orders/store/<store_slug>", methods=["POST"])
    def api_create_store_order(store_slug):
        return routes_api_create_store_order(store_slug, api_deps_factory())
