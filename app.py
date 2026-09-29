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
from engine import esc, compute_health_status, compute_reorder_qty, check_approval_required, get_product_policy

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
    df = pd.read_sql_query("SELECT product_id, name, category, stock_quantity, sales_velocity_daily, target_stock_level, vendor_id FROM inventory", conn)
    conn.close()
    df["sales_velocity_daily"] = df["sales_velocity_daily"].round(1)
    df["Days of Supply"] = (df["stock_quantity"] / df["sales_velocity_daily"]).round(1)
    df["Health Status"] = df.apply(
        lambda r: compute_health_status(r["stock_quantity"], r["target_stock_level"], r["sales_velocity_daily"]),
        axis=1
    )
    df["Health Status"] = df["Health Status"].apply(
        lambda s: "🚨 CRITICAL STOCKOUT" if s == "CRITICAL_STOCKOUT" else ("⚠️ LOW STOCK" if s == "LOW_STOCK" else "✅ OPTIMAL")
    )
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
            cur.execute("SELECT product_id, stock_quantity, sales_velocity_daily, target_stock_level FROM inventory WHERE name LIKE ?", (f"%{target_prod}%",))
            row_sel = cur.fetchone()
            conn.close()
            
            pid_sel = row_sel[0] if row_sel else "P-OAT1"
            c_stock = row_sel[1] if row_sel else 12
            vel_sel = row_sel[2] if row_sel else 15.0
            t_lvl = row_sel[3] if row_sel else 100
            
            # Compute Lead-Time-Aware Recommended Reorder Qty
            engine_rec_qty = compute_reorder_qty(c_stock, t_lvl, vel_sel, lead_time=2.0)
            
            order_qty = st.slider("Order Quantity", min_value=10, max_value=500, value=max(10, engine_rec_qty), step=5)
            st.caption(f"💡 Engine Recommended Reorder: **{engine_rec_qty} units** (Target: {t_lvl} − Stock: {c_stock} + Lead Sales: {int(vel_sel*2)})")
            btn_run_sim = st.button("🚀 Run Agent Workflow", type="primary", use_container_width=True)

    with col_right:
        days_left = round(c_stock / vel_sel, 1) if vel_sel > 0 else 999.0
        health_code = compute_health_status(c_stock, t_lvl, vel_sel)
        
        if health_code == "CRITICAL_STOCKOUT":
            status_badge = "🚨 CRITICAL STOCKOUT"
            alert_class = "sub-metric-badge-crit"
            banner_html = esc(f'<div class="alert-banner-low">🚨 <b>Shelf Monitor Alert:</b> Critical Stockout risk detected for <code>{target_prod}</code> ({days_left} days supply remaining). Reorder required.</div>')
        elif health_code == "LOW_STOCK":
            status_badge = "⚠️ LOW STOCK"
            alert_class = "sub-metric-badge-low"
            banner_html = esc(f'<div class="alert-banner-low" style="background:#fff7ed; border-color:#fed7aa; border-left-color:#f97316; color:#9a3412;">⚠️ <b>Shelf Monitor Alert:</b> Stock below safety threshold for <code>{target_prod}</code> ({days_left} days supply remaining). Reorder recommended: <b>{engine_rec_qty} units</b>.</div>')
        else:
            status_badge = "✅ OPTIMAL"
            alert_class = ""
            banner_html = esc(f'<div class="alert-banner-low" style="background:#f0fdf4; border-color:#bbf7d0; border-left-color:#16a34a; color:#14532d;">✅ <b>Shelf Monitor Scan:</b> Stock level is healthy for <code>{target_prod}</code> ({c_stock}/{t_lvl} units). Reorder recommended: <b>{engine_rec_qty} units</b> (to cover 2-day lead time sales).</div>')

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
                    <div class="sub-metric-unit">units</div>
                </div>
                <div class="sub-metric-box">
                    <div class="sub-metric-label">Sales Velocity</div>
                    <div class="sub-metric-val">{vel_sel:.1f}</div>
                    <div class="sub-metric-unit">units/day</div>
                </div>
                <div class="sub-metric-box">
                    <div class="sub-metric-label">Days of Supply</div>
                    <div class="sub-metric-val" style="color: {'#dc2626' if health_code == 'CRITICAL_STOCKOUT' else ('#d97706' if health_code == 'LOW_STOCK' else '#16a34a')};">{days_left}</div>
                    <div class="{alert_class}">{status_badge}</div>
                </div>
                <div class="sub-metric-box">
                    <div class="sub-metric-label">Target Capacity</div>
                    <div class="sub-metric-val">{t_lvl}</div>
                    <div class="sub-metric-unit">units</div>
                </div>
            </div>
            {banner_html}
        </div>
        """, unsafe_allow_html=True)
        
        if btn_run_sim:
            pol = get_product_policy(pid_sel)
            # Step 2: Strategic Policy
            st.markdown(esc(f"""
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
                    • Target Wholesale Price: <b>$3.30 / unit</b><br>
                    • Hard Policy Ceiling Price: <b>${pol.get('max_unit_price', 4.50):.2f} / unit</b> (Reject offers above ceiling)<br>
                    • Bulk Discount Tiers: ≥50 units (5% off), ≥100 units (10% off).
                </div>
            </div>
            """), unsafe_allow_html=True)
            
            # Step 3: Vendor Marketplace Discovery
            vendors_list = fetch_vendors(product_id=pid_sel)
            st.markdown(f"""
            <div class="optimizer-card">
                <div class="step-header">
                    <div class="step-badge" style="background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);">3</div>
                    <div>
                        <span class="step-title-text">Vendor Marketplace Discovery & Candidate Scoring</span>
                        <span class="step-subtitle-text">({len(vendors_list)} Suppliers Evaluated & Ranked)</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if vendors_list:
                df_v = pd.DataFrame(vendors_list)
                show_cols = [c for c in ["name", "category", "price_wholesale", "reliability_score", "delivery_days", "total_score", "selection_status"] if c in df_v.columns]
                df_render = df_v[show_cols].rename(columns={
                    "name": "Supplier", "category": "Category", "price_wholesale": "List Price",
                    "reliability_score": "SLA Score", "delivery_days": "Lead Time (Days)",
                    "total_score": "Composite Score", "selection_status": "Policy Status"
                })
                st.dataframe(df_render, use_container_width=True, hide_index=True)
            
            # Step 4: Multi-Round A2A Negotiation Handshake
            top_v = vendors_list[0] if vendors_list else {"name": "Clark Distributing", "endpoint_url": "http://localhost:8002/a2a"}
            rfq_res = send_a2a_rfq(top_v["endpoint_url"], pid_sel, order_qty, target_unit_price=3.30)
            
            st.markdown(esc(f"""
            <div class="optimizer-card">
                <div class="step-header">
                    <div class="step-badge" style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);">4</div>
                    <div>
                        <span class="step-title-text">Autonomous Multi-Round A2A Negotiation Engine</span>
                        <span class="step-subtitle-text">(Agent-to-Agent Microservice Handshake)</span>
                    </div>
                </div>
                <div class="dialog-bubble-buyer">
                    <b>📤 [Round 1 Bid] Buyer ➔ {rfq_res['vendor_name']}:</b> Requesting {order_qty} units of '{target_prod}'. Opening bid: <b>${rfq_res['list_price']*0.88:.2f}/unit</b>.
                </div>
                <div class="dialog-bubble-vendor">
                    <b>📥 [Round 2 Counter] {rfq_res['vendor_name']} Agent:</b> Volume counter-offer for {order_qty} units: <b>${rfq_res['negotiated_price']:.2f}/unit</b> ({rfq_res['delivery_days']}-day delivery).
                </div>
                <div class="dialog-bubble-success">
                    <b>🤝 [Round 3 Agreement Sealed] Buyer ➔ {rfq_res['vendor_name']}:</b> Confirmed {order_qty} units @ <b>${rfq_res['negotiated_price']:.2f}/unit</b>. Total PO: <b>${rfq_res['total_cost']:.2f}</b> (Saved: <b>${rfq_res['cost_saved']:.2f}</b>).
                </div>
            </div>
            """), unsafe_allow_html=True)
            
            # Step 5: Execute Purchase Order with Budget Guard Check
            po_total = rfq_res["total_cost"]
            if check_approval_required(po_total):
                st.markdown(esc(f"""
                <div class="optimizer-card" style="border-left: 5px solid #f59e0b;">
                    <div class="step-header">
                        <div class="step-badge" style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);">5</div>
                        <div>
                            <span class="step-title-text">🛑 Human Approval Required</span>
                            <span class="step-subtitle-text">(Order Total ${po_total:.2f} Exceeds $500 Autonomous Threshold)</span>
                        </div>
                    </div>
                    <p style="font-size:0.9rem; color:{'#94a3b8' if is_dark_mode else '#64748b'}; margin-bottom:0;">
                        Order total of <b>${po_total:.2f}</b> ({order_qty} units @ ${rfq_res['negotiated_price']:.2f}/unit) requires manager confirmation before dispatch. Please authorize in Tab 2 (Chat Terminal).
                    </p>
                </div>
                """), unsafe_allow_html=True)
            else:
                exec_res = execute_order(top_v.get("vendor_id", "V-CLARK"), pid_sel, order_qty, rfq_res["negotiated_price"], actor="WAR_ROOM")
                
                st.markdown(esc(f"""
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
                            <div class="sub-metric-val" style="color: #2563eb;">+{exec_res.get('ordered_quantity', order_qty)}</div>
                            <div class="sub-metric-unit">units ordered</div>
                        </div>
                        <div class="sub-metric-box">
                            <div class="sub-metric-label">PO Lifecycle Status</div>
                            <div class="sub-metric-val" style="color: #f59e0b; font-size:1.15rem;">IN_TRANSIT</div>
                            <div class="sub-metric-unit">Delivery: {exec_res.get('expected_delivery')}</div>
                        </div>
                    </div>
                </div>
                """), unsafe_allow_html=True)

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

    # --- HUMAN-IN-THE-LOOP APPROVAL UI ---
    if st.session_state["pending_approval"] is not None:
        pending = st.session_state["pending_approval"]
        deal = pending["deal"]
        
        st.markdown("---")
        st.warning("⚠️ **Pending Order Authorization Required**")
        original_value = deal['quantity'] * deal['unit_price']
        
        st.markdown(f"""
        <div class="optimizer-card" style="border-left: 5px solid #f59e0b;">
            <h4 style="margin-top:0; color:#0f172a;">📋 Order Details Awaiting Manager Approval</h4>
            <ul style="color:#334155; font-size:0.95rem; line-height:1.8;">
                <li><b>Product:</b> {deal['product_name']}</li>
                <li><b>Vendor:</b> {deal['vendor_name']}</li>
                <li><b>Requested Quantity:</b> {deal['quantity']} units</li>
                <li><b>Negotiated Unit Price:</b> ${deal['unit_price']:.2f}</li>
                <li><b>Negotiated Total:</b> <b style="color:#2563eb;">${original_value:.2f}</b></li>
                <li><b>List Price Total:</b> <span style="text-decoration: line-through; color:#64748b;">${deal.get('list_total', original_value):.2f}</span> <span style="color:#16a34a; font-weight:600;">(Saved ${deal.get('cost_saved', 0.0):.2f})</span></li>
                <li><b>Delivery Lead Time:</b> {deal.get('delivery_days', 2)} days</li>
            </ul>
            <p style="color:#64748b; font-size:0.85rem; margin-top:10px; margin-bottom:0;">
                <i>This order total (${original_value:.2f}) exceeds the $500.00 autonomous threshold. Manager confirmation is required.</i>
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Approve & Dispatch Order", type="primary", use_container_width=True, key="approve_btn"):
                exec_res = execute_order(
                    vendor_id=deal["vendor_id"],
                    product_id=deal["product_id"],
                    quantity=deal["quantity"],
                    price=deal["unit_price"],
                    actor="STORE_MANAGER"
                )
                
                if exec_res.get("success"):
                    success_msg = esc(
                        f"✅ **Purchase Order Approved & Dispatched!**\n\n"
                        f"- **Product:** {deal['product_name']}\n"
                        f"- **Vendor:** {deal['vendor_name']}\n"
                        f"- **PO ID:** {exec_res['po_id']}\n"
                        f"- **Quantity:** {exec_res['ordered_quantity']} units\n"
                        f"- **Unit Price:** ${deal['unit_price']:.2f}\n"
                        f"- **Total Value:** ${exec_res['total_value']:.2f}\n"
                        f"- **PO Status:** **IN_TRANSIT** (Expected Delivery: {exec_res['expected_delivery']})\n"
                        f"- **Note:** Order will be added to POS inventory upon delivery receipt."
                    )
                    st.session_state["chat_history"].append({"role": "assistant", "content": success_msg})
                    st.session_state["pending_approval"] = None
                    st.success("Order approved and dispatched!")
                    time.sleep(0.5)
                    st.rerun()
        
        with col2:
            if st.button("❌ Reject Order", use_container_width=True, key="reject_btn"):
                reject_msg = esc(
                    f"❌ **Purchase Order Rejected by Manager**\n\n"
                    f"The order for **{deal['quantity']} units** of **{deal['product_name']}** "
                    f"(Total: **${original_value:.2f}**) has been rejected. No PO dispatched."
                )
                st.session_state["chat_history"].append({"role": "assistant", "content": reject_msg})
                
                # Log audit entry
                now_str = datetime.datetime.now().isoformat()
                conn = sqlite3.connect("optivendor_store.db")
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO audit_log (timestamp, event_type, actor, product_id, vendor_id, po_id, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (now_str, "PO_REJECTED", "STORE_MANAGER", deal['product_id'], deal['vendor_id'], None, f"Manager rejected PO request for {deal['quantity']} units of {deal['product_name']} (Total: ${original_value:.2f})."))
                conn.commit()
                conn.close()
                
                st.session_state["pending_approval"] = None
                st.warning("Order rejected.")
                time.sleep(0.5)
                st.rerun()

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
            df_inv.style.apply(
                lambda row: ['background-color: #fee2e2; font-weight: bold;' if 'CRITICAL' in str(row['Health Status']) else ('background-color: #fef3c7;' if 'LOW' in str(row['Health Status']) else '') for _ in row],
                axis=1
            ),
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
        df_audit = pd.read_sql_query("SELECT log_id, timestamp, event_type, actor, product_id, vendor_id, po_id, details FROM audit_log ORDER BY timestamp DESC", conn)
        df_mov = pd.read_sql_query("SELECT movement_id, timestamp, product_id, change_qty, new_stock, reason, po_id FROM stock_movements ORDER BY movement_id DESC", conn)
    except Exception:
        df_po = pd.DataFrame()
        df_audit = pd.DataFrame()
        df_mov = pd.DataFrame()
    conn.close()

    if not df_po.empty:
        st.dataframe(df_po, use_container_width=True, hide_index=True)
        
        # Action Bar to Simulate Receipt for IN_TRANSIT orders
        in_transit_pos = df_po[df_po["status"] == "IN_TRANSIT"]
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
            st.dataframe(df_audit, use_container_width=True, hide_index=True)
        else:
            st.info("Audit log initialized.")