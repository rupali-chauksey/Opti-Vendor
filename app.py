import streamlit as st
import sqlite3
import pandas as pd
import time
import os
import sys
import datetime

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import importlib
import engine
importlib.reload(engine)
from engine import (
    esc, compute_health_status, compute_reorder_qty, check_approval_required,
    get_product_policy, get_inbound_qty, get_inventory_position, plan_order,
    log_audit_event, reject_plan
)

import database
importlib.reload(database)
from database import init_database

import tools
importlib.reload(tools)
from tools import query_inventory, fetch_vendors, send_a2a_rfq, execute_order, receive_purchase_order

import agents
importlib.reload(agents)
from agents import optivendor_pipeline

# Auto-initialize SQLite database if tables are missing
try:
    conn = sqlite3.connect("optivendor_store.db")
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='purchase_orders'")
    has_table = cur.fetchone()
    conn.close()
    if not has_table:
        init_database()
except Exception:
    init_database()

st.set_page_config(
    page_title="OptiVendor | Autonomous Multi-Agent Procurement System",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Theme State Initialization
if "app_theme" not in st.session_state:
    st.session_state["app_theme"] = "Dark"

# Theme Selector in Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/color/96/bot.png", width=52)
    st.markdown("### 🎨 Theme Mode")
    theme_choice = st.selectbox(
        "Select Interface Theme:",
        ["🌙 Control Tower (Dark)", "☀️ Enterprise (Light)"],
        index=0 if st.session_state.get("app_theme") == "Dark" else 1,
        key="ui_theme_selectbox"
    )
    if "Light" in theme_choice:
        st.session_state["app_theme"] = "Light"
    else:
        st.session_state["app_theme"] = "Dark"
    
    st.divider()
    st.markdown("### System Health & Stack")
    st.success("🟢 11 A2A Vendor Microservices Live")
    st.info("🦙 Local Ollama Models: `qwen2.5:7b` + `llama3.2`")
    st.info("💾 Database: `optivendor_store.db` (SQLite)")

is_dark_mode = st.session_state.get("app_theme") == "Dark"

if is_dark_mode:
    st.markdown("""
    <style>
        header[data-testid="stHeader"] { background: transparent !important; }
        .block-container { padding-top: 1rem !important; padding-bottom: 2rem !important; max-width: 100% !important; }

        .stApp {
            background-color: #080c14 !important;
            background-image: 
                radial-gradient(at 0% 0%, rgba(16, 185, 129, 0.06) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(14, 165, 233, 0.06) 0px, transparent 50%),
                linear-gradient(to right, rgba(30, 41, 59, 0.3) 1px, transparent 1px),
                linear-gradient(to bottom, rgba(30, 41, 59, 0.3) 1px, transparent 1px) !important;
            background-size: 100% 100%, 100% 100%, 32px 32px, 32px 32px !important;
            color: #f8fafc !important;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        
        section[data-testid="stSidebar"] {
            background-color: #0d1322 !important;
            border-right: 1px solid #1e293b !important;
        }
        section[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
        
        .hero-header {
            text-align: left;
            padding: 18px 22px;
            background: #0f172a !important;
            border: 1px solid #1e293b !important;
            border-radius: 14px;
            margin-bottom: 24px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
        }
        .hero-title {
            font-size: 2rem;
            font-weight: 800;
            color: #f8fafc !important;
            letter-spacing: -0.5px;
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .hero-subtitle { color: #94a3b8 !important; font-size: 0.95rem; font-weight: 400; }
        
        .optimizer-card {
            background: #0f172a !important;
            border-radius: 14px;
            padding: 22px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35);
            margin-bottom: 18px;
            border: 1px solid #1e293b !important;
            color: #f8fafc !important;
        }
        .optimizer-card h4, .optimizer-card h3, .optimizer-card p, .optimizer-card li, .optimizer-card b, .optimizer-card span {
            color: #f8fafc !important;
        }
        
        .step-header { display: flex; align-items: center; margin-bottom: 16px; }
        .step-badge {
            background: linear-gradient(135deg, #0d9488 0%, #059669 100%) !important;
            color: #ffffff !important;
            font-weight: 700;
            font-size: 0.95rem;
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-right: 12px;
            box-shadow: 0 2px 6px rgba(16, 185, 129, 0.3);
        }
        .step-title-text { font-size: 1.15rem; font-weight: 700; color: #f8fafc !important; }
        .step-subtitle-text { font-size: 0.82rem; color: #94a3b8 !important; font-weight: 400; display: block; }
        
        .sub-metric-box {
            background: #1e293b !important;
            border: 1px solid #334155 !important;
            border-radius: 10px;
            padding: 14px 10px;
            text-align: center;
        }
        .sub-metric-label { font-size: 0.8rem; color: #94a3b8 !important; font-weight: 500; margin-bottom: 4px; }
        .sub-metric-val { font-size: 1.65rem; font-weight: 800; color: #38bdf8 !important; line-height: 1.1; }
        .sub-metric-unit { font-size: 0.78rem; color: #94a3b8 !important; margin-top: 2px; }
        .sub-metric-badge-low { display: inline-block; background: #451a03 !important; color: #f97316 !important; font-size: 0.72rem; font-weight: 700; padding: 2px 8px; border-radius: 6px; margin-top: 4px; }
        .sub-metric-badge-crit { display: inline-block; background: #450a0a !important; color: #ef4444 !important; font-size: 0.72rem; font-weight: 700; padding: 2px 8px; border-radius: 6px; margin-top: 4px; }
        
        .dialog-bubble-buyer { background-color: #064e3b !important; border-left: 4px solid #10b981 !important; padding: 12px 16px; border-radius: 8px; margin-bottom: 10px; color: #a7f3d0 !important; font-size: 0.93rem; }
        .dialog-bubble-vendor { background-color: #431407 !important; border-left: 4px solid #ea580c !important; padding: 12px 16px; border-radius: 8px; margin-bottom: 10px; color: #ffedd5 !important; font-size: 0.93rem; }
        .dialog-bubble-success { background-color: #042f2e !important; border-left: 4px solid #14b8a6 !important; padding: 12px 16px; border-radius: 8px; margin-bottom: 10px; color: #99f6e4 !important; font-size: 0.93rem; }
        
        .stTabs [data-baseweb="tab-list"] { background: #0f172a !important; border-radius: 10px; padding: 4px; gap: 6px; border: 1px solid #1e293b !important; }
        .stTabs [data-baseweb="tab"] { color: #94a3b8 !important; font-weight: 600; border-radius: 8px; padding: 8px 18px; background: transparent; border: none; font-size: 0.92rem; }
        .stTabs [aria-selected="true"] { background: #1e293b !important; color: #10b981 !important; border-bottom: 2px solid #10b981 !important; box-shadow: 0 2px 8px rgba(16, 185, 129, 0.25) !important; }
        
        div.stButton > button {
            background: #0f172a !important;
            color: #f8fafc !important;
            border: 1px solid #334155 !important;
            border-radius: 10px !important;
            padding: 10px 14px !important;
            text-align: left !important;
            white-space: normal !important;
            word-wrap: break-word !important;
            font-size: 0.82rem !important;
            line-height: 1.35 !important;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25) !important;
        }
        div.stButton > button p, div.stButton > button span, div.stButton > button div { color: #f8fafc !important; }
        div.stButton > button:hover { background: #1e293b !important; color: #38bdf8 !important; border-color: #38bdf8 !important; }
        
        div.stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            padding: 10px 20px !important;
            box-shadow: 0 2px 8px rgba(16, 185, 129, 0.25) !important;
        }
        div.stButton > button[kind="primary"] p, div.stButton > button[kind="primary"] span { color: #ffffff !important; }
        
        div[data-testid="stChatMessage"] { background-color: #0d1527 !important; border: 1px solid #1e293b !important; border-radius: 12px !important; padding: 14px 18px !important; margin-bottom: 12px !important; color: #f8fafc !important; }
        div[data-testid="stChatMessage"] * { color: #f8fafc !important; }
        
        div[data-testid="stAlert"] {
            background-color: #1e293b !important;
            color: #f8fafc !important;
            border: 1px solid #334155 !important;
            border-radius: 10px !important;
        }
        div[data-testid="stAlert"] * {
            color: #f8fafc !important;
        }
        .alert-banner-low {
            border-radius: 8px !important;
            padding: 12px 16px !important;
            margin-top: 14px !important;
            font-size: 0.92rem !important;
        }
    </style>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <style>
        header[data-testid="stHeader"] { background: transparent !important; }
        .block-container { padding-top: 1rem !important; padding-bottom: 2rem !important; max-width: 100% !important; }
        .stApp { background-color: #f5f7fa !important; color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        .hero-header { text-align: left; padding: 10px 0 22px 0; border-bottom: 1px solid #e2e8f0; margin-bottom: 24px; }
        .hero-title { font-size: 2rem; font-weight: 800; color: #0f172a; letter-spacing: -0.5px; margin-bottom: 4px; display: flex; align-items: center; gap: 10px; }
        .hero-subtitle { color: #475569; font-size: 1rem; font-weight: 400; }
        .optimizer-card { background: #ffffff; border-radius: 14px; padding: 22px; box-shadow: 0 4px 16px rgba(15, 23, 42, 0.05); margin-bottom: 18px; border: 1px solid #e2e8f0; }
        .step-header { display: flex; align-items: center; margin-bottom: 16px; }
        .step-badge { background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%); color: #ffffff; font-weight: 700; font-size: 0.95rem; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-right: 12px; }
        .step-title-text { font-size: 1.15rem; font-weight: 700; color: #0f172a; }
        .step-subtitle-text { font-size: 0.82rem; color: #64748b; font-weight: 400; display: block; }
        .sub-metric-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 10px; text-align: center; }
        .sub-metric-label { font-size: 0.8rem; color: #64748b; font-weight: 500; margin-bottom: 4px; }
        .sub-metric-val { font-size: 1.65rem; font-weight: 800; color: #0f172a; line-height: 1.1; }
        .dialog-bubble-buyer { background-color: #f0fdf4; border-left: 4px solid #16a34a; padding: 12px 16px; border-radius: 8px; margin-bottom: 10px; color: #14532d; font-size: 0.93rem; }
        .dialog-bubble-vendor { background-color: #fff7ed; border-left: 4px solid #ea580c; padding: 12px 16px; border-radius: 8px; margin-bottom: 10px; color: #7c2d12; font-size: 0.93rem; }
        .dialog-bubble-success { background-color: #f0fdfa; border-left: 4px solid #0d9488; padding: 12px 16px; border-radius: 8px; margin-bottom: 10px; color: #134e4a; font-size: 0.93rem; }
        div.stButton > button { background-color: #ffffff !important; color: #0f172a !important; border: 1px solid #cbd5e1 !important; border-radius: 10px !important; padding: 10px 14px !important; text-align: left !important; white-space: normal !important; word-wrap: break-word !important; font-size: 0.82rem !important; }
        div.stButton > button[kind="primary"] { background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important; color: #ffffff !important; border: none !important; }
    </style>
    """, unsafe_allow_html=True)

# Top Header Banner
badge_style = "background: #064e3b; border: 1px solid #10b981; color: #34d399;" if is_dark_mode else "background: #f0fdf4; border: 1px solid #bbf7d0; color: #15803d;"
st.markdown(f"""
<div class="hero-header" style="display: flex; justify-content: space-between; align-items: center;">
    <div>
        <div class="hero-title">📦 OptiVendor Enterprise</div>
        <div class="hero-subtitle">Autonomous Multi-Agent Inventory Procurement, A2A Negotiation & POS Inventory Control</div>
    </div>
    <div style="{badge_style} font-size: 0.82rem; font-weight: 700; padding: 6px 14px; border-radius: 20px; display: flex; align-items: center; gap: 6px;">
        ● Orchestrator online
    </div>
</div>
""", unsafe_allow_html=True)

# Sidebar with Single Reset Button & Demo Scenarios
with st.sidebar:
    st.divider()
    st.markdown("### 🎬 Demo Scenarios")
    st.caption("Click any button to auto-run agent")
    
    st.markdown("**📊 Basic Queries**")
    if st.button("1️⃣ Specific Product", use_container_width=True, key="sb_1"):
        st.session_state["demo_query"] = "Check stock for Vegan Jumbo Shrimp"
    if st.button("2️⃣ Out of Stock", use_container_width=True, key="sb_2"):
        st.session_state["demo_query"] = "Check my store inventory and find which items are out of stock"
    if st.button("3️⃣ Expiring Soon", use_container_width=True, key="sb_3"):
        st.session_state["demo_query"] = "Which items are expiring soon?"
    
    st.markdown("---")
    st.markdown("**🟢 Small Orders (Auto)**")
    if st.button("4️⃣ Order 50 Oat Barista", use_container_width=True, key="sb_4"):
        st.session_state["demo_query"] = "Order 50 units of Oat Barista Blend"
    if st.button("5️⃣ Order 50 Almond Milk", use_container_width=True, key="sb_5"):
        st.session_state["demo_query"] = "Order 50 units of Almond Milk Unsweetened"
    
    st.markdown("---")
    st.markdown("**🟠 Large Orders (Approval)**")
    if st.button("6️⃣ Order 200 Truffle Brie", use_container_width=True, key="sb_6"):
        st.session_state["demo_query"] = "Order 200 units of Cultured Truffle Brie"
    if st.button("7️⃣ Order 500 Oat Barista", use_container_width=True, key="sb_7"):
        st.session_state["demo_query"] = "Order 500 units of Oat Barista Blend"
    
    st.divider()
    st.markdown("#### Database Maintenance")
    
    # SINGLE DETERMINISTIC RESET BUTTON WITH CONFIRM DIALOG
    if "show_reset_confirm" not in st.session_state:
        st.session_state["show_reset_confirm"] = False
        
    if not st.session_state["show_reset_confirm"]:
        if st.button("⚠️ Reset to Demo Baseline", use_container_width=True, key="single_reset_btn"):
            st.session_state["show_reset_confirm"] = True
            st.rerun()
    else:
        st.warning("⚠️ **Confirm Reset?** All POs and logs will be restored to original seed baseline.")
        c_rc1, c_rc2 = st.columns(2)
        with c_rc1:
            if st.button("✅ Yes, Reset", type="primary", use_container_width=True, key="confirm_reset_yes"):
                init_database()
                st.session_state["chat_history"] = [
                    {"role": "assistant", "content": "Database restored to baseline seed state! Ready for fresh demo."}
                ]
                st.session_state["pending_approval"] = None
                st.session_state["show_reset_confirm"] = False
                st.success("Database restored to baseline state!")
                st.rerun()
        with c_rc2:
            if st.button("❌ Cancel", use_container_width=True, key="confirm_reset_cancel"):
                st.session_state["show_reset_confirm"] = False
                st.rerun()

    st.divider()
    st.markdown(f"""
    <div style="text-align: center; font-size: 0.85rem; color: {'#94a3b8' if is_dark_mode else '#64748b'}; font-weight: 500;">
        👩‍💻 Developed by<br><b style="color: {'#38bdf8' if is_dark_mode else '#0284c7'}; font-size: 0.95rem; font-weight: 700;">Rupali Chauksey</b>
    </div>
    """, unsafe_allow_html=True)

# Helper: Get Live Inventory DF
def get_inventory_table():
    conn = sqlite3.connect("optivendor_store.db")
    df = pd.read_sql_query("SELECT product_id, name, category, stock_quantity, sales_velocity_daily, target_stock_level, vendor_id, expiration_date FROM inventory", conn)
    conn.close()
    df["sales_velocity_daily"] = df["sales_velocity_daily"].round(1)
    df["Days of Supply"] = (df["stock_quantity"] / df["sales_velocity_daily"]).round(1)
    
    # Inbound Orders & Inventory Position
    df["Inbound (On Order)"] = df["product_id"].apply(lambda pid: get_inbound_qty(pid))
    df["Inventory Position"] = df["stock_quantity"] + df["Inbound (On Order)"]

    today = datetime.date.today()
    def get_days_exp(exp_str):
        try:
            return (datetime.date.fromisoformat(exp_str) - today).days
        except Exception:
            return None
    df["days_to_exp"] = df["expiration_date"].apply(get_days_exp)

    df["raw_status"] = df.apply(
        lambda r: compute_health_status(
            stock=r["stock_quantity"],
            target=r["target_stock_level"],
            velocity=r["sales_velocity_daily"],
            lead_time=2.0,
            days_until_expiry=r["days_to_exp"],
            inbound_qty=r["Inbound (On Order)"]
        ),
        axis=1
    )
    def format_status(r):
        code = r["raw_status"]
        d_exp = r["days_to_exp"]
        d_lbl = f"{d_exp} day" if d_exp == 1 else f"{d_exp} days"
        dos = r["Days of Supply"]
        dos_lbl = f"{dos:.1f} day" if dos == 1.0 else f"{dos:.1f} days"
        if code == "EXPIRY_RISK":
            return f"⏳ Expiry risk ({d_lbl} left)"
        elif code == "STOCKOUT_BEFORE_ARRIVAL":
            return f"⚠️ Stockout before arrival ({dos_lbl} < 2.0d lead time)"
        elif code == "REPLENISHMENT_IN_TRANSIT":
            return f"🚚 In transit ({r['Inbound (On Order)']} units inbound)"
        elif code == "CRITICAL_STOCKOUT":
            return f"🚨 Critical stockout"
        elif code == "LOW_STOCK":
            return "⚠️ Low stock"
        elif code == "OVERSTOCKED":
            return "📦 Overstocked"
        else:
            return "✅ Optimal"

    df["Health Status"] = df.apply(format_status, axis=1)
    df = df.drop(columns=["days_to_exp", "raw_status"])
    return df

# 3 Minimalist Tabs
tab_warroom, tab_chat, tab_pos = st.tabs([
    "🚀 Live Visual War Room",
    "🤖 Multi-Agent Chat Terminal",
    "📦 Live Store Inventory & POS"
])

# -------------------------------------------------------------
# TAB 1: LIVE VISUAL WAR ROOM (STEP-BY-STEP VISUAL SIMULATION)
# -------------------------------------------------------------
with tab_warroom:
    col_left, col_right = st.columns([1, 2.5])
    
    with col_right:
        # Step 1 Data Fetch
        conn = sqlite3.connect("optivendor_store.db")
        cur = conn.cursor()
        cur.execute("SELECT product_id, name, stock_quantity, sales_velocity_daily, target_stock_level FROM inventory WHERE name LIKE ? OR product_id = ?", ("%Oat Barista%", "P-OAT1"))
        row_default = cur.fetchone()
        conn.close()

    with col_left:
        st.markdown("""
        <div class="optimizer-card">
            <h4 style="margin-top:0; color:#0f172a; font-weight:700; font-size:1.1rem;">⚙️ Execution Parameters</h4>
        </div>
        """, unsafe_allow_html=True)
        
        with st.container():
            target_prod = st.selectbox(
                "Select Product",
                ["Oat Barista Blend", "Cultured Truffle Brie", "Vegan Jumbo Shrimp", "Seitan Pepperoni (Bulk)"],
                index=0
            )
            
            # Fetch details for selected product
            conn = sqlite3.connect("optivendor_store.db")
            cur = conn.cursor()
            cur.execute("SELECT product_id, stock_quantity, sales_velocity_daily, target_stock_level, expiration_date FROM inventory WHERE name LIKE ?", (f"%{target_prod}%",))
            row_sel = cur.fetchone()
            conn.close()
            
            pid_sel = row_sel[0] if row_sel else "P-OAT1"
            c_stock = row_sel[1] if row_sel else 12
            vel_sel = row_sel[2] if row_sel else 15.0
            t_lvl = row_sel[3] if row_sel else 100
            exp_sel = row_sel[4] if row_sel else None

            pos_info = get_inventory_position(pid_sel)
            inbound_sel = pos_info["inbound"]
            inv_pos_sel = pos_info["position"]
            headroom_sel = max(0, t_lvl - inv_pos_sel)
            
            today = datetime.date.today()
            days_exp_sel = None
            if exp_sel:
                try:
                    days_exp_sel = (datetime.date.fromisoformat(exp_sel) - today).days
                except Exception:
                    pass
            
            # Compute Lead-Time-Aware Recommended Reorder Qty using centralized plan_order
            plan_rec = plan_order(product_id=pid_sel, requested_qty=None)
            suggested_reorder = plan_rec.qty
            lead_demand = int(vel_sel * 2)
            calc_gap = int(t_lvl - inv_pos_sel + lead_demand)
            
            slider_max = max(100, t_lvl * 2)
            default_val = suggested_reorder
            order_qty = st.slider("Order Quantity", min_value=0, max_value=slider_max, value=default_val, step=5)
            
            if inbound_sel > 0:
                st.info(f"🚚 **{inbound_sel} units already in transit** (Position: {inv_pos_sel}/{t_lvl} units).")
            if calc_gap <= 0:
                st.caption(f"💡 Recommended: **0 units** (Target: {t_lvl} − Position: {inv_pos_sel} + Lead Demand: {lead_demand} = {calc_gap} ≤ 0)")
            elif suggested_reorder != calc_gap:
                st.caption(f"💡 Recommended: **{suggested_reorder} units** (Target: {t_lvl} − Position: {inv_pos_sel} + Lead Demand: {lead_demand} = {calc_gap}, capped to {suggested_reorder})")
            else:
                st.caption(f"💡 Recommended: **{suggested_reorder} units** (Target: {t_lvl} − Position: {inv_pos_sel} + Lead Demand: {lead_demand} = {suggested_reorder})")
            
            if suggested_reorder == 0:
                st.warning("⚠️ **Reorder not recommended:** Inventory position fulfills target capacity. Restock workflow disabled.")
                btn_run_sim = st.button("🚀 Run Agent Workflow", type="primary", use_container_width=True, disabled=True)
            else:
                btn_run_sim = st.button("🚀 Run Agent Workflow", type="primary", use_container_width=True)

    with col_right:
        days_left = round(c_stock / vel_sel, 1) if vel_sel > 0 else 999.0
        days_left_lbl = f"{days_left:.1f} day" if days_left == 1.0 else f"{days_left:.1f} days"
        health_code = compute_health_status(c_stock, t_lvl, vel_sel, lead_time=2.0, days_until_expiry=days_exp_sel, inbound_qty=inbound_sel)
        d_exp_lbl = f"{days_exp_sel} day" if days_exp_sel == 1 else f"{days_exp_sel} days"
        
        if health_code == "EXPIRY_RISK":
            status_badge = f"⏳ EXPIRY RISK ({d_exp_lbl})"
            alert_class = "sub-metric-badge-low"
            banner_bg = "#4c0519" if is_dark_mode else "#fff1f2"
            banner_border = "#881337" if is_dark_mode else "#fecdd3"
            banner_color = "#fecdd3" if is_dark_mode else "#9f1239"
            banner_html = f'<div class="alert-banner-low" style="background:{banner_bg}; border:1px solid {banner_border}; border-left:4px solid #e11d48; color:{banner_color};">⏳ <b>Shelf Monitor Alert:</b> Batch expires in <b>{d_exp_lbl}</b>. Spoilage risk: prioritize depletion before restock.</div>'
        elif health_code == "STOCKOUT_BEFORE_ARRIVAL":
            status_badge = f"⚠️ STOCKOUT BEFORE ARRIVAL"
            alert_class = "sub-metric-badge-crit"
            banner_bg = "#450a0a" if is_dark_mode else "#fff1f2"
            banner_border = "#991b1b" if is_dark_mode else "#fecdd3"
            banner_color = "#fca5a5" if is_dark_mode else "#991b1b"
            banner_html = f'<div class="alert-banner-low" style="background:{banner_bg}; border:1px solid {banner_border}; border-left:4px solid #ef4444; color:{banner_color};">⚠️ <b>Shelf Monitor Warning:</b> On-hand stock is only <b>{c_stock} units</b> ({days_left_lbl} supply), while delivery takes 2 days (+{inbound_sel} units in transit). <b>Stock will run out before arrival!</b> Suggest expediting transit or emergency buffer order.</div>'
        elif health_code == "REPLENISHMENT_IN_TRANSIT":
            status_badge = f"🚚 REPLENISHMENT (+{inbound_sel} Inbound)"
            alert_class = "sub-metric-badge-low"
            banner_bg = "#172554" if is_dark_mode else "#eff6ff"
            banner_border = "#1e40af" if is_dark_mode else "#bfdbfe"
            banner_color = "#bfdbfe" if is_dark_mode else "#1e40af"
            banner_html = f'<div class="alert-banner-low" style="background:{banner_bg}; border:1px solid {banner_border}; border-left:4px solid #2563eb; color:{banner_color};">🚚 <b>Shelf Monitor Notice:</b> Stock is low ({days_left_lbl} supply), but <b>{inbound_sel} units</b> are in transit. Target covered upon arrival.</div>'
        elif health_code == "CRITICAL_STOCKOUT":
            status_badge = "🚨 CRITICAL STOCKOUT"
            alert_class = "sub-metric-badge-crit"
            banner_bg = "#450a0a" if is_dark_mode else "#fff1f2"
            banner_border = "#991b1b" if is_dark_mode else "#fecdd3"
            banner_color = "#fca5a5" if is_dark_mode else "#991b1b"
            banner_html = f'<div class="alert-banner-low" style="background:{banner_bg}; border:1px solid {banner_border}; border-left:4px solid #ef4444; color:{banner_color};">🚨 <b>Shelf Monitor Alert:</b> Critical Stockout risk detected for <code>{target_prod}</code> ({days_left_lbl} supply remaining). Reorder required.</div>'
        elif health_code == "LOW_STOCK":
            status_badge = "⚠️ LOW STOCK"
            alert_class = "sub-metric-badge-low"
            banner_bg = "#431407" if is_dark_mode else "#fff7ed"
            banner_border = "#9a3412" if is_dark_mode else "#fed7aa"
            banner_color = "#fed7aa" if is_dark_mode else "#9a3412"
            banner_html = f'<div class="alert-banner-low" style="background:{banner_bg}; border:1px solid {banner_border}; border-left:4px solid #f97316; color:{banner_color};">⚠️ <b>Shelf Monitor Alert:</b> Stock below safety threshold for <code>{target_prod}</code> ({days_left_lbl} supply remaining). Reorder recommended: <b>{suggested_reorder} units</b>.</div>'
        else:
            status_badge = "✅ OPTIMAL"
            alert_class = ""
            banner_bg = "#052e16" if is_dark_mode else "#f0fdf4"
            banner_border = "#166534" if is_dark_mode else "#bbf7d0"
            banner_color = "#bbf7d0" if is_dark_mode else "#14532d"
            banner_html = f'<div class="alert-banner-low" style="background:{banner_bg}; border:1px solid {banner_border}; border-left:4px solid #16a34a; color:{banner_color};">✅ <b>Shelf Monitor Scan:</b> Stock level is healthy for <code>{target_prod}</code> ({c_stock}/{t_lvl} units).</div>'

        # Fetch last stock movement for subtitle
        conn = sqlite3.connect("optivendor_store.db")
        cur = conn.cursor()
        cur.execute("SELECT po_id, change_qty, timestamp FROM stock_movements WHERE product_id = ? ORDER BY movement_id DESC LIMIT 1", (pid_sel,))
        last_mov = cur.fetchone()
        conn.close()
        
        last_mov_text = f"Last Movement: +{last_mov[1]} units via {last_mov[0]}" if last_mov else "No recent PO receipts"

        # Step 1: Shelf Monitor Card
        st.markdown(f"""
        <div class="optimizer-card">
            <div class="step-header">
                <div class="step-badge">1</div>
                <div>
                    <span class="step-title-text">Shelf Monitor Agent</span>
                    <span class="step-subtitle-text">(Inventory Health Scan • {last_mov_text})</span>
                </div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;">
                <div class="sub-metric-box">
                    <div class="sub-metric-label">Current Stock</div>
                    <div class="sub-metric-val">{c_stock}</div>
                    <div class="sub-metric-unit">units on-hand</div>
                </div>
                <div class="sub-metric-box">
                    <div class="sub-metric-label">Inbound Orders</div>
                    <div class="sub-metric-val" style="color: #2563eb;">+{inbound_sel}</div>
                    <div class="sub-metric-unit">units on order</div>
                </div>
                <div class="sub-metric-box">
                    <div class="sub-metric-label">Days of Supply</div>
                    <div class="sub-metric-val" style="color: {'#dc2626' if health_code == 'CRITICAL_STOCKOUT' else ('#d97706' if 'LOW' in health_code or 'EXPIRY' in health_code else '#16a34a')};">{days_left}</div>
                    <div class="{alert_class}">{status_badge}</div>
                </div>
                <div class="sub-metric-box">
                    <div class="sub-metric-label">Target Capacity</div>
                    <div class="sub-metric-val">{t_lvl}</div>
                    <div class="sub-metric-unit">units max</div>
                </div>
            </div>
            {banner_html}
        </div>
        """, unsafe_allow_html=True)
        
        if btn_run_sim:
            # Execute centralized plan_order
            plan = plan_order(product_id=pid_sel, requested_qty=order_qty)
            pol = get_product_policy(pid_sel)

            # Step 2: Strategic Policy
            st.markdown(f"""
            <div class="optimizer-card">
                <div class="step-header">
                    <div class="step-badge" style="background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);">2</div>
                    <div>
                        <span class="step-title-text">Strategic Memory Bank Policy</span>
                        <span class="step-subtitle-text">(Cost & Demand Bounds Ingestion)</span>
                    </div>
                </div>
                <div class="dialog-bubble-buyer">
                    <b>🧠 Long-Term Strategy Memory Ingested for {pol['name']}:</b><br>
                    • Target Wholesale Price: <b>${pol.get('target_price', 3.30):.2f} / unit</b><br>
                    • Hard Policy Ceiling Price: <b>${pol.get('max_unit_price', 3.80):.2f} / unit</b> (Offers above ceiling will be disqualified)<br>
                    • Bulk Discount Tiers: ≥50 units (5% off), ≥100 units (10% off).
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Step 3: Vendor Marketplace Discovery
            vendors_list = fetch_vendors(product_id=pid_sel)
            st.markdown(f"""
            <div class="optimizer-card">
                <div class="step-header">
                    <div class="step-badge" style="background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);">3</div>
                    <div>
                        <span class="step-title-text">Vendor Marketplace Discovery & Candidate Scoring</span>
                        <span class="step-subtitle-text">({len(vendors_list)} Suppliers Evaluated & Ranked • Weights: 50% Price, 30% SLA / Reliability, 20% Lead Time)</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if vendors_list:
                df_v = pd.DataFrame(vendors_list)
                show_cols = [c for c in ["name", "category", "price_wholesale", "reliability_score", "delivery_days", "total_score", "selection_status"] if c in df_v.columns]
                df_render = df_v[show_cols].rename(columns={
                    "name": "Supplier", "category": "Category", "price_wholesale": "List Price ($)",
                    "reliability_score": "SLA Score", "delivery_days": "Lead Time (Days)",
                    "total_score": "Composite Score", "selection_status": "Policy Status"
                })
                st.dataframe(df_render, use_container_width=True, hide_index=True)
                if plan.get("vendor_selection_rationale"):
                    st.caption(f"🏆 **Supplier Selection Rationale:** {plan['vendor_selection_rationale']}")
            
            if not plan.get("success"):
                st.warning(f"⚠️ {plan.get('message')}")
            else:
                final_q = plan["final_quantity"]
                unit_p = plan["unit_price"]
                po_total = plan["total_cost"]
                deliv_days = plan["delivery_days"]
                deliv_lbl = f"{deliv_days} day" if deliv_days == 1 else f"{deliv_days} days"
                v_name = plan["vendor_name"]

                # Step 4: Multi-Round A2A Negotiation Handshake
                adj_note = f"<br><i>Note: {plan['adjustment_reason']}</i>" if plan.get("adjusted") else ""
                if plan.get("cost_saved", 0.0) <= 0.0:
                    negotiation_body_html = f"""
                    <div class="dialog-bubble-buyer">
                        <b>📤 [Volume Tier Evaluation] Buyer ➔ {v_name}:</b> Requesting {final_q} units of '{target_prod}'.{adj_note}
                    </div>
                    <div class="dialog-bubble-vendor">
                        <b>📥 [Tier Response] {v_name} Agent:</b> Order volume ({final_q} units) does not qualify for bulk tier (minimum 50 units). List price applies: <b>${unit_p:.2f}/unit</b> ({deliv_lbl} delivery).
                    </div>
                    <div class="dialog-bubble-success">
                        <b>🤝 [List Price Confirmed] Buyer ➔ {v_name}:</b> No volume tier eligible, list price accepted. Confirmed {final_q} units @ <b>${unit_p:.2f}/unit</b>. Total PO: <b>${po_total:.2f}</b>.
                    </div>
                    """
                else:
                    negotiation_body_html = f"""
                    <div class="dialog-bubble-buyer">
                        <b>📤 [Round 1 Bid] Buyer ➔ {v_name}:</b> Requesting {final_q} units of '{target_prod}'. Opening bid: <b>${plan['list_price']*0.88:.2f}/unit</b>.{adj_note}
                    </div>
                    <div class="dialog-bubble-vendor">
                        <b>📥 [Round 2 Counter] {v_name} Agent:</b> Volume counter-offer for {final_q} units: <b>${unit_p:.2f}/unit</b> ({deliv_lbl} delivery).
                    </div>
                    <div class="dialog-bubble-success">
                        <b>🤝 [Round 3 Agreement Sealed] Buyer ➔ {v_name}:</b> Confirmed {final_q} units @ <b>${unit_p:.2f}/unit</b>. Total PO: <b>${po_total:.2f}</b> (Saved: <b>${plan['cost_saved']:.2f}</b>).
                    </div>
                    """

                st.markdown(f"""
                <div class="optimizer-card">
                    <div class="step-header">
                        <div class="step-badge" style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);">4</div>
                        <div>
                            <span class="step-title-text">Autonomous Multi-Round A2A Negotiation Engine</span>
                            <span class="step-subtitle-text">(Agent-to-Agent Microservice Handshake)</span>
                        </div>
                    </div>
                    {negotiation_body_html}
                </div>
                """, unsafe_allow_html=True)
                
                # Step 5: Execute Purchase Order with Budget Guard Check
                if plan.get("needs_approval"):
                    reasons = plan.get("approval_reasons") or []
                    approval_sub = reasons[0] if reasons else f"Order Total ${po_total:.2f} Exceeds $500 Autonomous Threshold"
                    st.markdown(f"""
                    <div class="optimizer-card" style="border-left: 5px solid #f59e0b;">
                        <div class="step-header">
                            <div class="step-badge" style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);">5</div>
                            <div>
                                <span class="step-title-text">🛑 Human Approval Required</span>
                                <span class="step-subtitle-text">({approval_sub})</span>
                            </div>
                        </div>
                        <p style="font-size:0.9rem; color:{'#94a3b8' if is_dark_mode else '#64748b'}; margin-bottom:12px;">
                            Order total of <b>${po_total:.2f}</b> ({final_q} units @ ${unit_p:.2f}/unit from {v_name}) requires manager confirmation before dispatch.
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button("✅ Authorize & Dispatch This Order Now", type="primary", use_container_width=True, key="war_room_auth_btn"):
                        exec_res = execute_order(
                            vendor_id=plan["vendor_id"],
                            product_id=pid_sel,
                            quantity=final_q,
                            price=unit_p,
                            actor="STORE_MANAGER",
                            savings=plan["cost_saved"],
                            list_price=plan["list_price"],
                            guard_msg=plan.get("adjustment_reason")
                        )
                        st.success(f"PO {exec_res['po_id']} authorized and dispatched! Expected delivery: {exec_res['expected_delivery']}.")
                        time.sleep(0.5)
                        st.rerun()
                else:
                    exec_res = execute_order(
                        vendor_id=plan["vendor_id"],
                        product_id=pid_sel,
                        quantity=final_q,
                        price=unit_p,
                        actor="WAR_ROOM",
                        savings=plan["cost_saved"],
                        list_price=plan["list_price"],
                        guard_msg=plan.get("adjustment_reason")
                    )
                    
                    st.markdown(f"""
                    <div class="optimizer-card">
                        <div class="step-header">
                            <div class="step-badge" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%);">5</div>
                            <div>
                                <span class="step-title-text">Atomic Purchase Order Dispatched</span>
                                <span class="step-subtitle-text">(PO {exec_res.get('po_id')} Dispatched • Status: IN_TRANSIT)</span>
                            </div>
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;">
                            <div class="sub-metric-box">
                                <div class="sub-metric-label">PO ID</div>
                                <div class="sub-metric-val" style="font-size:1.1rem; color:#38bdf8;">{exec_res.get('po_id')}</div>
                                <div class="sub-metric-unit">Dispatched</div>
                            </div>
                            <div class="sub-metric-box">
                                <div class="sub-metric-label">PO Quantity</div>
                                <div class="sub-metric-val" style="color: #2563eb;">+{exec_res.get('ordered_quantity', final_q)}</div>
                                <div class="sub-metric-unit">units ordered</div>
                            </div>
                            <div class="sub-metric-box">
                                <div class="sub-metric-label">PO Lifecycle Status</div>
                                <div class="sub-metric-val" style="color: #f59e0b; font-size:1.15rem;">IN_TRANSIT</div>
                                <div class="sub-metric-unit">Delivery: {exec_res.get('expected_delivery')}</div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

# -------------------------------------------------------------
# TAB 2: MULTI-AGENT CHAT TERMINAL
# -------------------------------------------------------------
with tab_chat:
    # 5 Interactive Quick Action Cards Grid (Without Text Truncation)
    st.markdown("<p style='font-size:0.85rem; font-weight:700; margin-bottom:8px; text-transform:uppercase; letter-spacing:0.5px;'>⚡ Quick Action Cards</p>", unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        if st.button("🔍 Check Inventory\nView all stock levels", use_container_width=True, key="quick_1"):
            st.session_state["demo_query"] = "Check my store inventory"
            st.rerun()
    with c2:
        if st.button("⚠️ Critical Stockouts\nItems under 2 days", use_container_width=True, key="quick_2"):
            st.session_state["demo_query"] = "Check my store inventory and find which items are out of stock"
            st.rerun()
    with c3:
        if st.button("📅 Expiring Batches\nItems expiring in 7 days", use_container_width=True, key="quick_3"):
            st.session_state["demo_query"] = "Which items are expiring soon?"
            st.rerun()
    with c4:
        if st.button("🛒 Order 50 Oat Barista\nSmall Order (< $500)", use_container_width=True, key="quick_4"):
            st.session_state["demo_query"] = "Order 50 units of Oat Barista Blend"
            st.rerun()
    with c5:
        if st.button("🛒 Order 500 Oat Barista\nLarge Order (> $500)", use_container_width=True, key="quick_5"):
            st.session_state["demo_query"] = "Order 500 units of Oat Barista Blend"
            st.rerun()
    
    st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = [
            {"role": "assistant", "content": "Hello! I am the **OptiVendor Store Manager Orchestrator**. How can I assist with store inventory scans, vendor negotiations, or restock procurement today?"}
        ]

    if "pending_approval" not in st.session_state:
        st.session_state["pending_approval"] = None

    if "demo_query" not in st.session_state:
        st.session_state["demo_query"] = None

    # --- DEDICATED PENDING APPROVALS PANEL ---
    if st.session_state.get("pending_approval") is not None:
        pending = st.session_state["pending_approval"]
        deal = pending["deal"]
        created_time_str = datetime.datetime.fromtimestamp(pending.get("timestamp", time.time())).strftime("%Y-%m-%d %H:%M:%S")
        plan_id = deal.get("plan_id", "PLAN-PENDING")
        prod_name = deal.get("product_name", "Unknown Product")
        proposed_qty = deal.get("quantity", 0)
        total_val = deal.get("total_cost", 0.0)
        unit_p = deal.get("unit_price", 0.0)
        v_name = deal.get("vendor_name", "Unknown Vendor")
        reasons = deal.get("approval_reasons") or []
        reason_txt = reasons[0] if reasons else f"Order total ${total_val:.2f} exceeds $500 threshold"
        adj_msg = deal.get("adjustment_reason")
        adj_html = f"<div style='font-size:0.85rem; color:#d97706; margin-top:8px;'><b>Capacity Adjustment:</b> {adj_msg}</div>" if adj_msg else ""

        st.markdown(f"""
        <div class="optimizer-card" style="border: 2px solid #f59e0b; background: {'#0f172a' if is_dark_mode else '#fffbeb'}; margin-bottom: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid {'#334155' if is_dark_mode else '#fed7aa'}; padding-bottom: 10px; margin-bottom: 14px;">
                <h4 style="margin: 0; color: #f59e0b; display: flex; align-items: center; gap: 8px;">
                    🛡️ Dedicated Pending Approvals Panel
                </h4>
                <span style="font-size: 0.82rem; background: #f59e0b; color: #000; font-weight: 700; padding: 2px 8px; border-radius: 6px;">ACTION REQUIRED</span>
            </div>
            <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 14px;">
                <div class="sub-metric-box">
                    <div class="sub-metric-label">Plan ID</div>
                    <div class="sub-metric-val" style="font-size: 0.95rem; color: #38bdf8;">{plan_id}</div>
                    <div class="sub-metric-unit">Created: {created_time_str}</div>
                </div>
                <div class="sub-metric-box">
                    <div class="sub-metric-label">Product</div>
                    <div class="sub-metric-val" style="font-size: 0.95rem;">{prod_name}</div>
                    <div class="sub-metric-unit">Vendor: {v_name}</div>
                </div>
                <div class="sub-metric-box">
                    <div class="sub-metric-label">Proposed Quantity</div>
                    <div class="sub-metric-val" style="color: #f59e0b;">{proposed_qty} units</div>
                    <div class="sub-metric-unit">${unit_p:.2f}/unit</div>
                </div>
                <div class="sub-metric-box">
                    <div class="sub-metric-label">Total Amount</div>
                    <div class="sub-metric-val" style="color: #10b981;">${total_val:.2f}</div>
                    <div class="sub-metric-unit">Saved: ${deal.get('cost_saved', 0.0):.2f}</div>
                </div>
                <div class="sub-metric-box">
                    <div class="sub-metric-label">Trigger Reason</div>
                    <div class="sub-metric-val" style="font-size: 0.78rem; color: #f87171;">{reason_txt}</div>
                    <div class="sub-metric-unit">Manager Guard</div>
                </div>
            </div>
            {adj_html}
        </div>
        """, unsafe_allow_html=True)

        c_app, c_rej = st.columns(2)
        with c_app:
            if st.button("✅ Approve Proposed Order", type="primary", use_container_width=True, key="panel_approve_btn"):
                # 1. Log APPROVED audit event FIRST (Strict order: APPROVED -> PO_CREATED)
                log_audit_event(
                    event_type="APPROVED",
                    actor="STORE_MANAGER",
                    product_id=deal["product_id"],
                    vendor_id=deal["vendor_id"],
                    po_id=None,
                    reason="Manager approved proposed order plan",
                    details=f"Store manager approved plan {plan_id} for {proposed_qty} units of {prod_name} @ ${unit_p:.2f}/unit (Total: ${total_val:.2f})."
                )

                # 2. Execute PO and log PO_CREATED
                exec_res = execute_order(
                    vendor_id=deal["vendor_id"],
                    product_id=deal["product_id"],
                    quantity=proposed_qty,
                    price=unit_p,
                    actor="STORE_MANAGER",
                    savings=deal.get("cost_saved"),
                    list_price=deal.get("list_price"),
                    guard_msg=deal.get("adjustment_reason")
                )

                success_msg = esc(
                    f"✅ **Purchase Order Approved & Dispatched!**\n\n"
                    f"- **Product:** {prod_name}\n"
                    f"- **Vendor:** {v_name}\n"
                    f"- **Plan ID:** {plan_id}\n"
                    f"- **PO ID:** {exec_res['po_id']}\n"
                    f"- **Quantity:** {exec_res['ordered_quantity']} units\n"
                    f"- **Unit Price:** ${unit_p:.2f}\n"
                    f"- **Total Value:** ${exec_res['total_value']:.2f}\n"
                    f"- **PO Status:** **IN_TRANSIT** (Expected Delivery: {exec_res['expected_delivery']})\n"
                    f"- **Note:** Order will be added to POS inventory upon delivery receipt."
                )
                st.session_state["chat_history"].append({"role": "assistant", "content": success_msg})
                # Remove card after decision
                st.session_state["pending_approval"] = None
                st.success("Order approved and dispatched!")
                time.sleep(0.5)
                st.rerun()

        with c_rej:
            if st.button("❌ Reject Proposed Order", use_container_width=True, key="panel_reject_btn"):
                # 1. Log REJECTED audit event (No PO created)
                reject_plan(
                    plan_id_or_plan=plan_id,
                    actor="STORE_MANAGER",
                    reason="Manager rejected proposed order plan"
                )
                reject_msg = esc(
                    f"❌ **Purchase Order Plan Rejected by Manager**\n\n"
                    f"Plan **{plan_id}** for **{proposed_qty} units** of **{prod_name}** "
                    f"(Total: **${total_val:.2f}**) has been rejected. No PO dispatched."
                )
                st.session_state["chat_history"].append({"role": "assistant", "content": reject_msg})
                # Remove card after decision
                st.session_state["pending_approval"] = None
                st.warning("Order rejected.")
                time.sleep(0.5)
                st.rerun()
        st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

    # Display chat history
    for msg in st.session_state["chat_history"]:
        avatar_icon = "https://img.icons8.com/color/96/bot.png" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=avatar_icon):
            if msg.get("trace_steps"):
                with st.expander("🛠️ View Multi-Agent Execution Graph & Tool Traces (Open/Hide)", expanded=False):
                    for step in msg["trace_steps"]:
                        if "Node 1" in step:
                            st.markdown(f"🧠 **[Node 1: Intent Orchestrator]** `{step}`")
                        elif "Node 2" in step:
                            st.markdown(f"📊 **[Node 2: Shelf Monitor Agent]** `{step}`")
                        elif "Node 3" in step:
                            st.markdown(f"💬 **[Node 3: Autonomous A2A Negotiator]** `{step}`")
                        elif "Node 4" in step:
                            st.markdown(f"🛡️ **[Node 4: Safety Guardrails Engine]** `{step}`")
                        else:
                            st.markdown(f"⚙️ **[Graph Step]** `{step}`")
            st.markdown(msg["content"])

    # Process User Query
    user_query = None
    if st.session_state.get("demo_query"):
        user_query = st.session_state["demo_query"]
        st.session_state["demo_query"] = None
    
    if user_query:
        st.session_state["chat_history"].append({"role": "user", "content": user_query})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_query)

        with st.chat_message("assistant", avatar="https://img.icons8.com/color/96/bot.png"):
            with st.status("🧠 **Orchestrator Executing Multi-Agent Graph...**", expanded=True) as status_box:
                init_state = {
                    "user_query": user_query,
                    "intent": "CHECK_STOCK",
                    "filter_type": "OUT_OF_STOCK",
                    "target_product": None,
                    "target_quantity": 100,
                    "inventory_results": [],
                    "vendor_candidates": [],
                    "current_vendor_index": 0,
                    "iteration_count": 0,
                    "max_iterations": 3,
                    "negotiation_log": [],
                    "agreed_deal": None,
                    "execution_result": None,
                    "human_approval_needed": False,
                    "final_response": "",
                    "trace_steps": []
                }
                
                config = {"configurable": {"thread_id": f"chat_{int(time.time())}"}}
                result = optivendor_pipeline.invoke(init_state, config=config)
                
                for step in result.get("trace_steps", []):
                    if "Node 1" in step:
                        status_box.write(f"🧠 **[Node 1: Intent Orchestrator]** {step}")
                    elif "Node 2" in step:
                        status_box.write(f"📊 **[Node 2: Shelf Monitor Agent]** {step}")
                    elif "Node 3" in step:
                        status_box.write(f"💬 **[Node 3: Autonomous A2A Negotiator]** {step}")
                    elif "Node 4" in step:
                        status_box.write(f"🛡️ **[Node 4: Safety Guardrails Engine]** {step}")
                    else:
                        status_box.write(f"⚙️ **[Graph Step]** {step}")
                    time.sleep(0.2)
                    
                status_box.update(label="✅ **Multi-Agent Pipeline Graph Completed!**", state="complete", expanded=True)

            reply = result.get("final_response", "Request completed.")
            st.markdown(reply)
            st.session_state["chat_history"].append({
                "role": "assistant",
                "content": reply,
                "trace_steps": result.get("trace_steps", [])
            })
            
            if result.get("human_approval_needed") and result.get("agreed_deal"):
                st.session_state["pending_approval"] = {
                    "deal": result["agreed_deal"],
                    "timestamp": time.time()
                }
            st.rerun()

    user_query_manual = st.chat_input("Ask: 'Check my store inventory...'")
    if user_query_manual:
        st.session_state["demo_query"] = user_query_manual
        st.rerun()

# -------------------------------------------------------------
# TAB 3: LIVE STORE INVENTORY, POS & AUDIT LEDGER
# -------------------------------------------------------------
with tab_pos:
    st.markdown("""
    <div class="optimizer-card">
        <h4 style="margin-top:0; color:#0f172a; font-weight:700;">📦 Store Inventory & POS Database State (<code>inventory</code>)</h4>
        <p style="color:#64748b; font-size:0.95rem;">Real-time stock levels, daily sales velocity, target capacity, and Days of Supply.</p>
    </div>
    """, unsafe_allow_html=True)

    df_inv = get_inventory_table()
    if not df_inv.empty:
        st.dataframe(
            df_inv,
            column_config={
                "sales_velocity_daily": st.column_config.NumberColumn("Velocity (units/day)", format="%.1f"),
                "Days of Supply": st.column_config.NumberColumn("Days of Supply", format="%.1f"),
                "stock_quantity": st.column_config.NumberColumn("On-Hand Stock"),
                "Inbound (On Order)": st.column_config.NumberColumn("On Order (Inbound)"),
                "Inventory Position": st.column_config.NumberColumn("Inventory Position"),
                "target_stock_level": st.column_config.NumberColumn("Target Capacity"),
            },
            use_container_width=True,
            hide_index=True
        )

    st.markdown("<div style='margin-top: 24px;'></div>", unsafe_allow_html=True)
    
    # --- PURCHASE ORDERS LIFECYCLE TABLE WITH RECEIVE ACTION BUTTONS ---
    st.markdown(f"""
    <div class="optimizer-card">
        <h4 style="margin-top:0; color:{'#f8fafc' if is_dark_mode else '#0f172a'}; font-weight:700;">📋 Purchase Orders Lifecycle (<code>purchase_orders</code>)</h4>
        <p style="font-size:0.9rem; color:{'#94a3b8' if is_dark_mode else '#64748b'};">Track dispatched orders from <code>IN_TRANSIT</code> ➔ <code>RECEIVED</code>. Click receive to update POS stock & log movements.</p>
    </div>
    """, unsafe_allow_html=True)

    conn = sqlite3.connect("optivendor_store.db")
    try:
        df_po = pd.read_sql_query("SELECT po_id, product_id, vendor_id, quantity, unit_price, total_cost, savings, status, expected_delivery, created_at FROM purchase_orders ORDER BY created_at DESC", conn)
        df_audit = pd.read_sql_query("SELECT log_id, timestamp, event_type, actor, product_id, vendor_id, po_id, reason, details FROM audit_log ORDER BY log_id DESC", conn)
        df_mov = pd.read_sql_query("SELECT movement_id, timestamp, product_id, change_qty, new_stock, reason, po_id FROM stock_movements ORDER BY movement_id DESC", conn)
        df_batches = pd.read_sql_query("SELECT batch_id, product_id, qty, expiry_date, created_at FROM inventory_batches ORDER BY expiry_date ASC", conn)
    except Exception:
        df_po = pd.DataFrame()
        df_audit = pd.DataFrame()
        df_mov = pd.DataFrame()
        df_batches = pd.DataFrame()
    conn.close()

    if not df_po.empty:
        # Map raw enums to readable labels
        df_po_display = df_po.copy()
        df_po_display["status"] = df_po_display["status"].replace({
            "IN_TRANSIT": "In transit", "RECEIVED": "Received", "APPROVED": "Approved", "REJECTED": "Rejected"
        })
        st.dataframe(
            df_po_display,
            column_config={
                "unit_price": st.column_config.NumberColumn("Unit Price ($)", format="$%.2f"),
                "total_cost": st.column_config.NumberColumn("Total Cost ($)", format="$%.2f"),
                "savings": st.column_config.NumberColumn("Savings ($)", format="$%.2f"),
                "status": st.column_config.TextColumn("Status"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        # Action Bar to Simulate Receipt for IN_TRANSIT orders
        in_transit_pos = df_po[df_po["status"].isin(["IN_TRANSIT", "In transit"])]
        if not in_transit_pos.empty:
            st.markdown("##### 🚚 Simulate Delivery Receipt for Pending Orders")
            c_sel, c_btn = st.columns([3, 1])
            with c_sel:
                po_to_receive = st.selectbox("Select IN_TRANSIT Purchase Order to Receive:", in_transit_pos["po_id"].tolist())
            with c_btn:
                st.write("")
                if st.button("📦 Receive Order & Update POS", type="primary", use_container_width=True):
                    rec_res = receive_purchase_order(po_to_receive, actor="STORE_MANAGER")
                    if rec_res.get("success"):
                        st.success(rec_res["message"])
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(rec_res["message"])
    else:
        st.info("No purchase orders created yet. Execute an order in War Room or Chat Terminal!")

    st.markdown("<div style='margin-top: 24px;'></div>", unsafe_allow_html=True)
    
    # Batch-level FEFO Inventory Ledger
    st.markdown(f"""
    <div class="optimizer-card">
        <h4 style="margin-top:0; color:{'#f8fafc' if is_dark_mode else '#0f172a'}; font-weight:700;">🏷️ Batch-Level Inventory Ledger (<code>inventory_batches</code> • FEFO Tracking)</h4>
        <p style="font-size:0.9rem; color:{'#94a3b8' if is_dark_mode else '#64748b'};">Tracks physical batches with distinct expiration dates. Stock depletion prioritizes earliest expiring batches (First Expiring, First Out).</p>
    </div>
    """, unsafe_allow_html=True)
    if not df_batches.empty:
        st.dataframe(df_batches, use_container_width=True, hide_index=True)
    else:
        st.info("No active inventory batches found.")

    st.markdown("<div style='margin-top: 24px;'></div>", unsafe_allow_html=True)

    col_mov, col_log = st.columns(2)
    with col_mov:
        st.markdown("**📈 Stock Movements Ledger (`stock_movements`)**")
        if not df_mov.empty:
            st.dataframe(df_mov, use_container_width=True, hide_index=True)
        else:
            st.info("No inventory stock movements recorded yet.")
            
    with col_log:
        st.markdown("**🛡️ System Audit Trail (`audit_log`)**")
        if not df_audit.empty:
            df_audit_display = df_audit.copy()
            event_map = {
                "PLAN_CREATED": "Plan created",
                "QTY_ADJUSTED": "Quantity adjusted",
                "APPROVAL_REQUESTED": "Approval requested",
                "APPROVED": "Approved",
                "REJECTED": "Rejected",
                "PO_CREATED": "PO created",
                "PO_RECEIVED": "PO received",
                "SYSTEM_INIT": "System initialized"
            }
            df_audit_display["event_type"] = df_audit_display["event_type"].replace(event_map)
            st.dataframe(
                df_audit_display,
                column_config={
                    "timestamp": st.column_config.TextColumn("Timestamp", width="medium"),
                    "event_type": st.column_config.TextColumn("Event", width="small"),
                    "actor": st.column_config.TextColumn("Actor", width="small"),
                    "product_id": st.column_config.TextColumn("Product", width="small"),
                    "po_id": st.column_config.TextColumn("PO ID", width="small"),
                    "reason": st.column_config.TextColumn("Reason", width="medium"),
                    "details": st.column_config.TextColumn("Event Details", width="large")
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Audit log initialized.")