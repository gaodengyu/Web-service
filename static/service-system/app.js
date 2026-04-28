const SERVICE_ROOT = "/service";
const DEFAULT_FILTERS = {
    q: "",
    game: "",
    max_price: "",
    sort: "recommended",
};
const STATUS_COMPLETED = "\u5df2\u5b8c\u6210";
const STATUS_NO_COMPLAINT = "\u65e0\u6295\u8bc9";
const ACTIVE_ORDER_STATUSES = [
    "\u5f85\u63a5\u5f85",
    "\u5df2\u63a5\u5355",
    "\u5f85\u786e\u8ba4\u5b8c\u6210",
];

const state = {
    bootstrap: null,
    session: null,
    csrfToken: "",
    route: parseRoute(),
    page: {
        status: "loading",
        data: null,
        error: "",
    },
    cache: {
        discovery: new Map(),
        stores: new Map(),
        dashboard: null,
        orders: null,
        wallet: null,
        chats: null,
        chatThreads: new Map(),
        adminUsers: null,
        adminOrders: new Map(),
    },
    requestToken: 0,
    toast: null,
    toastTimer: null,
};

const root = document.getElementById("service-app");

const ROLE_METRICS = {
    player: [
        ["total_orders", "Orders"],
        ["pending_orders", "Pending"],
        ["completed_orders", "Completed"],
        ["complaint_orders", "Complaints"],
        ["total_spend", "Spend"],
    ],
    booster: [
        ["total_orders", "Orders"],
        ["active_orders", "Active"],
        ["completed_orders", "Completed"],
        ["avg_rating", "Rating"],
        ["total_income", "Income"],
        ["completion_rate", "Completion"],
        ["recommendation_score", "Score"],
    ],
    merchant: [
        ["booster_count", "Boosters"],
        ["orders_count", "Orders"],
        ["completed_orders", "Completed"],
        ["pending_orders", "Pending"],
        ["gmv", "GMV"],
        ["avg_rating", "Rating"],
    ],
    admin: [
        ["users_count", "Users"],
        ["players_count", "Players"],
        ["boosters_count", "Boosters"],
        ["merchants_count", "Merchants"],
        ["stores_count", "Stores"],
        ["orders_count", "Orders"],
        ["completed_orders_count", "Completed"],
        ["pending_complaints_count", "Complaints"],
        ["avg_rating", "Rating"],
        ["conversion_rate", "Conversion"],
    ],
};

window.addEventListener("popstate", () => {
    syncRoute();
});

root.addEventListener("click", (event) => {
    const link = event.target.closest("[data-link]");
    if (link) {
        event.preventDefault();
        navigate(link.getAttribute("href") || SERVICE_ROOT);
        return;
    }

    const actionTarget = event.target.closest("[data-action]");
    if (!actionTarget) {
        return;
    }

    const action = actionTarget.dataset.action;
    if (action === "logout") {
        event.preventDefault();
        handleLogout();
        return;
    }
    if (action === "retry") {
        event.preventDefault();
        syncRoute({ force: true });
    }
});

root.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) {
        return;
    }

    if (form.dataset.form === "login") {
        event.preventDefault();
        handleLogin(form, event.submitter);
        return;
    }

    if (form.dataset.form === "discovery-filters") {
        event.preventDefault();
        handleDiscoveryFilterSubmit(form, event.submitter);
        return;
    }

    if (form.dataset.form === "store-order") {
        event.preventDefault();
        handleStoreOrder(form, event.submitter);
        return;
    }

    if (form.dataset.form === "wallet-recharge") {
        event.preventDefault();
        handleWalletRecharge(form, event.submitter);
        return;
    }

    if (form.dataset.form === "wallet-withdraw") {
        event.preventDefault();
        handleWalletWithdraw(form, event.submitter);
        return;
    }

    if (form.dataset.form === "chat-send") {
        event.preventDefault();
        handleChatSend(form, event.submitter);
        return;
    }

    if (form.dataset.form === "admin-user-action") {
        event.preventDefault();
        handleAdminUserAction(form, event.submitter);
        return;
    }

    if (form.dataset.form === "admin-store-review") {
        event.preventDefault();
        handleAdminStoreReview(form, event.submitter);
        return;
    }

    if (form.dataset.form === "admin-booster-review") {
        event.preventDefault();
        handleAdminBoosterReview(form, event.submitter);
        return;
    }

    if (form.dataset.form === "admin-merchant-review") {
        event.preventDefault();
        handleAdminMerchantReview(form, event.submitter);
        return;
    }

    if (form.dataset.form === "admin-order-action") {
        event.preventDefault();
        handleAdminOrderAction(form, event.submitter);
        return;
    }

    if (form.dataset.form === "admin-order-filters") {
        event.preventDefault();
        handleAdminOrderFilterSubmit(form, event.submitter);
    }
});

boot();

function buildFormData(form, submitter) {
    const formData = new FormData(form);
    if (submitter?.name) {
        formData.set(submitter.name, submitter.value || "");
    }
    return formData;
}

async function boot() {
    renderBootScreen("Loading service system...");
    try {
        await refreshBootstrap({ force: true });
        await syncRoute({ force: true });
    } catch (error) {
        state.page = {
            status: "error",
            data: null,
            error: getErrorMessage(error),
        };
        render();
    }
}

async function refreshBootstrap({ force = false } = {}) {
    if (state.bootstrap && !force) {
        return state.bootstrap;
    }
    const payload = await requestJson("/api/bootstrap");
    state.bootstrap = payload;
    state.session = payload.session || null;
    state.csrfToken = payload.csrfToken || state.csrfToken;
    return payload;
}

async function syncRoute({ force = false } = {}) {
    state.route = parseRoute();

    if (routeRequiresAuth(state.route) && !state.session) {
        navigate(buildLoginHref(currentServiceLocation()), { replace: true });
        return;
    }

    const token = ++state.requestToken;
    state.page = {
        status: "loading",
        data: null,
        error: "",
    };
    render();

    try {
        const data = await loadRouteData(state.route, { force });
        if (token !== state.requestToken) {
            return;
        }
        state.page = {
            status: "ready",
            data,
            error: "",
        };
        render();
    } catch (error) {
        if (token !== state.requestToken) {
            return;
        }
        if (error.status === 401) {
            state.session = null;
            syncBootstrapSession();
            invalidateUserCaches();
            if (routeRequiresAuth(state.route)) {
                showToast("Session expired. Please sign in again.", "danger");
                navigate(buildLoginHref(currentServiceLocation()), { replace: true });
                return;
            }
        }
        state.page = {
            status: "error",
            data: null,
            error: getErrorMessage(error),
        };
        render();
    }
}

async function loadRouteData(route, { force = false } = {}) {
    if (route.name === "home") {
        return loadDiscovery(route.filters, { force });
    }
    if (route.name === "store") {
        return loadStoreDetail(route.slug, { force });
    }
    if (route.name === "dashboard") {
        return loadDashboard({ force });
    }
    if (route.name === "orders") {
        return loadOrders({ force });
    }
    if (route.name === "wallet") {
        return loadWallet({ force });
    }
    if (route.name === "chats") {
        return loadChats({ force });
    }
    if (route.name === "chat_thread") {
        return loadChatThread(route.partner, { force });
    }
    if (route.name === "admin_users") {
        return loadAdminUsers({ force });
    }
    if (route.name === "admin_orders") {
        return loadAdminOrders(route.filters, { force });
    }
    return {};
}

async function loadDiscovery(filters, { force = false } = {}) {
    const normalized = {
        ...DEFAULT_FILTERS,
        ...(filters || {}),
    };
    const cacheKey = JSON.stringify(normalized);
    if (!force && state.cache.discovery.has(cacheKey)) {
        return state.cache.discovery.get(cacheKey);
    }

    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(normalized)) {
        if (value && !(key === "sort" && value === DEFAULT_FILTERS.sort)) {
            params.set(key, value);
        }
    }

    const query = params.toString();
    const payload = await requestJson(`/api/stores${query ? `?${query}` : ""}`);
    state.cache.discovery.set(cacheKey, payload);
    return payload;
}

async function loadStoreDetail(slug, { force = false } = {}) {
    if (!force && state.cache.stores.has(slug)) {
        return state.cache.stores.get(slug);
    }
    const payload = await requestJson(`/api/stores/${encodeURIComponent(slug)}`);
    state.cache.stores.set(slug, payload);
    return payload;
}

async function loadDashboard({ force = false } = {}) {
    if (!force && state.cache.dashboard) {
        return state.cache.dashboard;
    }
    const payload = await requestJson("/api/dashboard");
    state.cache.dashboard = payload;
    return payload;
}

async function loadOrders({ force = false } = {}) {
    if (!force && state.cache.orders) {
        return state.cache.orders;
    }
    const payload = await requestJson("/api/orders");
    state.cache.orders = payload;
    return payload;
}

async function loadWallet({ force = false } = {}) {
    if (!force && state.cache.wallet) {
        return state.cache.wallet;
    }
    const payload = await requestJson("/api/wallet");
    state.cache.wallet = payload;
    return payload;
}

async function loadChats({ force = false } = {}) {
    if (!force && state.cache.chats) {
        return state.cache.chats;
    }
    const payload = await requestJson("/api/chats");
    state.cache.chats = payload;
    return payload;
}

async function loadChatThread(partner, { force = false } = {}) {
    const cacheKey = partner || "";
    if (!force && state.cache.chatThreads.has(cacheKey)) {
        return state.cache.chatThreads.get(cacheKey);
    }
    const payload = await requestJson(`/api/chats/${encodeURIComponent(cacheKey)}`);
    state.cache.chatThreads.set(cacheKey, payload);
    return payload;
}

async function loadAdminUsers({ force = false } = {}) {
    if (!force && state.cache.adminUsers) {
        return state.cache.adminUsers;
    }
    const payload = await requestJson("/api/admin/users");
    state.cache.adminUsers = payload;
    return payload;
}

async function loadAdminOrders(filters, { force = false } = {}) {
    const normalized = {
        keyword: (filters?.keyword || "").trim(),
        status: (filters?.status || "").trim(),
        complaint: (filters?.complaint || "").trim(),
    };
    const cacheKey = JSON.stringify(normalized);
    if (!force && state.cache.adminOrders.has(cacheKey)) {
        return state.cache.adminOrders.get(cacheKey);
    }
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(normalized)) {
        if (value) {
            params.set(key, value);
        }
    }
    const payload = await requestJson(`/api/admin/orders${params.toString() ? `?${params.toString()}` : ""}`);
    state.cache.adminOrders.set(cacheKey, payload);
    return payload;
}

async function handleLogin(form, submitter) {
    const submitButton = form.querySelector('button[type="submit"]');
    setButtonBusy(submitButton, true, "Signing in...");
    const formData = buildFormData(form, submitter);

    try {
        const payload = await requestJson("/api/auth/login", {
            method: "POST",
            body: {
                identifier: (formData.get("identifier") || "").toString().trim(),
                password: (formData.get("password") || "").toString(),
            },
        });
        state.session = payload.session || null;
        state.csrfToken = payload.csrfToken || state.csrfToken;
        syncBootstrapSession();
        invalidateUserCaches();
        showToast("Signed in successfully.");
        const fallback = state.session?.dashboardPath || buildServiceHref("dashboard");
        const target = sanitizeNextPath(state.route.next || fallback);
        navigate(target, { replace: true });
    } catch (error) {
        showToast(getErrorMessage(error), "danger");
        setButtonBusy(submitButton, false);
    }
}

async function handleLogout() {
    try {
        const payload = await requestJson("/api/auth/logout", {
            method: "POST",
            body: {},
        });
        state.session = null;
        state.csrfToken = payload.csrfToken || state.csrfToken;
        syncBootstrapSession();
        invalidateUserCaches();
        showToast("Signed out.");
        navigate(buildServiceHref(), { replace: true });
    } catch (error) {
        showToast(getErrorMessage(error), "danger");
    }
}

function handleDiscoveryFilterSubmit(form, submitter) {
    const formData = buildFormData(form, submitter);
    const filters = {
        q: (formData.get("q") || "").toString().trim(),
        game: (formData.get("game") || "").toString().trim(),
        max_price: (formData.get("max_price") || "").toString().trim(),
        sort: (formData.get("sort") || DEFAULT_FILTERS.sort).toString().trim() || DEFAULT_FILTERS.sort,
    };
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
        if (value && !(key === "sort" && value === DEFAULT_FILTERS.sort)) {
            params.set(key, value);
        }
    }
    navigate(`${buildServiceHref()}${params.toString() ? `?${params.toString()}` : ""}`);
}

async function handleStoreOrder(form, submitter) {
    if (!state.session) {
        navigate(buildLoginHref(currentServiceLocation()));
        return;
    }
    if (state.session.role !== "player") {
        showToast("Only player accounts can create store orders here.", "danger");
        return;
    }

    const submitButton = form.querySelector('button[type="submit"]');
    setButtonBusy(submitButton, true, "Creating order...");
    const formData = buildFormData(form, submitter);
    const storeSlug = form.dataset.storeSlug || "";
    const payload = {
        selected_booster: (formData.get("selected_booster") || "").toString().trim(),
        service_type: (formData.get("service_type") || "").toString().trim(),
        game: (formData.get("game") || "").toString().trim(),
        target_rank: (formData.get("target_rank") || "").toString().trim(),
        detail: (formData.get("detail") || "").toString().trim(),
        start_time_mode: (formData.get("start_time_mode") || "custom").toString().trim(),
        order_hours: (formData.get("order_hours") || "1").toString().trim(),
        start_time: (formData.get("start_time") || "").toString().trim(),
        payment_method: (formData.get("payment_method") || "stripe").toString().trim(),
    };

    try {
        const response = await requestJson(`/api/orders/store/${encodeURIComponent(storeSlug)}`, {
            method: "POST",
            body: payload,
        });

        if (response.paymentMode === "stripe" && response.checkoutUrl) {
            showToast("Redirecting to Stripe checkout...");
            window.location.assign(response.checkoutUrl);
            return;
        }

        invalidateUserCaches();
        await refreshBootstrap({ force: true });
        showToast(response.message || "Order created.");
        navigate(buildServiceHref("orders"));
    } catch (error) {
        showToast(getErrorMessage(error), "danger");
        setButtonBusy(submitButton, false);
    }
}

async function handleWalletRecharge(form, submitter) {
    const submitButton = form.querySelector('button[type="submit"]');
    setButtonBusy(submitButton, true, "Creating checkout...");
    const formData = buildFormData(form, submitter);
    try {
        const response = await requestJson("/api/wallet/recharge", {
            method: "POST",
            body: {
                amount: (formData.get("amount") || "").toString().trim(),
            },
        });
        if (response.checkoutUrl) {
            showToast("Redirecting to Stripe recharge...");
            window.location.assign(response.checkoutUrl);
            return;
        }
        showToast(response.message || "Recharge session created.");
        setButtonBusy(submitButton, false);
    } catch (error) {
        showToast(getErrorMessage(error), "danger");
        setButtonBusy(submitButton, false);
    }
}

async function handleWalletWithdraw(form, submitter) {
    const submitButton = form.querySelector('button[type="submit"]');
    setButtonBusy(submitButton, true, "Submitting withdrawal...");
    const formData = buildFormData(form, submitter);
    try {
        await requestJson("/api/wallet/withdraw", {
            method: "POST",
            body: {
                amount: (formData.get("amount") || "").toString().trim(),
            },
        });
        invalidateUserCaches();
        state.cache.wallet = null;
        await refreshBootstrap({ force: true });
        showToast("Withdrawal submitted.");
        await syncRoute({ force: true });
    } catch (error) {
        showToast(getErrorMessage(error), "danger");
        setButtonBusy(submitButton, false);
    }
}

async function handleChatSend(form, submitter) {
    const submitButton = form.querySelector('button[type="submit"]');
    setButtonBusy(submitButton, true, "Sending...");
    const formData = buildFormData(form, submitter);
    const partner = form.dataset.partner || "";
    const messageField = form.querySelector('textarea[name="message"]');
    try {
        await requestJson(`/api/chats/${encodeURIComponent(partner)}`, {
            method: "POST",
            body: {
                message: (formData.get("message") || "").toString(),
            },
        });
        if (messageField) {
            messageField.value = "";
        }
        state.cache.chats = null;
        state.cache.chatThreads.delete(partner);
        await syncRoute({ force: true });
    } catch (error) {
        showToast(getErrorMessage(error), "danger");
        setButtonBusy(submitButton, false);
    }
}

async function handleAdminUserAction(form, submitter) {
    const submitButton = form.querySelector('button[type="submit"]');
    setButtonBusy(submitButton, true, "Saving...");
    const formData = buildFormData(form, submitter);
    try {
        await requestJson("/api/admin/users/actions", {
            method: "POST",
            body: {
                username: (formData.get("username") || "").toString().trim(),
                action: (formData.get("action") || "").toString().trim(),
                newPassword: (formData.get("new_password") || "").toString(),
            },
        });
        state.cache.adminUsers = null;
        showToast("Admin user action completed.");
        await syncRoute({ force: true });
    } catch (error) {
        showToast(getErrorMessage(error), "danger");
        setButtonBusy(submitButton, false);
    }
}

async function handleAdminStoreReview(form, submitter) {
    await handleAdminReviewForm(form, submitter, "store");
}

async function handleAdminBoosterReview(form, submitter) {
    await handleAdminReviewForm(form, submitter, "booster");
}

async function handleAdminMerchantReview(form, submitter) {
    await handleAdminReviewForm(form, submitter, "merchant");
}

async function handleAdminReviewForm(form, submitter, reviewType) {
    const submitButton = form.querySelector('button[type="submit"]');
    setButtonBusy(submitButton, true, "Saving...");
    const formData = buildFormData(form, submitter);
    let endpoint = "";
    if (reviewType === "store") {
        endpoint = `/api/admin/store-applications/${encodeURIComponent((formData.get("store_id") || "").toString())}/review`;
    } else if (reviewType === "booster") {
        endpoint = `/api/admin/booster-applications/${encodeURIComponent((formData.get("application_id") || "").toString())}/review`;
    } else {
        endpoint = `/api/admin/merchant-applications/${encodeURIComponent((formData.get("merchant_application_id") || "").toString())}/review`;
    }

    try {
        await requestJson(endpoint, {
            method: "POST",
            body: {
                action: (formData.get("action") || "").toString().trim(),
                reviewNote: (formData.get("review_note") || "").toString().trim(),
            },
        });
        state.cache.adminUsers = null;
        showToast("Review result saved.");
        await syncRoute({ force: true });
    } catch (error) {
        showToast(getErrorMessage(error), "danger");
        setButtonBusy(submitButton, false);
    }
}

async function handleAdminOrderAction(form, submitter) {
    const submitButton = form.querySelector('button[type="submit"]');
    setButtonBusy(submitButton, true, "Saving...");
    const formData = buildFormData(form, submitter);
    const orderId = (formData.get("order_id") || "").toString().trim();
    try {
        await requestJson(`/api/admin/orders/${encodeURIComponent(orderId)}/actions`, {
            method: "POST",
            body: {
                action: (formData.get("action") || "").toString().trim(),
                complaintStatus: (formData.get("complaint_status") || "").toString().trim(),
                complaintReply: (formData.get("complaint_reply") || "").toString().trim(),
                adminNote: (formData.get("admin_note") || "").toString().trim(),
            },
        });
        state.cache.adminOrders.clear();
        state.cache.orders = null;
        showToast("Order action saved.");
        await syncRoute({ force: true });
    } catch (error) {
        showToast(getErrorMessage(error), "danger");
        setButtonBusy(submitButton, false);
    }
}

function handleAdminOrderFilterSubmit(form, submitter) {
    const formData = buildFormData(form, submitter);
    const params = new URLSearchParams();
    for (const key of ["keyword", "status", "complaint"]) {
        const value = (formData.get(key) || "").toString().trim();
        if (value) {
            params.set(key, value);
        }
    }
    navigate(`${buildServiceHref("admin/orders")}${params.toString() ? `?${params.toString()}` : ""}`);
}

function render() {
    if (!state.bootstrap) {
        renderBootScreen(state.page.error || "Loading service system...");
        return;
    }

    const viewMeta = getViewMeta(state.route, state.page.data);
    root.innerHTML = `
        <div class="service-shell">
            ${renderSidebar()}
            <main class="service-main">
                ${renderTopbar(viewMeta)}
                ${renderView()}
            </main>
        </div>
        ${renderToast()}
    `;
}

function renderBootScreen(message) {
    root.innerHTML = `<div class="service-loading">${escapeHtml(message || "Loading...")}</div>`;
}

function renderSidebar() {
    const isAdmin = state.session?.role === "admin";
    const navItems = [
        {
            href: buildServiceHref(),
            label: "Storefront",
            active: state.route.name === "home" || state.route.name === "store",
        },
        {
            href: buildServiceHref("dashboard"),
            label: "Dashboard",
            active: state.route.name === "dashboard",
            hidden: !state.session,
        },
        {
            href: buildServiceHref("orders"),
            label: "Orders",
            active: state.route.name === "orders",
            hidden: !state.session,
        },
        {
            href: buildServiceHref("wallet"),
            label: "Wallet",
            active: state.route.name === "wallet",
            hidden: !state.session || isAdmin,
        },
        {
            href: buildServiceHref("chats"),
            label: "Chats",
            active: state.route.name === "chats" || state.route.name === "chat_thread",
            hidden: !state.session || isAdmin,
        },
        {
            href: buildServiceHref("admin/users"),
            label: "Admin Users",
            active: state.route.name === "admin_users",
            hidden: !isAdmin,
        },
        {
            href: buildServiceHref("admin/orders"),
            label: "Admin Orders",
            active: state.route.name === "admin_orders",
            hidden: !isAdmin,
        },
        {
            href: buildLoginHref(currentServiceLocation()),
            label: "Sign in",
            active: state.route.name === "login",
            hidden: Boolean(state.session),
        },
    ];

    const sessionMarkup = state.session
        ? `
            <div class="sidebar-user">
                <strong>${escapeHtml(state.session.displayName || state.session.username)}</strong>
                <span class="user-role">${escapeHtml(state.session.roleLabel || state.session.role || "")}</span>
                <div class="wallet-row">
                    <span>Balance ${escapeHtml(formatNumber(state.session.wallet?.balance || 0))}</span>
                    <span>Available ${escapeHtml(formatNumber(state.session.wallet?.available || 0))}</span>
                </div>
                <div class="button-row">
                    <button class="ghost-btn" data-action="logout" type="button">Sign out</button>
                </div>
            </div>
        `
        : `
            <div class="sidebar-user">
                <strong>Guest mode</strong>
                <span class="user-role">Browse public stores, then sign in when you want to place an order.</span>
                <div class="button-row">
                    <a class="ghost-btn" href="${escapeHtml(buildLoginHref(currentServiceLocation()))}" data-link>Sign in</a>
                </div>
            </div>
        `;

    return `
        <aside class="service-sidebar">
            <div>
                <div class="brand-mark">
                    <span>GB</span>
                    <span>GameBuddy Service</span>
                </div>
                <p class="sidebar-copy">
                    Frontend shell, API routes, and the existing database are now wired as a service-facing system without removing the legacy pages.
                </p>
            </div>
            <nav class="sidebar-nav">
                ${navItems
                    .filter((item) => !item.hidden)
                    .map(
                        (item) => `
                            <a class="nav-link${item.active ? " is-active" : ""}" href="${escapeHtml(item.href)}" data-link>
                                <span>${escapeHtml(item.label)}</span>
                                <span>&rsaquo;</span>
                            </a>
                        `
                    )
                    .join("")}
            </nav>
            ${sessionMarkup}
        </aside>
    `;
}

function renderTopbar(meta) {
    const actionMarkup = state.session
        ? `
            <div class="topbar-actions">
                <a class="ghost-btn" href="${escapeHtml(buildServiceHref())}" data-link>Browse</a>
                <a class="ghost-btn" href="${escapeHtml(buildServiceHref("dashboard"))}" data-link>Dashboard</a>
                <a class="btn is-accent" href="${escapeHtml(topbarPrimaryHref())}" data-link>${escapeHtml(topbarPrimaryLabel())}</a>
            </div>
        `
        : `
            <div class="topbar-actions">
                <a class="ghost-btn" href="${escapeHtml(buildServiceHref())}" data-link>Explore stores</a>
                <a class="btn is-accent" href="${escapeHtml(buildLoginHref(currentServiceLocation()))}" data-link>Sign in</a>
            </div>
        `;

    return `
        <section class="topbar">
            <div>
                <span class="eyebrow">${escapeHtml(meta.eyebrow)}</span>
                <h1 class="headline">${escapeHtml(meta.title)}</h1>
                <p class="muted">${escapeHtml(meta.description)}</p>
            </div>
            <div>
                <p class="muted">${escapeHtml(state.bootstrap.systemTime || "")}</p>
                ${actionMarkup}
            </div>
        </section>
    `;
}

function renderView() {
    if (state.page.status === "loading") {
        return `
            <section class="view-surface">
                <div class="service-loading">LOADING SERVICE DATA</div>
            </section>
        `;
    }

    if (state.page.status === "error") {
        return `
            <section class="view-surface">
                <div class="empty-state">
                    <strong>Something went wrong.</strong>
                    <p>${escapeHtml(state.page.error || "Unable to load this view right now.")}</p>
                </div>
                <div class="button-row">
                    <button class="btn" type="button" data-action="retry">Retry</button>
                </div>
            </section>
        `;
    }

    if (state.route.name === "login") {
        return renderLoginView();
    }
    if (state.route.name === "store") {
        return renderStoreDetailView(state.page.data);
    }
    if (state.route.name === "dashboard") {
        return renderDashboardView(state.page.data);
    }
    if (state.route.name === "orders") {
        return renderOrdersView(state.page.data);
    }
    if (state.route.name === "wallet") {
        return renderWalletView(state.page.data);
    }
    if (state.route.name === "chats") {
        return renderChatsView(state.page.data);
    }
    if (state.route.name === "chat_thread") {
        return renderChatThreadView(state.page.data);
    }
    if (state.route.name === "admin_users") {
        return renderAdminUsersView(state.page.data);
    }
    if (state.route.name === "admin_orders") {
        return renderAdminOrdersView(state.page.data);
    }
    return renderDiscoveryView(state.page.data);
}

function renderLoginView() {
    if (state.session) {
        return `
            <section class="view-surface auth-card">
                <div class="section-title">
                    <h2>Already signed in</h2>
                </div>
                <p class="muted">
                    You are signed in as ${escapeHtml(state.session.displayName || state.session.username)}.
                </p>
                <div class="button-row">
                    <a class="btn" href="${escapeHtml(state.session.dashboardPath || buildServiceHref("dashboard"))}" data-link>Go to dashboard</a>
                    <button class="ghost-btn" type="button" data-action="logout">Sign out</button>
                </div>
            </section>
        `;
    }

    return `
        <section class="view-surface auth-card">
            <div class="section-title">
                <h2>Sign in to continue</h2>
            </div>
            <p class="muted">Use your existing GameBuddy account. The service frontend will continue through JSON APIs only.</p>
            <form class="form-grid" data-form="login">
                <label>
                    Username, email, or phone
                    <input name="identifier" autocomplete="username" placeholder="Enter your account identifier" required>
                </label>
                <label>
                    Password
                    <input name="password" type="password" autocomplete="current-password" placeholder="Enter your password" required>
                </label>
                <div class="button-row">
                    <button class="btn is-accent" type="submit">Sign in</button>
                    <a class="ghost-btn" href="${escapeHtml(buildServiceHref())}" data-link>Back to stores</a>
                </div>
            </form>
        </section>
    `;
}

function renderDiscoveryView(data) {
    const filters = {
        ...DEFAULT_FILTERS,
        ...(data.filters || {}),
    };
    const stores = data.stores || [];
    const featured = data.featured || [];
    const games = state.bootstrap.constants?.discoveryGames || [];

    return `
        <div class="page-grid">
            <div class="hero-grid">
                <section class="view-surface">
                    <div class="section-title">
                        <h2>Public store discovery</h2>
                        <span class="badge">${escapeHtml(`${stores.length} stores`)}</span>
                    </div>
                    <p class="muted">This page is now rendered by the separated frontend shell and pulls all catalog data from `/api/stores`.</p>
                    <form class="form-grid" data-form="discovery-filters">
                        <div class="form-grid two">
                            <label>
                                Keyword
                                <input name="q" value="${escapeHtml(filters.q)}" placeholder="Search name, city, game, or tagline">
                            </label>
                            <label>
                                Game
                                <select name="game">
                                    <option value="">All games</option>
                                    ${games
                                        .map((game) => `<option value="${escapeHtml(game)}"${filters.game === game ? " selected" : ""}>${escapeHtml(game)}</option>`)
                                        .join("")}
                                </select>
                            </label>
                        </div>
                        <div class="form-grid two">
                            <label>
                                Max price
                                <input name="max_price" type="number" min="0" step="1" value="${escapeHtml(filters.max_price)}" placeholder="Optional ceiling">
                            </label>
                            <label>
                                Sort
                                <select name="sort">
                                    ${renderOption("recommended", filters.sort, "Recommended")}
                                    ${renderOption("rating_desc", filters.sort, "Highest rating")}
                                    ${renderOption("price_asc", filters.sort, "Lowest price")}
                                </select>
                            </label>
                        </div>
                        <div class="button-row">
                            <button class="btn" type="submit">Apply filters</button>
                            <a class="ghost-btn" href="${escapeHtml(buildServiceHref())}" data-link>Clear</a>
                        </div>
                    </form>
                </section>
                <section class="view-surface">
                    <div class="section-title">
                        <h2>Snapshot</h2>
                    </div>
                    <div class="summary-grid">
                        ${renderMetricCard("Featured", featured.length)}
                        ${renderMetricCard("Games", games.length)}
                        ${renderMetricCard("Live session", state.session ? "Yes" : "Guest")}
                    </div>
                    <div class="panel">
                        <h3>What is separated now</h3>
                        <p class="muted">Routing, discovery, store detail, login, dashboard, orders, and store order creation all run through the new service-facing frontend and API layer.</p>
                    </div>
                </section>
            </div>
            <section class="view-surface">
                <div class="section-title">
                    <h2>Featured stores</h2>
                </div>
                ${featured.length ? `<div class="card-grid">${featured.map((store) => renderStoreCard(store)).join("")}</div>` : renderEmptyState("No featured stores are available right now.")}
            </section>
            <section class="view-surface">
                <div class="section-title">
                    <h2>All available stores</h2>
                </div>
                ${stores.length ? `<div class="card-grid">${stores.map((store) => renderStoreCard(store)).join("")}</div>` : renderEmptyState("No public stores matched the current filters.")}
            </section>
        </div>
    `;
}

function renderStoreDetailView(data) {
    const store = data.store || null;
    if (!store) {
        return `
            <section class="view-surface">
                ${renderEmptyState("This store is not publicly available.")}
            </section>
        `;
    }

    const boosters = store.boosters || [];
    const serviceTypeOptions = data.serviceTypeOptions || [];
    const playerReady = Boolean(state.session && state.session.role === "player");
    const signInHref = buildLoginHref(currentServiceLocation());

    return `
        <div class="page-grid">
            <div class="hero-grid">
                <section class="view-surface">
                    <div class="badge-row">
                        ${renderBadge(store.reviewLabel || "Public")}
                        ${store.badge ? renderBadge(store.badge, "accent") : ""}
                        ${store.city ? renderBadge(store.city) : ""}
                    </div>
                    <h2>${escapeHtml(store.name)}</h2>
                    <p class="muted">${escapeHtml(store.tagline || store.heroText || store.description || "Store-managed service flow with structured dispatching.")}</p>
                    <div class="summary-grid">
                        ${renderMetricCard("Starting price", store.priceText || "--")}
                        ${renderMetricCard("Boosters", store.boosterCount || 0)}
                        ${renderMetricCard("Completed", store.completedOrders || 0)}
                        ${renderMetricCard("Rating", store.avgRating ?? "--")}
                    </div>
                    <div class="panel">
                        <h3>Store details</h3>
                        <div class="store-meta">
                            <span>Games: ${escapeHtml(store.gamesText || "Not provided")}</span>
                            <span>Owner: ${escapeHtml(store.ownerDisplayName || store.name)}</span>
                            <span>Contact note: ${escapeHtml(store.contactNote || "Use order flow or chat after assignment.")}</span>
                        </div>
                    </div>
                </section>
                <section class="view-surface">
                    <div class="section-title">
                        <h2>Create store order</h2>
                    </div>
                    ${renderOrderComposer({
                        store,
                        boosters,
                        serviceTypeOptions,
                        playerReady,
                        signInHref,
                    })}
                </section>
            </div>
            <section class="view-surface">
                <div class="section-title">
                    <h2>Available boosters</h2>
                </div>
                ${boosters.length ? `<div class="card-grid">${boosters.map((booster) => renderBoosterCard(booster)).join("")}</div>` : renderEmptyState("This store does not have public booster cards yet.")}
            </section>
        </div>
    `;
}

function renderOrderComposer({ store, boosters, serviceTypeOptions, playerReady, signInHref }) {
    if (!playerReady) {
        if (!state.session) {
            return `
                <div class="empty-state">
                    Sign in with a player account to place an order in the new service frontend.
                </div>
                <div class="button-row">
                    <a class="btn is-accent" href="${escapeHtml(signInHref)}" data-link>Sign in as player</a>
                </div>
            `;
        }
        return `
            <div class="empty-state">
                Current role: ${escapeHtml(state.session.roleLabel || state.session.role || "")}. Only player accounts can submit new store orders here.
            </div>
        `;
    }

    if (!boosters.length) {
        return renderEmptyState("This store currently has no booster profile available for direct ordering.");
    }

    return `
        <form class="form-grid" data-form="store-order" data-store-slug="${escapeHtml(store.slug)}">
            <label>
                Assigned booster
                <select name="selected_booster" required>
                    ${boosters
                        .map((booster, index) => {
                            const label = `${booster.displayName || booster.username} | ${booster.profile?.rank || "Rank pending"} | ${booster.profile?.price || "Quote pending"}`;
                            return `<option value="${escapeHtml(booster.username)}"${index === 0 ? " selected" : ""}>${escapeHtml(label)}</option>`;
                        })
                        .join("")}
                </select>
            </label>
            <div class="form-grid two">
                <label>
                    Game
                    <select name="game" required>
                        ${(store.games || [])
                            .map((game, index) => `<option value="${escapeHtml(game)}"${index === 0 ? " selected" : ""}>${escapeHtml(game)}</option>`)
                            .join("")}
                    </select>
                </label>
                <label>
                    Service type
                    <select name="service_type" required>
                        ${serviceTypeOptions.map((option, index) => `<option value="${escapeHtml(option)}"${index === 0 ? " selected" : ""}>${escapeHtml(option)}</option>`).join("")}
                    </select>
                </label>
            </div>
            <div class="form-grid two">
                <label>
                    Start mode
                    <select name="start_time_mode">
                        <option value="custom" selected>Schedule manually</option>
                        <option value="now">Start now</option>
                    </select>
                </label>
                <label>
                    Order hours
                    <input name="order_hours" type="number" min="0.5" step="0.5" value="1.0" required>
                </label>
            </div>
            <div class="form-grid two">
                <label>
                    Preferred start time
                    <input name="start_time" type="datetime-local">
                </label>
                <label>
                    Target rank
                    <input name="target_rank" placeholder="Optional target rank">
                </label>
            </div>
            <label>
                Payment
                <select name="payment_method">
                    <option value="stripe" selected>Stripe checkout</option>
                    <option value="buddy_coin">Buddy coin</option>
                </select>
            </label>
            <label>
                Order details
                <textarea name="detail" placeholder="Describe the game mode, goal, and any schedule constraints." required></textarea>
            </label>
            <div class="button-row">
                <button class="btn is-accent" type="submit">Create order</button>
                <a class="ghost-btn" href="${escapeHtml(buildServiceHref("orders"))}" data-link>View my orders</a>
            </div>
        </form>
    `;
}

function renderDashboardView(data) {
    const role = data.role || state.session?.role || "player";
    const metrics = renderRoleMetrics(role, data.stats || {});
    const panels = [];

    if (role === "player") {
        panels.push(renderStoresSection("Recommended stores", data.recommendedStores || []));
        panels.push(renderOrdersSection("Recent orders", data.orders || []));
        panels.push(renderNotificationsSection("Notifications", data.notifications || []));
    } else if (role === "booster") {
        panels.push(
            renderSummaryPanel(
                "Booster profile",
                `
                    <div class="summary-grid">
                        ${renderMetricCard("Profile completion", `${data.profileCompletion || 0}%`)}
                        ${renderMetricCard("Store linked", data.store?.name || "Not linked")}
                    </div>
                `
            )
        );
        panels.push(renderOrdersSection("Recent assigned orders", data.orders || []));
        panels.push(renderNotificationsSection("Notifications", data.notifications || []));
    } else if (role === "merchant") {
        panels.push(
            renderSummaryPanel(
                "Store overview",
                data.store
                    ? `<div class="card-grid">${renderStoreCard(data.store)}</div>`
                    : renderEmptyState("No store has been attached to this merchant account yet.")
            )
        );
        panels.push(renderOrdersSection("Store orders", data.orders || []));
        panels.push(renderApplicationsSection("Pending talent applications", data.pendingApplications || []));
        panels.push(renderNotificationsSection("Notifications", data.notifications || []));
    } else {
        panels.push(renderBoostersSection("Top boosters", data.topBoosters || []));
        panels.push(renderOrdersSection("Complaint queue", data.complaints || []));
        panels.push(renderOrdersSection("Recent platform orders", data.orders || []));
    }

    return `
        <div class="page-grid">
            <section class="view-surface">
                <div class="section-title">
                    <h2>${escapeHtml((state.session?.roleLabel || role || "Service").toString())} dashboard</h2>
                    <span class="badge">/api/dashboard</span>
                </div>
                <div class="kpi-grid">${metrics}</div>
            </section>
            ${panels.join("")}
        </div>
    `;
}

function renderOrdersView(data) {
    const orders = data.orders || [];
    const summary = summarizeOrders(orders);

    return `
        <div class="page-grid">
            <section class="view-surface">
                <div class="section-title">
                    <h2>Order center</h2>
                    <span class="badge">${escapeHtml(`${orders.length} orders`)}</span>
                </div>
                <div class="summary-grid">
                    ${renderMetricCard("Total", summary.total)}
                    ${renderMetricCard("Active", summary.active)}
                    ${renderMetricCard("Completed", summary.completed)}
                    ${renderMetricCard("Complaints", summary.complaints)}
                </div>
            </section>
            ${renderOrdersSection("All orders", orders)}
        </div>
    `;
}

function renderWalletView(data) {
    const wallet = data.wallet || {};
    const transactions = data.transactions || [];
    const role = data.role || state.session?.role || "";
    const actionPanel = role === "player"
        ? `
            <section class="view-surface">
                <div class="section-title">
                    <h2>Recharge</h2>
                </div>
                <form class="form-grid" data-form="wallet-recharge">
                    <label>
                        Recharge amount
                        <input name="amount" type="number" min="1" step="1" placeholder="Example: 100" required>
                    </label>
                    <div class="button-row">
                        <button class="btn is-accent" type="submit">Recharge with Stripe</button>
                    </div>
                </form>
            </section>
        `
        : `
            <section class="view-surface">
                <div class="section-title">
                    <h2>Withdraw</h2>
                </div>
                <form class="form-grid" data-form="wallet-withdraw">
                    <label>
                        Withdrawal amount
                        <input name="amount" type="number" min="1" step="1" placeholder="Example: 100" required>
                    </label>
                    <div class="button-row">
                        <button class="btn is-accent" type="submit">Submit withdrawal</button>
                    </div>
                </form>
            </section>
        `;

    return `
        <div class="page-grid">
            <section class="view-surface">
                <div class="section-title">
                    <h2>Buddy Coin wallet</h2>
                    <span class="badge">/api/wallet</span>
                </div>
                <div class="summary-grid">
                    ${renderMetricCard("Balance", wallet.balance || 0)}
                    ${renderMetricCard("Locked", wallet.locked || 0)}
                    ${renderMetricCard("Available", wallet.available || 0)}
                    ${renderMetricCard("Withdraw rate", data.withdrawRate || 0)}
                </div>
            </section>
            <div class="hero-grid">
                ${actionPanel}
                <section class="view-surface">
                    <div class="section-title">
                        <h2>Wallet rules</h2>
                    </div>
                    <div class="list-stack">
                        <article class="note-card">Player recharge rate: 1 real-money unit = ${escapeHtml(formatNumber(data.coinToCashRate || 0))} buddy coin.</article>
                        <article class="note-card">Withdrawal rate: 1 buddy coin = ${escapeHtml(formatNumber(data.withdrawRate || 0))} real-money unit.</article>
                        <article class="note-card">Completed order revenue share for boosters: ${escapeHtml(formatPercent((data.shareRate || 0) * 100))}.</article>
                    </div>
                </section>
            </div>
            <section class="view-surface">
                <div class="section-title">
                    <h2>Transaction history</h2>
                    <span class="badge">${escapeHtml(`${transactions.length} records`)}</span>
                </div>
                ${
                    transactions.length
                        ? `<div class="list-stack">${transactions.map((item) => renderWalletTransactionCard(item)).join("")}</div>`
                        : renderEmptyState("No wallet transactions yet.")
                }
            </section>
        </div>
    `;
}

function renderChatsView(data) {
    const conversations = data.conversations || [];
    const notifications = data.notifications || [];
    return `
        <div class="page-grid">
            <section class="view-surface">
                <div class="section-title">
                    <h2>Message center</h2>
                    <span class="badge">${escapeHtml(`${conversations.length} conversations`)}</span>
                </div>
                ${
                    conversations.length
                        ? `<div class="list-stack">${conversations.map((item) => renderConversationCard(item)).join("")}</div>`
                        : renderEmptyState("No active conversations yet.")
                }
            </section>
            <section class="view-surface">
                <div class="section-title">
                    <h2>Recent notifications</h2>
                </div>
                ${
                    notifications.length
                        ? `<div class="list-stack">${notifications.map((item) => renderNotificationCard(item)).join("")}</div>`
                        : renderEmptyState("No notifications yet.")
                }
            </section>
        </div>
    `;
}

function renderChatThreadView(data) {
    const messages = data.messages || [];
    const partner = data.partner || {};
    return `
        <div class="page-grid">
            <section class="view-surface">
                <div class="section-title">
                    <h2>Chat with ${escapeHtml(partner.displayName || partner.username || "partner")}</h2>
                    <a class="ghost-btn" href="${escapeHtml(buildServiceHref("chats"))}" data-link>Back to chats</a>
                </div>
                ${
                    messages.length
                        ? `<div class="list-stack">${messages.map((item) => renderChatMessageCard(item)).join("")}</div>`
                        : renderEmptyState("No messages yet. Start the conversation below.")
                }
            </section>
            <section class="view-surface">
                <div class="section-title">
                    <h2>Send message</h2>
                </div>
                <form class="form-grid" data-form="chat-send" data-partner="${escapeHtml(partner.username || "")}">
                    <label>
                        Message
                        <textarea name="message" placeholder="Type your message here." required></textarea>
                    </label>
                    <div class="button-row">
                        <button class="btn is-accent" type="submit">Send</button>
                    </div>
                </form>
            </section>
        </div>
    `;
}

function renderAdminUsersView(data) {
    return `
        <div class="page-grid">
            <section class="view-surface">
                <div class="section-title">
                    <h2>Admin governance</h2>
                    <span class="badge">/api/admin/users</span>
                </div>
                <div class="summary-grid">
                    ${renderMetricCard("Accounts", data.users?.length || 0)}
                    ${renderMetricCard("Pending stores", data.pendingStoreApplications?.length || 0)}
                    ${renderMetricCard("Pending boosters", data.pendingBoosterApplications?.length || 0)}
                    ${renderMetricCard("Pending merchants", data.pendingMerchantApplications?.length || 0)}
                </div>
            </section>
            ${renderAdminStoreSection("Pending store applications", data.pendingStoreApplications || [], true)}
            ${renderAdminBoosterSection("Pending booster applications", data.pendingBoosterApplications || [], true)}
            ${renderAdminMerchantSection("Pending merchant applications", data.pendingMerchantApplications || [], true)}
            ${renderAdminStoreSection("Recent reviewed stores", data.reviewedStoreApplications || [], false)}
            ${renderAdminBoosterSection("Recent reviewed boosters", data.reviewedBoosterApplications || [], false)}
            ${renderAdminMerchantSection("Recent reviewed merchants", data.reviewedMerchantApplications || [], false)}
            ${renderAdminUserListSection(data.users || [])}
        </div>
    `;
}

function renderAdminOrdersView(data) {
    const filters = data.filters || {};
    const orders = data.orders || [];
    return `
        <div class="page-grid">
            <section class="view-surface">
                <div class="section-title">
                    <h2>Admin order governance</h2>
                    <span class="badge">${escapeHtml(`${orders.length} orders`)}</span>
                </div>
                <form class="form-grid" data-form="admin-order-filters">
                    <div class="form-grid two">
                        <label>
                            Keyword
                            <input name="keyword" value="${escapeHtml(filters.keyword || "")}" placeholder="Player, booster, or game">
                        </label>
                        <label>
                            Status
                            <select name="status">
                                <option value="">All statuses</option>
                                ${(data.orderStatusOptions || []).map((option) => renderOption(option, filters.status || "", option)).join("")}
                            </select>
                        </label>
                    </div>
                    <div class="form-grid two">
                        <label>
                            Complaint status
                            <select name="complaint">
                                <option value="">All complaints</option>
                                ${(data.complaintStatusOptions || []).map((option) => renderOption(option, filters.complaint || "", option)).join("")}
                            </select>
                        </label>
                        <div class="button-row" style="align-self:end;">
                            <button class="btn" type="submit">Apply filters</button>
                            <a class="ghost-btn" href="${escapeHtml(buildServiceHref("admin/orders"))}" data-link>Clear</a>
                        </div>
                    </div>
                </form>
            </section>
            <section class="view-surface">
                <div class="section-title">
                    <h2>Order queue</h2>
                </div>
                ${
                    orders.length
                        ? `<div class="list-stack">${orders.map((order) => renderAdminOrderCard(order, data.complaintStatusOptions || [])).join("")}</div>`
                        : renderEmptyState("No orders matched the current filters.")
                }
            </section>
        </div>
    `;
}

function renderStoresSection(title, stores) {
    return `
        <section class="view-surface">
            <div class="section-title">
                <h2>${escapeHtml(title)}</h2>
            </div>
            ${stores.length ? `<div class="card-grid">${stores.map((store) => renderStoreCard(store)).join("")}</div>` : renderEmptyState("Nothing to show here yet.")}
        </section>
    `;
}

function renderBoostersSection(title, boosters) {
    return `
        <section class="view-surface">
            <div class="section-title">
                <h2>${escapeHtml(title)}</h2>
            </div>
            ${boosters.length ? `<div class="card-grid">${boosters.map((booster) => renderBoosterCard(booster)).join("")}</div>` : renderEmptyState("No booster snapshot is available right now.")}
        </section>
    `;
}

function renderOrdersSection(title, orders) {
    return `
        <section class="view-surface">
            <div class="section-title">
                <h2>${escapeHtml(title)}</h2>
            </div>
            ${orders.length ? `<div class="order-grid">${orders.map((order) => renderOrderCard(order)).join("")}</div>` : renderEmptyState("No orders are available in this view.")}
        </section>
    `;
}

function renderNotificationsSection(title, notifications) {
    return `
        <section class="view-surface">
            <div class="section-title">
                <h2>${escapeHtml(title)}</h2>
            </div>
            ${
                notifications.length
                    ? `<div class="list-stack">${notifications.map((item) => renderNotificationCard(item)).join("")}</div>`
                    : renderEmptyState("No notifications yet.")
            }
        </section>
    `;
}

function renderApplicationsSection(title, applications) {
    return `
        <section class="view-surface">
            <div class="section-title">
                <h2>${escapeHtml(title)}</h2>
            </div>
            ${
                applications.length
                    ? `<div class="list-stack">${applications.map((item) => renderApplicationCard(item)).join("")}</div>`
                    : renderEmptyState("No pending talent applications.")
            }
        </section>
    `;
}

function renderSummaryPanel(title, content) {
    return `
        <section class="view-surface">
            <div class="section-title">
                <h2>${escapeHtml(title)}</h2>
            </div>
            ${content}
        </section>
    `;
}

function renderStoreCard(store) {
    return `
        <article class="store-card">
            <div class="badge-row">
                ${renderBadge(store.reviewLabel || "Open")}
                ${store.badge ? renderBadge(store.badge, "accent") : ""}
            </div>
            <div>
                <h3>${escapeHtml(store.name || "Unnamed store")}</h3>
                <p class="muted">${escapeHtml(store.tagline || store.description || "Store-managed service with dispatch support.")}</p>
            </div>
            <div class="store-meta">
                <span>Games: ${escapeHtml(store.gamesText || "Pending")}</span>
                <span>City: ${escapeHtml(store.city || "Unknown")}</span>
                <span>Starting price: ${escapeHtml(store.priceText || "--")}</span>
                <span>Boosters: ${escapeHtml(String(store.boosterCount || 0))}</span>
                <span>Rating: ${escapeHtml(String(store.avgRating ?? "--"))}</span>
            </div>
            <div class="button-row">
                <a class="btn" href="${escapeHtml(buildServiceHref(`stores/${store.slug}`))}" data-link>Open store</a>
            </div>
        </article>
    `;
}

function renderBoosterCard(booster) {
    const profile = booster.profile || {};
    return `
        <article class="booster-card">
            <div class="badge-row">
                ${profile.badge ? renderBadge(profile.badge) : renderBadge("Booster")}
                ${profile.statusText ? renderBadge(profile.statusText, "accent") : ""}
            </div>
            <div>
                <h3>${escapeHtml(booster.displayName || booster.username || "Booster")}</h3>
                <p class="muted">${escapeHtml(profile.intro || profile.games || profile.playStyle || "Profile details are still being expanded.")}</p>
            </div>
            <div class="booster-meta">
                <span>Games: ${escapeHtml(profile.games || "Pending")}</span>
                <span>Rank: ${escapeHtml(profile.rank || "Pending")}</span>
                <span>Price: ${escapeHtml(profile.price || "--")}</span>
                <span>Completion: ${escapeHtml(formatPercent(booster.stats?.completionRate || 0))}</span>
                <span>Rating: ${escapeHtml(String(booster.stats?.avgRating ?? "--"))}</span>
            </div>
        </article>
    `;
}

function renderOrderCard(order) {
    const storeLink = order.store?.slug ? buildServiceHref(`stores/${order.store.slug}`) : "";
    return `
        <article class="order-card">
            <div class="badge-row">
                ${renderBadge(order.status || "Order")}
                ${order.paymentStatus ? renderBadge(order.paymentStatus, badgeTone(order.paymentStatus)) : ""}
                ${order.complaintStatus && order.complaintStatus !== STATUS_NO_COMPLAINT ? renderBadge(order.complaintStatus, badgeTone(order.complaintStatus)) : ""}
            </div>
            <div>
                <h3>#${escapeHtml(String(order.id || "--"))} ${escapeHtml(order.game || "Game order")}</h3>
                <p class="muted">${escapeHtml(order.detail || "No description provided.")}</p>
            </div>
            <div class="order-meta">
                <span>Store: ${storeLink ? `<a href="${escapeHtml(storeLink)}" data-link>${escapeHtml(order.storeLabel || order.store?.name || "--")}</a>` : escapeHtml(order.storeLabel || "--")}</span>
                <span>Player: ${escapeHtml(order.player || "--")}</span>
                <span>Booster: ${escapeHtml(order.assignedBoosterName || order.boosterLabel || order.booster || "--")}</span>
                <span>Service: ${escapeHtml(order.serviceType || "--")}</span>
                <span>Time: ${escapeHtml(order.preferredTime || "--")}</span>
                <span>Duration: ${escapeHtml(order.duration || "--")}</span>
                <span>Price: ${escapeHtml(order.price || "--")}</span>
                <span>Created: ${escapeHtml(order.createdAt || "--")}</span>
            </div>
        </article>
    `;
}

function renderNotificationCard(notification) {
    return `
        <article class="note-card">
            <div class="badge-row">
                ${notification.type ? renderBadge(notification.type, "accent") : renderBadge("Notification")}
            </div>
            <p>${escapeHtml(notification.message || "")}</p>
            <p class="muted">From ${escapeHtml(notification.sender || "system")} at ${escapeHtml(notification.timestamp || "--")}</p>
        </article>
    `;
}

function renderApplicationCard(application) {
    return `
        <article class="note-card">
            <strong>${escapeHtml(application.displayName || application.username || "Applicant")}</strong>
            <p class="muted">Username: ${escapeHtml(application.username || "--")}</p>
            <p class="muted">Game account: ${escapeHtml(application.gameAccount || "--")}</p>
            <p class="muted">Submitted: ${escapeHtml(application.createdAt || "--")}</p>
        </article>
    `;
}

function renderWalletTransactionCard(transaction) {
    const tone = (transaction.coinAmount || 0) >= 0 ? "accent" : "danger";
    return `
        <article class="note-card">
            <div class="section-title">
                <h3>${escapeHtml(transaction.type || "Transaction")}</h3>
                ${renderBadge(formatSignedNumber(transaction.coinAmount || 0), tone)}
            </div>
            <p class="muted">${escapeHtml(transaction.note || "No note")}</p>
            <p class="muted">Created: ${escapeHtml(transaction.createdAt || "--")}</p>
            ${transaction.relatedOrderId ? `<p class="muted">Order #${escapeHtml(String(transaction.relatedOrderId))}</p>` : ""}
            ${transaction.cashAmount ? `<p class="muted">Cash equivalent: ${escapeHtml(formatNumber(transaction.cashAmount))}</p>` : ""}
        </article>
    `;
}

function renderConversationCard(conversation) {
    return `
        <article class="note-card">
            <div class="section-title">
                <h3>${escapeHtml(conversation.partnerLabel || conversation.partner || "Conversation")}</h3>
                <span class="muted">${escapeHtml(conversation.timestamp || "--")}</span>
            </div>
            <p>${escapeHtml(conversation.lastMessage || "")}</p>
            <div class="button-row">
                <a class="btn" href="${escapeHtml(buildServiceHref(`chats/${conversation.partner}`))}" data-link>Open thread</a>
                ${conversation.partnerStoreSlug ? `<a class="ghost-btn" href="${escapeHtml(buildServiceHref(`stores/${conversation.partnerStoreSlug}`))}" data-link>Open store</a>` : ""}
            </div>
        </article>
    `;
}

function renderChatMessageCard(message) {
    const isMine = message.sender === state.session?.username;
    return `
        <article class="note-card">
            <div class="section-title">
                <h3>${escapeHtml(isMine ? "You" : message.sender || "Partner")}</h3>
                <span class="muted">${escapeHtml(message.timestamp || "--")}</span>
            </div>
            <p>${escapeHtml(message.message || "")}</p>
        </article>
    `;
}

function renderAdminStoreSection(title, stores, interactive) {
    return `
        <section class="view-surface">
            <div class="section-title">
                <h2>${escapeHtml(title)}</h2>
            </div>
            ${
                stores.length
                    ? `<div class="list-stack">${stores.map((item) => renderAdminStoreCard(item, interactive)).join("")}</div>`
                    : renderEmptyState("Nothing to review here.")
            }
        </section>
    `;
}

function renderAdminBoosterSection(title, applications, interactive) {
    return `
        <section class="view-surface">
            <div class="section-title">
                <h2>${escapeHtml(title)}</h2>
            </div>
            ${
                applications.length
                    ? `<div class="list-stack">${applications.map((item) => renderAdminBoosterApplicationCard(item, interactive)).join("")}</div>`
                    : renderEmptyState("Nothing to review here.")
            }
        </section>
    `;
}

function renderAdminMerchantSection(title, applications, interactive) {
    return `
        <section class="view-surface">
            <div class="section-title">
                <h2>${escapeHtml(title)}</h2>
            </div>
            ${
                applications.length
                    ? `<div class="list-stack">${applications.map((item) => renderAdminMerchantApplicationCard(item, interactive)).join("")}</div>`
                    : renderEmptyState("Nothing to review here.")
            }
        </section>
    `;
}

function renderAdminStoreCard(store, interactive) {
    return `
        <article class="note-card">
            <div class="section-title">
                <h3>${escapeHtml(store.name || "Store")}</h3>
                ${renderBadge(store.reviewLabel || "Pending", badgeTone(store.reviewLabel || ""))}
            </div>
            <p class="muted">${escapeHtml(store.gamesText || "No games listed")} | ${escapeHtml(store.ownerDisplayName || store.name || "")}</p>
            <p>${escapeHtml(store.description || store.tagline || "No description provided.")}</p>
            ${
                interactive
                    ? `
                        <form class="form-grid" data-form="admin-store-review">
                            <input type="hidden" name="store_id" value="${escapeHtml(String(store.id || ""))}">
                            <label>
                                Review note
                                <input name="review_note" placeholder="Optional note for the store owner">
                            </label>
                            <div class="button-row">
                                <button class="btn" type="submit" name="action" value="approve_store">Approve</button>
                                <button class="ghost-btn" type="submit" name="action" value="reject_store">Reject</button>
                            </div>
                        </form>
                    `
                    : ""
            }
        </article>
    `;
}

function renderAdminBoosterApplicationCard(application, interactive) {
    return `
        <article class="note-card">
            <div class="section-title">
                <h3>${escapeHtml(application.displayName || application.username || "Booster application")}</h3>
                ${renderBadge(application.status || "Pending", badgeTone(application.status || ""))}
            </div>
            <p class="muted">${escapeHtml(application.storeName || "No assigned store")} | ${escapeHtml(application.gameAccount || "No game account")}</p>
            <p class="muted">${escapeHtml(application.email || "No email")} ${application.phone ? `| ${escapeHtml(application.phone)}` : ""}</p>
            ${application.reviewNote ? `<p>${escapeHtml(application.reviewNote)}</p>` : ""}
            ${
                interactive
                    ? `
                        <form class="form-grid" data-form="admin-booster-review">
                            <input type="hidden" name="application_id" value="${escapeHtml(String(application.id || ""))}">
                            <label>
                                Review note
                                <input name="review_note" placeholder="Optional note for the applicant">
                            </label>
                            <div class="button-row">
                                <button class="btn" type="submit" name="action" value="approve_booster_application">Approve</button>
                                <button class="ghost-btn" type="submit" name="action" value="reject_booster_application">Reject</button>
                            </div>
                        </form>
                    `
                    : ""
            }
        </article>
    `;
}

function renderAdminMerchantApplicationCard(application, interactive) {
    return `
        <article class="note-card">
            <div class="section-title">
                <h3>${escapeHtml(application.username || "Merchant application")}</h3>
                ${renderBadge(application.status || "Pending", badgeTone(application.status || ""))}
            </div>
            <p class="muted">${escapeHtml(application.storeName || "No store name")} ${application.storeCity ? `| ${escapeHtml(application.storeCity)}` : ""}</p>
            <p class="muted">${escapeHtml(application.email || "No email")} ${application.phone ? `| ${escapeHtml(application.phone)}` : ""}</p>
            ${application.reviewNote ? `<p>${escapeHtml(application.reviewNote)}</p>` : ""}
            ${
                interactive
                    ? `
                        <form class="form-grid" data-form="admin-merchant-review">
                            <input type="hidden" name="merchant_application_id" value="${escapeHtml(String(application.id || ""))}">
                            <label>
                                Review note
                                <input name="review_note" placeholder="Optional note for the applicant">
                            </label>
                            <div class="button-row">
                                <button class="btn" type="submit" name="action" value="approve_merchant_application">Approve</button>
                                <button class="ghost-btn" type="submit" name="action" value="reject_merchant_application">Reject</button>
                            </div>
                        </form>
                    `
                    : ""
            }
        </article>
    `;
}

function renderAdminUserListSection(users) {
    return `
        <section class="view-surface">
            <div class="section-title">
                <h2>Platform accounts</h2>
            </div>
            ${
                users.length
                    ? `<div class="list-stack">${users.map((item) => renderAdminUserCard(item)).join("")}</div>`
                    : renderEmptyState("No accounts found.")
            }
        </section>
    `;
}

function renderAdminUserCard(user) {
    const action = user.banned ? "unban" : "ban";
    const actionLabel = user.banned ? "Unban" : "Ban";
    return `
        <article class="note-card">
            <div class="section-title">
                <h3>${escapeHtml(user.displayName || user.username || "User")}</h3>
                ${renderBadge(user.banned ? "Banned" : "Active", user.banned ? "danger" : "accent")}
            </div>
            <p class="muted">${escapeHtml(user.roleLabel || user.role || "")} | ${escapeHtml(user.username || "")}</p>
            <p class="muted">Failed logins: ${escapeHtml(String(user.failedLoginAttempts || 0))}</p>
            <div class="button-row">
                <form data-form="admin-user-action">
                    <input type="hidden" name="username" value="${escapeHtml(user.username || "")}">
                    <input type="hidden" name="action" value="${escapeHtml(action)}">
                    <button class="ghost-btn" type="submit">${escapeHtml(actionLabel)}</button>
                </form>
                <form data-form="admin-user-action">
                    <input type="hidden" name="username" value="${escapeHtml(user.username || "")}">
                    <input type="hidden" name="action" value="delete">
                    <button class="ghost-btn" type="submit">Delete</button>
                </form>
            </div>
            <form class="form-grid" data-form="admin-user-action">
                <input type="hidden" name="username" value="${escapeHtml(user.username || "")}">
                <input type="hidden" name="action" value="reset_password">
                <label>
                    Reset password
                    <input name="new_password" placeholder="Enter a new password">
                </label>
                <div class="button-row">
                    <button class="btn" type="submit">Reset password</button>
                </div>
            </form>
        </article>
    `;
}

function renderAdminOrderCard(order, complaintStatusOptions) {
    const complaintOptions = complaintStatusOptions.map((option) => renderOption(option, order.complaintStatus || "", option)).join("");
    return `
        <article class="note-card">
            <div class="section-title">
                <h3>#${escapeHtml(String(order.id || ""))} ${escapeHtml(order.player || "")} -> ${escapeHtml(order.booster || "")}</h3>
                <div class="badge-row">
                    ${renderBadge(order.status || "Order")}
                    ${renderBadge(order.paymentStatus || "Payment", badgeTone(order.paymentStatus || ""))}
                    ${renderBadge(order.complaintStatus || "Complaint", badgeTone(order.complaintStatus || ""))}
                </div>
            </div>
            <p class="muted">${escapeHtml(order.game || "")} | ${escapeHtml(order.serviceType || "Standard service")} | ${escapeHtml(order.price || "--")}</p>
            <p>${escapeHtml(order.detail || "No detail provided.")}</p>
            ${order.complaint ? `<p><strong>Complaint:</strong> ${escapeHtml(order.complaint)}</p>` : ""}
            <form class="form-grid" data-form="admin-order-action">
                <input type="hidden" name="order_id" value="${escapeHtml(String(order.id || ""))}">
                <div class="form-grid two">
                    <label>
                        Complaint status
                        <select name="complaint_status">
                            ${complaintOptions}
                        </select>
                    </label>
                    <label>
                        Admin note
                        <input name="admin_note" value="${escapeHtml(order.adminNote || "")}" placeholder="Internal note">
                    </label>
                </div>
                <label>
                    Complaint reply
                    <textarea name="complaint_reply" placeholder="Reply to the player and booster.">${escapeHtml(order.complaintReply || "")}</textarea>
                </label>
                <div class="button-row">
                    <button class="btn" type="submit" name="action" value="handle_complaint">Save complaint result</button>
                    <button class="ghost-btn" type="submit" name="action" value="mark_refunded">Mark refunded</button>
                </div>
            </form>
        </article>
    `;
}

function renderRoleMetrics(role, stats) {
    const definitions = ROLE_METRICS[role] || Object.keys(stats || {}).map((key) => [key, humanizeKey(key)]);
    return definitions
        .map(([key, label]) => renderMetricCard(label, formatMetricValue(key, stats?.[key])))
        .join("");
}

function renderMetricCard(label, value) {
    return `
        <article class="metric-card">
            <span class="muted">${escapeHtml(String(label))}</span>
            <strong>${escapeHtml(String(value))}</strong>
        </article>
    `;
}

function renderBadge(text, tone = "") {
    if (!text) {
        return "";
    }
    const className = tone ? `badge is-${tone}` : "badge";
    return `<span class="${className}">${escapeHtml(String(text))}</span>`;
}

function renderEmptyState(message) {
    return `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function renderToast() {
    if (!state.toast?.message) {
        return "";
    }
    return `<div class="toast">${escapeHtml(state.toast.message)}</div>`;
}

function renderOption(value, current, label) {
    return `<option value="${escapeHtml(value)}"${value === current ? " selected" : ""}>${escapeHtml(label)}</option>`;
}

function getViewMeta(route, data) {
    if (route.name === "login") {
        return {
            eyebrow: "Auth",
            title: "Service Sign In",
            description: "Session creation is handled through /api/auth/login.",
        };
    }
    if (route.name === "store") {
        return {
            eyebrow: "Store detail",
            title: data?.store?.name || "Store view",
            description: data?.store?.tagline || "Read a public store snapshot and create a structured order.",
        };
    }
    if (route.name === "dashboard") {
        return {
            eyebrow: "Dashboard",
            title: `${state.session?.displayName || state.session?.username || "Service"} workspace`,
            description: "Role-aware dashboard data comes from the API snapshot layer.",
        };
    }
    if (route.name === "orders") {
        return {
            eyebrow: "Orders",
            title: "Unified order center",
            description: "The separated frontend consumes order snapshots for every role through the API.",
        };
    }
    if (route.name === "wallet") {
        return {
            eyebrow: "Wallet",
            title: "Buddy Coin wallet",
            description: "Recharge and withdrawal actions now run through JSON APIs.",
        };
    }
    if (route.name === "chats" || route.name === "chat_thread") {
        return {
            eyebrow: "Chats",
            title: route.name === "chat_thread" ? "Conversation thread" : "Message center",
            description: "Conversation lists and thread messages are loaded from the API layer.",
        };
    }
    if (route.name === "admin_users") {
        return {
            eyebrow: "Admin",
            title: "User governance",
            description: "Store reviews, application reviews, and account actions now have service APIs.",
        };
    }
    if (route.name === "admin_orders") {
        return {
            eyebrow: "Admin",
            title: "Dispute and order governance",
            description: "Order filtering and complaint handling now run through the API layer.",
        };
    }
    return {
        eyebrow: "Storefront",
        title: "GameBuddy service discovery",
        description: "Public discovery is now served by the standalone service frontend shell.",
    };
}

function topbarPrimaryHref() {
    if (!state.session) {
        return buildServiceHref("dashboard");
    }
    if (state.session.role === "admin") {
        return buildServiceHref("admin/users");
    }
    if (state.session.role === "player" || state.session.role === "booster" || state.session.role === "merchant") {
        return buildServiceHref("chats");
    }
    return buildServiceHref("orders");
}

function topbarPrimaryLabel() {
    if (!state.session) {
        return "Dashboard";
    }
    if (state.session.role === "admin") {
        return "Governance";
    }
    if (state.session.role === "player" || state.session.role === "booster" || state.session.role === "merchant") {
        return "Chats";
    }
    return "Orders";
}

function parseRoute() {
    const pathname = (window.location.pathname || SERVICE_ROOT).replace(/\/+$/, "") || SERVICE_ROOT;
    const search = new URLSearchParams(window.location.search || "");
    const relativePath = pathname.startsWith(SERVICE_ROOT)
        ? pathname.slice(SERVICE_ROOT.length).replace(/^\/+/, "")
        : "";

    if (!relativePath) {
        return {
            name: "home",
            filters: {
                q: search.get("q") || "",
                game: search.get("game") || "",
                max_price: search.get("max_price") || "",
                sort: search.get("sort") || DEFAULT_FILTERS.sort,
            },
        };
    }

    if (relativePath === "login") {
        return {
            name: "login",
            next: search.get("next") || "",
        };
    }

    if (relativePath === "dashboard") {
        return { name: "dashboard" };
    }

    if (relativePath === "orders") {
        return { name: "orders" };
    }

    if (relativePath === "wallet") {
        return { name: "wallet" };
    }

    if (relativePath === "chats") {
        return { name: "chats" };
    }

    if (relativePath.startsWith("chats/")) {
        return {
            name: "chat_thread",
            partner: decodeURIComponent(relativePath.slice("chats/".length)),
        };
    }

    if (relativePath === "admin/users") {
        return { name: "admin_users" };
    }

    if (relativePath === "admin/orders") {
        return {
            name: "admin_orders",
            filters: {
                keyword: search.get("keyword") || "",
                status: search.get("status") || "",
                complaint: search.get("complaint") || "",
            },
        };
    }

    if (relativePath.startsWith("stores/")) {
        return {
            name: "store",
            slug: decodeURIComponent(relativePath.slice("stores/".length)),
        };
    }

    return {
        name: "home",
        filters: { ...DEFAULT_FILTERS },
    };
}

function routeRequiresAuth(route) {
    return ["dashboard", "orders", "wallet", "chats", "chat_thread", "admin_users", "admin_orders"].includes(route.name);
}

function navigate(target, { replace = false } = {}) {
    const href = sanitizeNextPath(target || buildServiceHref());
    if (href === currentServiceLocation()) {
        syncRoute();
        return;
    }
    window.history[replace ? "replaceState" : "pushState"]({}, "", href);
    syncRoute();
}

function buildServiceHref(path = "") {
    return path ? `${SERVICE_ROOT}/${path.replace(/^\/+/, "")}` : SERVICE_ROOT;
}

function buildLoginHref(nextPath = "") {
    const params = new URLSearchParams();
    const safeNext = sanitizeNextPath(nextPath || "");
    if (safeNext && safeNext !== buildServiceHref("dashboard")) {
        params.set("next", safeNext);
    }
    return `${buildServiceHref("login")}${params.toString() ? `?${params.toString()}` : ""}`;
}

function sanitizeNextPath(target) {
    const value = (target || "").trim();
    if (!value) {
        return buildServiceHref("dashboard");
    }
    if (!value.startsWith(SERVICE_ROOT)) {
        return buildServiceHref("dashboard");
    }
    return value;
}

function currentServiceLocation() {
    return `${window.location.pathname}${window.location.search}`;
}

function syncBootstrapSession() {
    if (state.bootstrap) {
        state.bootstrap.session = state.session;
    }
}

function invalidateUserCaches() {
    state.cache.dashboard = null;
    state.cache.orders = null;
    state.cache.wallet = null;
    state.cache.chats = null;
    state.cache.chatThreads.clear();
    state.cache.adminUsers = null;
    state.cache.adminOrders.clear();
}

async function requestJson(url, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers || {});
    const hasJsonBody = options.body !== undefined;

    if (hasJsonBody && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }
    if (method !== "GET" && state.csrfToken && !headers.has("X-CSRF-Token")) {
        headers.set("X-CSRF-Token", state.csrfToken);
    }

    const response = await fetch(url, {
        credentials: "same-origin",
        method,
        headers,
        body: hasJsonBody && headers.get("Content-Type") === "application/json"
            ? JSON.stringify(options.body)
            : options.body,
    });

    let payload = {};
    const isJson = (response.headers.get("content-type") || "").includes("application/json");
    if (isJson) {
        payload = await response.json();
    } else {
        const text = await response.text();
        payload = text ? { message: text } : {};
    }

    if (payload.csrfToken) {
        state.csrfToken = payload.csrfToken;
    }

    if (!response.ok || payload.ok === false) {
        const error = new Error(payload?.error?.message || payload?.message || response.statusText || "Request failed");
        error.status = response.status;
        error.code = payload?.error?.code || "request_failed";
        error.payload = payload;
        throw error;
    }

    return payload;
}

function summarizeOrders(orders) {
    return orders.reduce(
        (summary, order) => {
            summary.total += 1;
            if (order.status === STATUS_COMPLETED) {
                summary.completed += 1;
            }
            if (ACTIVE_ORDER_STATUSES.includes(order.status)) {
                summary.active += 1;
            }
            if (order.complaintStatus && order.complaintStatus !== STATUS_NO_COMPLAINT) {
                summary.complaints += 1;
            }
            return summary;
        },
        {
            total: 0,
            active: 0,
            completed: 0,
            complaints: 0,
        }
    );
}

function formatMetricValue(key, value) {
    if (value === null || value === undefined || value === "") {
        return "--";
    }
    if (typeof value === "number") {
        if (key.includes("rate")) {
            return `${formatNumber(value)}%`;
        }
        return formatNumber(value);
    }
    return String(value);
}

function formatPercent(value) {
    return `${formatNumber(value)}%`;
}

function formatSignedNumber(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
        return String(value);
    }
    return `${numeric >= 0 ? "+" : ""}${formatNumber(numeric)}`;
}

function formatNumber(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
        return String(value);
    }
    return numeric.toLocaleString("zh-CN", {
        maximumFractionDigits: 2,
    });
}

function humanizeKey(value) {
    return String(value || "")
        .split("_")
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" ");
}

function badgeTone(text) {
    const value = String(text || "").toLowerCase();
    if (!value) {
        return "";
    }
    if (/\u5931\u8d25|complaint|banned|cancel|locked|forbidden|danger|\u62d2\u7edd/.test(value)) {
        return "danger";
    }
    if (/\u5f85|pending|processing|review|\u672a\u652f\u4ed8|approval/.test(value)) {
        return "accent";
    }
    return "";
}

function getErrorMessage(error) {
    if (!error) {
        return "Unknown error.";
    }
    if (typeof error === "string") {
        return error;
    }
    return error.message || "Request failed.";
}

function setButtonBusy(button, busy, busyLabel = "Working...") {
    if (!(button instanceof HTMLButtonElement)) {
        return;
    }
    if (!button.dataset.defaultLabel) {
        button.dataset.defaultLabel = button.textContent || "";
    }
    button.disabled = busy;
    button.textContent = busy ? busyLabel : button.dataset.defaultLabel;
}

function showToast(message, tone = "default") {
    if (state.toastTimer) {
        window.clearTimeout(state.toastTimer);
    }
    state.toast = {
        message,
        tone,
    };
    render();
    state.toastTimer = window.setTimeout(() => {
        state.toast = null;
        render();
    }, 3000);
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}
