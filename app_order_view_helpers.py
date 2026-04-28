import json
import os
import sqlite3
from datetime import datetime, timedelta
from flask import session

# ==========================================
# 🌟 独家黑科技：自动嗅探数据库获取历史订单
# ==========================================
def _emergency_get_orders(booster_username):
    """自动去本地数据库/JSON文件中抓取该陪玩师的订单进行比对"""
    orders = []
    if os.path.exists('orders.json'):
        try:
            with open('orders.json', 'r', encoding='utf-8') as f:
                all_orders = json.load(f)
                orders.extend([o for o in all_orders if o.get('booster') == booster_username])
        except Exception:
            pass
            
    if os.path.exists('data.db'):
        try:
            conn = sqlite3.connect('data.db')
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM orders WHERE booster=?", (booster_username,))
            db_orders = [dict(row) for row in cur.fetchall()]
            orders.extend(db_orders)
            conn.close()
        except Exception:
            pass
    return orders

def parse_order_datetime(value):
    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None

def format_time_range(start_dt, end_dt):
    if not start_dt or not end_dt:
        return ""
    return f"{start_dt:%Y-%m-%d %H:%M} - {end_dt:%H:%M}"

def format_duration_hours(hours):
    if hours <= 0:
        return ""
    rounded_hours = round(hours, 2)
    if float(rounded_hours).is_integer():
        return f"{int(rounded_hours)} 小时"
    return f"{rounded_hours:g} 小时"

def calculate_time_based_quote(start_value, end_value, hourly_rate, *, safe_float, stringify_price, existing_orders=None):
    rate_value = safe_float(hourly_rate, 0)
    start_dt = parse_order_datetime(start_value)
    end_dt = parse_order_datetime(end_value)

    if rate_value <= 0:
        return {"valid": False, "error": "该目标尚未配置有效的每小时单价。"}
    if not start_dt or not end_dt:
        return {"valid": False, "error": "请填写完整的开始时间和结束时间。"}
    if end_dt <= start_dt:
        return {"valid": False, "error": "结束时间必须晚于开始时间。"}

    # ==========================================
    # 🛡️ 核心防御：交集定理判断撞单
    # ==========================================
    if existing_orders:
        for order in existing_orders:
            status = order.get("status", "")
            if status in ["已取消", "已拒绝", "已退款", "已完成", "cancelled", "rejected", "completed"]:
                continue
            old_start = parse_order_datetime(order.get("start_time"))
            old_end = parse_order_datetime(order.get("end_time"))
            if old_start and old_end:
                if start_dt < old_end and end_dt > old_start:
                    return {
                        "valid": False, 
                        "error": "⚠️ 下单失败：档期冲突！该陪玩师在您选择的时段内已有其他排班，请调整开始时间或购买时长。"
                    }

    hours = round((end_dt - start_dt).total_seconds() / 3600, 2)
    if hours <= 0:
        return {"valid": False, "error": "预约时长必须大于 0。"}

    total_price = round(rate_value * hours, 2)
    return {
        "valid": True,
        "error": "",
        "hours": hours,
        "hourly_rate": stringify_price(rate_value),
        "duration_text": format_duration_hours(hours),
        "time_range_text": format_time_range(start_dt, end_dt),
        "price": stringify_price(total_price),
    }

def get_order_store(order, *, get_store, get_store_by_owner, get_all_stores):
    if not order:
        return None
    store = None
    if order.get("store_id"):
        store = get_store(order["store_id"])
    if not store and order.get("store_owner"):
        store = get_store_by_owner(order["store_owner"])
    if not store and order.get("store_name"):
        for candidate in get_all_stores():
            if candidate["name"] == order["store_name"]:
                store = candidate
                break
    return store

def decorate_order_for_view(order, *, get_order_store, build_store_card, get_user, build_booster_card):
    if not order:
        return None
    order_view = dict(order)
    store = get_order_store(order)
    store_card = build_store_card(store) if store else None
    assigned_booster_username = order.get("assigned_booster") or order.get("booster")
    assigned_booster_user = get_user(assigned_booster_username) if assigned_booster_username else None
    assigned_booster = build_booster_card(assigned_booster_user) if assigned_booster_user and assigned_booster_user["role"] == "booster" else None
    order_view["store"] = store_card
    order_view["store_label"] = order.get("store_name") or (store_card["name"] if store_card else "店铺接待大厅")
    order_view["assigned_booster_username"] = assigned_booster_username
    order_view["assigned_booster_name"] = order.get("assigned_booster_name") or (assigned_booster["display_name"] if assigned_booster else "")
    order_view["booster_label"] = order_view["assigned_booster_name"] or "待店铺分配"
    order_view["assigned_booster_card"] = assigned_booster
    return order_view

# ==========================================
# 🌟 核心修复：后端接管时间轴控制权
# ==========================================
def build_store_order_payload(player_username, store, source, *, safe_float, stringify_price, get_booster_orders=None):
    selected_booster_username = source.get("selected_booster", "").strip()
    service_type = source.get("service_type", "").strip()
    target_rank = source.get("target_rank", "").strip() if service_type == "技术上分" else ""
    selected_booster = None
    for booster in store.get("boosters", []):
        if booster.get("username") == selected_booster_username:
            selected_booster = booster
            break

    price_value = selected_booster.get("price_value", 0) if selected_booster else 0
    
    start_mode = source.get("start_time_mode", "custom")
    
    try:
        hours = float(source.get("order_hours", 1.0))
    except (TypeError, ValueError):
        hours = 1.0

    # 统一时间轴逻辑
    if start_mode == "now":
        start_dt = datetime.now()
        end_dt = start_dt + timedelta(hours=hours)
        start_time = start_dt.strftime("%Y-%m-%dT%H:%M")
        end_time = end_dt.strftime("%Y-%m-%dT%H:%M")
    else:
        start_time = source.get("start_time", "").strip()
        end_time = source.get("end_time", "").strip()
        
        if start_time and not end_time:
            start_dt = parse_order_datetime(start_time)
            if start_dt:
                end_dt = start_dt + timedelta(hours=hours)
                end_time = end_dt.strftime("%Y-%m-%dT%H:%M")

    # 自动获取排期进行防撞单检测
    if get_booster_orders:
        existing_orders = get_booster_orders(selected_booster_username)
    else:
        existing_orders = _emergency_get_orders(selected_booster_username)

    quote = calculate_time_based_quote(
        start_time, end_time, price_value, 
        safe_float=safe_float, stringify_price=stringify_price,
        existing_orders=existing_orders  
    )
    
    return {
        "player": player_username,
        "booster": selected_booster_username,
        "store_id": str(store["id"]),
        "store_owner": store["owner_username"],
        "store_name": store["name"],
        "assigned_booster": "",
        "assigned_booster_name": "",
        "game": source.get("game", "").strip(),
        "detail": source.get("detail", "").strip(),
        "service_type": service_type,
        "target_rank": target_rank,
        "duration": quote.get("duration_text", ""),
        "preferred_time": quote.get("time_range_text", ""),
        "price": quote.get("price", ""),
        "hourly_rate": quote.get("hourly_rate", stringify_price(price_value)),
        "start_time": start_time,
        "end_time": end_time,
        "selected_booster": selected_booster_username,
        "selected_booster_name": selected_booster.get("display_name", "") if selected_booster else "",
        "pricing_valid": bool(selected_booster) and quote.get("valid", False),
        "pricing_error": "请选择一位陪玩师。" if not selected_booster else quote.get("error", ""),
    }

def resolve_store_for_order_target(target, *, get_store_by_slug, get_user, get_store_for_profile):
    store = get_store_by_slug(target)
    if store:
        return store
    booster_user = get_user(target)
    if booster_user and booster_user["role"] == "booster":
        return get_store_for_profile(booster_user.get("profile", {}))
    return None

def get_store_applications_for_owner(owner_username, status=None, *, get_booster_applications):
    applications = get_booster_applications(status=status) if status else get_booster_applications()
    return [item for item in applications if item["store_owner_username"] == owner_username]

def public_store_access_allowed(store, *, store_is_approved):
    if not store:
        return False
    if store_is_approved(store):
        return True
    username = session.get("username")
    role = session.get("role")
    return bool(username and ((role == "merchant" and username == store["owner_username"]) or role == "admin"))
