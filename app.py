import streamlit as st
import sqlite3
import pandas as pd
import time
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from database import init_database
from tools import query_inventory, fetch_vendors, send_a2a_rfq, execute_order
from agents import veganflow_pipeline

# Auto-initialize SQLite database on Cloud Deployment if missing
try:
    conn = sqlite3.connect("veganflow_store.db")
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory'")
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

# Professional Enterprise Light Grey Theme (#F5F7FA) with LangSmith/Datadog Minimalist Styling
st.markdown("""
<style>
    /* High-End Logistics & Supply Chain Cyber-Grid Theme */
    .stApp {
        background-color: #f8fafc !important;
        background-image: 
            radial-gradient(at 0% 0%, rgba(14, 165, 233, 0.08) 0px, transparent 50%),
            radial-gradient(at 100% 100%, rgba(16, 185, 129, 0.08) 0px, transparent 50%),
            linear-gradient(to right, rgba(226, 232, 240, 0.6) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(226, 232, 240, 0.6) 1px, transparent 1px) !important;
        background-size: 100% 100%, 100% 100%, 32px 32px, 32px 32px !important;
        color: #0f172a;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* Hero Header Banner (Centered, High Visibility) */
    .hero-header {
        text-align: center;
        padding: 24px 30px;
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 20px;
        margin-bottom: 24px;
        box-shadow: 0 12px 30px -8px rgba(15, 23, 42, 0.35), 0 0 20px rgba(14, 165, 233, 0.12);
    }
    .hero-avatar-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 64px;
        height: 64px;
        border-radius: 18px;
        background: linear-gradient(135deg, #38bdf8 0%, #10b981 100%);
        box-shadow: 0 6px 20px rgba(56, 189, 248, 0.35);
        margin-bottom: 12px;
        font-size: 2rem;
    }
    .hero-title {
        font-size: 2.1rem;
        font-weight: 800;
        color: #ffffff;
        letter-spacing: -0.5px;
        margin-bottom: 6px;
        justify-content: center;
        align-items: center;
        display: flex;
        gap: 10px;
    }
    .hero-title-highlight {
        background: linear-gradient(135deg, #38bdf8 0%, #34d399 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .hero-subtitle {
        color: #94a3b8;
        font-size: 1.02rem;
        font-weight: 400;
        max-width: 680px;
        margin: 0 auto;
    }
    
    /* Glassmorphism White Card Container */
    .optimizer-card {
        background: rgba(255, 255, 255, 0.92);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.05), 0 8px 10px -6px rgba(15, 23, 42, 0.02);
        margin-bottom: 20px;
        border: 1px solid rgba(226, 232, 240, 0.9);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .optimizer-card:hover {
        box-shadow: 0 14px 30px -5px rgba(15, 23, 42, 0.08);
    }
    
    /* Step Header with Badges */
    .step-header {
        display: flex;
        align-items: center;
        margin-bottom: 16px;
    }
    .step-badge {
        background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
        color: #ffffff;
        font-weight: 700;
        font-size: 0.95rem;
        width: 32px;
        height: 32px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-right: 12px;
        box-shadow: 0 2px 6px rgba(2, 132, 199, 0.25);
    }
    .step-title-text {
        font-size: 1.15rem;
        font-weight: 700;
        color: #0f172a;
    }
    .step-subtitle-text {
        font-size: 0.82rem;
        color: #64748b;
        font-weight: 400;
        display: block;
    }
    
    /* Sub-Metric Boxes */
    .sub-metric-box {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 14px 10px;
        text-align: center;
    }
    .sub-metric-label {
        font-size: 0.8rem;
        color: #64748b;
        font-weight: 500;
        margin-bottom: 4px;
    }
    .sub-metric-val {
        font-size: 1.65rem;
        font-weight: 800;
        color: #0f172a;
        line-height: 1.1;
    }
    .sub-metric-unit {
        font-size: 0.78rem;
        color: #64748b;
        margin-top: 2px;
    }
    .sub-metric-badge-low {
        display: inline-block;
        background: #fee2e2;
        color: #dc2626;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 6px;
        margin-top: 4px;
    }
    .sub-metric-badge-crit {
        display: inline-block;
        background: #fef2f2;
        color: #b91c1c;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 6px;
        margin-top: 4px;
    }
    
    /* Preserved Red Status Alert Banner for Critical Stockout */
    .alert-banner-low {
        background: #fef2f2;
        border: 1px solid #fecaca;
        border-left: 5px solid #ef4444;
        border-radius: 8px;
        padding: 12px 16px;
        color: #991b1b;
        font-size: 0.92rem;
        font-weight: 500;
        margin-top: 14px;
    }
    
    /* Dialog Bubbles */
    .dialog-bubble-buyer {
        background-color: #f0fdf4;
        border-left: 4px solid #16a34a;
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 10px;
        color: #14532d;
        font-size: 0.93rem;
    }
    .dialog-bubble-vendor {
        background-color: #fff7ed;
        border-left: 4px solid #ea580c;
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 10px;
        color: #7c2d12;
        font-size: 0.93rem;
    }
    .dialog-bubble-success {
        background-color: #f0fdfa;
        border-left: 4px solid #0d9488;
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 10px;
        color: #134e4a;
        font-size: 0.93rem;
    }
    
    /* Minimalist Datadog / LangSmith Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background: #e2e8f0;
        border-radius: 10px;
        padding: 4px;
        gap: 6px;
        border: 1px solid #cbd5e1;
    }
    .stTabs [data-baseweb="tab"] {
        color: #475569 !important;
        font-weight: 600;
        border-radius: 8px;
        padding: 8px 18px;
        background: transparent;
        border: none;
        font-size: 0.92rem;
    }
    .stTabs [aria-selected="true"] {
        background: #ffffff !important;
        color: #0f172a !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06);
    }
    
    /* Button Customization: GREEN / DARK BLUE for Action */
    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 10px 20px !important;
        box-shadow: 0 2px 8px rgba(16, 185, 129, 0.25) !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #059669 0%, #047857 100%) !important;
        box-shadow: 0 4px 12px rgba(16, 185, 129, 0.35) !important;
    }
    
    .qty-preview-badge {
        background: #f1f5f9;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        text-align: center;
        padding: 8px;
        font-weight: 700;
        font-size: 1.05rem;
        color: #0f172a;
        margin-top: 4px;
        margin-bottom: 14px;
    }
</style>
""", unsafe_allow_html=True)

# Top Header
st.markdown("""
<div class="hero-header">
    <div class="hero-avatar-badge">🤖</div>
    <div class="hero-title">OptiVendor <span class="hero-title-highlight">Multi-Agent System</span></div>
    <div class="hero-subtitle">Autonomous Inventory Procurement, Agent-to-Agent (A2A) Price Negotiation & POS Control</div>
</div>
""", unsafe_allow_html=True)

# Sidebar with Demo Scenarios
with st.sidebar:
    st.markdown("""
    <div style="text-align: center; padding: 6px 0 14px 0;">
        <div style="display: inline-flex; align-items: center; justify-content: center; width: 62px; height: 62px; border-radius: 18px; background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); box-shadow: 0 6px 18px rgba(99, 102, 241, 0.35); margin-bottom: 8px;">
            <span style="font-size: 2rem;">🤖</span>
        </div>
        <h3 style="margin: 4px 0 0 0; color: #0f172a; font-size: 1.15rem; font-weight: 800;">System Health & Stack</h3>
    </div>
    """, unsafe_allow_html=True)
    st.success("🟢 11 A2A Vendor Microservices Live")
    st.info("🦙 Local Ollama Models: `qwen2.5:7b` + `llama3.2`")
    st.info("💾 Database: `veganflow_store.db` (SQLite)")
    
    st.divider()
    
    # ============================================
    # DEMO SCENARIOS IN SIDEBAR
    # ============================================
    st.markdown("### 🎬 Demo Scenarios")
    st.caption("Click any button to auto-run agent")
    
    # --- Basic Queries ---
    st.markdown("**📊 Basic Queries**")
    if st.button("1️⃣ Specific Product", use_container_width=True, key="sb_1"):
        st.session_state["demo_query"] = "Check stock for Vegan Jumbo Shrimp"
    if st.button("2️⃣ Out of Stock", use_container_width=True, key="sb_2"):
        st.session_state["demo_query"] = "Check my store inventory and find which items are out of stock"
    if st.button("3️⃣ Expiring Soon", use_container_width=True, key="sb_3"):
        st.session_state["demo_query"] = "Which items are expiring soon?"
    
    st.markdown("---")
    
    # --- Small Orders ---
    st.markdown("**🟢 Small Orders (Auto)**")
    if st.button("4️⃣ Order 50 Oat Barista", use_container_width=True, key="sb_4"):
        st.session_state["demo_query"] = "Order 50 units of Oat Barista Blend"
    if st.button("5️⃣ Order 50 Almond Milk", use_container_width=True, key="sb_5"):
        st.session_state["demo_query"] = "Order 50 units of Almond Milk Unsweetened"
    
    st.markdown("---")
    
    # --- Large Orders ---
    st.markdown("**🟠 Large Orders (Approval)**")
    if st.button("6️⃣ Order 200 Truffle Brie", use_container_width=True, key="sb_6"):
        st.session_state["demo_query"] = "Order 200 units of Cultured Truffle Brie"
    if st.button("7️⃣ Order 500 Oat Barista", use_container_width=True, key="sb_7"):
        st.session_state["demo_query"] = "Order 500 units of Oat Barista Blend"
    
    st.divider()
    
    # --- Database Maintenance ---
    st.markdown("#### Database Maintenance")
    if st.button("⚠️ Reset POS & Store Database", use_container_width=True):
        init_database()
        st.session_state["chat_history"] = [
            {"role": "assistant", "content": "Database reset! Ready for fresh demo."}
        ]
        st.session_state["pending_approval"] = None
        st.success("Database restored!")
        st.rerun()

    st.divider()
    st.markdown("""
    <div style="text-align: center; font-size: 0.85rem; color: #64748b; font-weight: 500;">
        👩‍💻 Developed by<br><b style="color: #0f172a; font-size: 0.95rem;">Rupali Chauksey</b>
    </div>
    """, unsafe_allow_html=True)

# Helper: Get Live Inventory DF
def get_inventory_table():
    conn = sqlite3.connect("veganflow_store.db")
    df = pd.read_sql_query("SELECT product_id, name, category, stock_quantity, sales_velocity_daily, target_stock_level, vendor_id FROM inventory", conn)
    conn.close()
    df["Days of Supply"] = (df["stock_quantity"] / df["sales_velocity_daily"]).round(1)
    df["Health Status"] = df["Days of Supply"].apply(
        lambda x: "🚨 CRITICAL STOCKOUT" if x < 1.0 else ("⚠️ LOW STOCK" if x < 3.0 else "✅ OPTIMAL")
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
            order_qty = st.slider("Order Quantity", min_value=20, max_value=500, value=100, step=10)
            st.markdown(f'<div class="qty-preview-badge">{order_qty} units</div>', unsafe_allow_html=True)
            btn_run_sim = st.button("🚀 Run Agent Workflow", type="primary", use_container_width=True)

    with col_right:
        # Step 1 Data Fetch
        conn = sqlite3.connect("veganflow_store.db")
        cur = conn.cursor()
        cur.execute("SELECT product_id, stock_quantity, sales_velocity_daily, target_stock_level FROM inventory WHERE name LIKE ?", (f"%{target_prod}%",))
        row = cur.fetchone()
        conn.close()
        
        pid = row[0] if row else "P-OAT1"
        cur_stock = row[1] if row else 12
        velocity = row[2] if row else 15.0
        target_lvl = row[3] if row else 100
        days_left = round(cur_stock / velocity, 1) if velocity > 0 else 999.0
        
        # Step 1: Shelf Monitor Card
        st.markdown(f"""
        <div class="optimizer-card">
            <div class="step-header">
                <div class="step-badge">1</div>
                <div>
                    <span class="step-title-text">Shelf Monitor Agent</span>
                    <span class="step-subtitle-text">(Inventory Health Scan)</span>
                </div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;">
                <div class="sub-metric-box">
                    <div class="sub-metric-label">Current Stock</div>
                    <div class="sub-metric-val">{cur_stock}</div>
                    <div class="sub-metric-unit">units</div>
                </div>
                <div class="sub-metric-box">
                    <div class="sub-metric-label">Sales Velocity</div>
                    <div class="sub-metric-val">{velocity}</div>
                    <div class="sub-metric-unit">units/day</div>
                </div>
                <div class="sub-metric-box">
                    <div class="sub-metric-label">Days of Supply</div>
                    <div class="sub-metric-val" style="color: {'#dc2626' if days_left < 1.0 else ('#d97706' if days_left < 3.0 else '#16a34a')};">{days_left}</div>
                    <div class="{ 'sub-metric-badge-crit' if days_left < 1.0 else ('sub-metric-badge-low' if days_left < 3.0 else '')}">
                        {'🚨 CRITICAL' if days_left < 1.0 else ('⚠️ LOW' if days_left < 3.0 else '✅ OPTIMAL')}
                    </div>
                </div>
                <div class="sub-metric-box">
                    <div class="sub-metric-label">Target Stock</div>
                    <div class="sub-metric-val">{target_lvl}</div>
                    <div class="sub-metric-unit">units</div>
                </div>
            </div>
            <div class="alert-banner-low">
                ⚠️ <b>Alert commanded by Shelf Monitor:</b> Stock level critically low for <code>{target_prod}</code> ({days_left} days remaining). Automated reorder sequence initiated for {order_qty} units.
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if btn_run_sim:
            # Step 2: Strategic Memory Policy
            st.markdown("""
            <div class="optimizer-card">
                <div class="step-header">
                    <div class="step-badge" style="background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);">2</div>
                    <div>
                        <span class="step-title-text">Strategic Memory Bank Policy</span>
                        <span class="step-subtitle-text">(Cost & Demand Bounds Ingestion)</span>
                    </div>
                </div>
                <div class="dialog-bubble-buyer">
                    <b>🧠 Long-Term Strategy Memory Ingested:</b><br>
                    • Target Wholesale Price: <b>$3.30 / unit</b><br>
                    • Hard Budget Ceiling: <b>$3.60 / unit</b> (Reject offers above this threshold)<br>
                    • Bulk Quantity Rule: Orders ≥ 50 units unlock 5% volume supplier discount.
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Step 3: Vendor Discovery
            vendors_list = fetch_vendors(product_id=pid)
            st.markdown(f"""
            <div class="optimizer-card">
                <div class="step-header">
                    <div class="step-badge" style="background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);">3</div>
                    <div>
                        <span class="step-title-text">Vendor Marketplace Discovery</span>
                        <span class="step-subtitle-text">({len(vendors_list)} Competing Suppliers Identified)</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if vendors_list:
                st.dataframe(pd.DataFrame(vendors_list)[["name", "category", "reliability_score", "price_wholesale", "delivery_days"]], use_container_width=True)
            
            # Step 4: A2A Autonomous Negotiation
            top_v = vendors_list[0] if vendors_list else {"name": "Earthly Gourmet", "endpoint_url": "http://localhost:8001/a2a"}
            rfq_res = send_a2a_rfq(top_v["endpoint_url"], pid, order_qty, target_unit_price=3.30)
            
            st.markdown(f"""
            <div class="optimizer-card">
                <div class="step-header">
                    <div class="step-badge" style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);">4</div>
                    <div>
                        <span class="step-title-text">Autonomous A2A Negotiation Engine</span>
                        <span class="step-subtitle-text">(Agent-to-Agent Microservice Handshake)</span>
                    </div>
                </div>
                <div class="dialog-bubble-buyer">
                    <b>📤 [A2A Handshake] Procurement Buyer ➔ {rfq_res['vendor_name']}:</b><br>
                    <i>"PURCHASE ORDER INQUIRY: Requesting {order_qty} units of '{target_prod}'. Opening target bid: <b>$3.30 / unit</b>."</i>
                </div>
                <div class="dialog-bubble-vendor">
                    <b>📥 [A2A Counter] {rfq_res['vendor_name']} Vendor Agent:</b><br>
                    <i>"COUNTER-OFFER: List price is ${rfq_res['list_price']:.2f}. For volume of {order_qty} units, accepted wholesale price is <b>${rfq_res['negotiated_price']:.2f} / unit</b> with {rfq_res['delivery_days']}-day delivery."</i>
                </div>
                <div class="dialog-bubble-success">
                    <b>🤝 [A2A Agreement Sealed] Procurement Agent ➔ {rfq_res['vendor_name']}:</b><br>
                    <i>"PURCHASE CONFIRMED: {order_qty} units @ ${rfq_res['negotiated_price']:.2f}/unit. Total PO Value: <b>${rfq_res['total_cost']:.2f}</b> (Saved: <b>${rfq_res['cost_saved']:.2f}</b>)."</i>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Step 5: Execute Order & POS Update
            exec_res = execute_order(top_v.get("vendor_id", "V-EARTH"), pid, order_qty, rfq_res["negotiated_price"])
            
            st.markdown(f"""
            <div class="optimizer-card">
                <div class="step-header">
                    <div class="step-badge" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%);">5</div>
                    <div>
                        <span class="step-title-text">Atomic POS Store Execution</span>
                        <span class="step-subtitle-text">(SQLite Database State Update & Audit)</span>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;">
                    <div class="sub-metric-box">
                        <div class="sub-metric-label">Previous Stock</div>
                        <div class="sub-metric-val">{exec_res.get('previous_stock', cur_stock)}</div>
                        <div class="sub-metric-unit">units</div>
                    </div>
                    <div class="sub-metric-box">
                        <div class="sub-metric-label">Inbound Replenishment</div>
                        <div class="sub-metric-val" style="color: #2563eb;">+{exec_res.get('ordered_quantity', order_qty)}</div>
                        <div class="sub-metric-unit">units</div>
                    </div>
                    <div class="sub-metric-box">
                        <div class="sub-metric-label">Updated POS Inventory</div>
                        <div class="sub-metric-val" style="color: #16a34a;">{exec_res.get('updated_stock', cur_stock + order_qty)}</div>
                        <div class="sub-metric-unit">✅ OPTIMAL HEALTH</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
           
# -------------------------------------------------------------
# TAB 2: MULTI-AGENT CHAT TERMINAL (WITH HITL APPROVAL + DEMO AUTO-RUN)
# -------------------------------------------------------------
with tab_chat:
    st.markdown("""
    <div class="optimizer-card">
        <h4 style="margin-top:0; color:#0f172a; font-weight:700;">🤖 Multi-Agent Interactive Chat Terminal</h4>
        <p style="color:#64748b; font-size:0.95rem; margin-bottom:0;">Chat directly with the <b>OptiVendor Store Manager Orchestrator</b>. Or click a demo button in the <b>sidebar</b> to auto-run.</p>
    </div>
    """, unsafe_allow_html=True)

    # Initialize session states
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = [
            {"role": "assistant", "content": "Hello! I am the **OptiVendor Store Manager Orchestrator**. How can I assist with store inventory, out-of-stock scans, or automated restock negotiations today?"}
        ]

    if "pending_approval" not in st.session_state:
        st.session_state["pending_approval"] = None

    if "demo_query" not in st.session_state:
        st.session_state["demo_query"] = None

    if "active_demo_query" not in st.session_state:
        st.session_state["active_demo_query"] = None

    # Display chat history
    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # --- HUMAN-IN-THE-LOOP APPROVAL UI ---
    if st.session_state["pending_approval"] is not None:
        pending = st.session_state["pending_approval"]
        deal = pending["deal"]
        
        st.markdown("---")
        st.warning("⚠️ **Pending Order Approval Required**")
        
        # Calculate original order value
        original_value = deal['quantity'] * deal['unit_price']
        
        st.markdown(f"""
        <div class="optimizer-card" style="border-left: 5px solid #f59e0b;">
            <h4 style="margin-top:0; color:#0f172a;">📋 Order Details Awaiting Manager Approval</h4>
            <ul style="color:#334155; font-size:0.95rem; line-height:1.8;">
                <li><b>Product:</b> {deal['product_name']}</li>
                <li><b>Vendor:</b> {deal['vendor_name']}</li>
                <li><b>Requested Quantity:</b> {deal['quantity']} units</li>
                <li><b>Unit Price:</b> ${deal['unit_price']:.2f}</li>
                <li><b>Original Order Value:</b> <b style="color:#dc2626;">${original_value:.2f}</b></li>
                <li><b>Delivery Window:</b> {deal.get('delivery_days', 'N/A')} days</li>
            </ul>
            <p style="color:#64748b; font-size:0.85rem; margin-top:10px;">
                <i>This order exceeds the $500.00 autonomous threshold. Manager confirmation is required before execution.</i>
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Approve Order", type="primary", use_container_width=True, key="approve_btn"):
                exec_res = execute_order(
                    vendor_id=deal["vendor_id"],
                    product_id=deal["product_id"],
                    quantity=deal["quantity"],
                    price=deal["unit_price"]
                )
                
                if exec_res.get("success"):
                    req_qty = deal.get("quantity", exec_res["ordered_quantity"])
                    actual_qty = exec_res["ordered_quantity"]
                    cur_stock = exec_res.get("previous_stock", 0)
                    
                    conn = sqlite3.connect("veganflow_store.db")
                    cur = conn.cursor()
                    cur.execute("SELECT target_stock_level FROM inventory WHERE product_id = ?", (deal["product_id"],))
                    row = cur.fetchone()
                    conn.close()
                    target_stock = row[0] if row else (cur_stock + actual_qty)
                    max_allowed = target_stock - cur_stock

                    if req_qty > actual_qty:
                        qty_lines = (
                            f"- **Requested Quantity:** {req_qty} units\n"
                            f"- **Actual Ordered Quantity:** {actual_qty} units *(reduced by Overstocking Guard)*\n"
                            f"- **Reason:** Target stock ({target_stock}) - Previous stock ({cur_stock}) = {max_allowed} units maximum allowed\n"
                        )
                    else:
                        qty_lines = (
                            f"- **Requested Quantity:** {req_qty} units\n"
                            f"- **Actual Ordered Quantity:** {actual_qty} units\n"
                        )

                    success_msg = (
                        f"✅ **Order Approved & Executed Successfully!**\n\n"
                        f"- **Product:** {deal['product_name']}\n"
                        f"- **Vendor:** {deal['vendor_name']}\n"
                        f"{qty_lines}"
                        f"- **Unit Price:** ${deal['unit_price']:.2f}\n"
                        f"- **Total PO Cost:** ${exec_res['total_value']:.2f}\n"
                        f"- **New Stock Level:** {exec_res['updated_stock']} units\n"
                        f"- **POS Status:** ✅ Successfully updated in database."
                    )
                    st.session_state["chat_history"].append({"role": "assistant", "content": success_msg})
                    
                    try:
                        with open("approval_log.txt", "a", encoding="utf-8") as f:
                            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | APPROVED | {deal['product_name']} | Requested: {req_qty} | Executed: {actual_qty} | Total: ${exec_res['total_value']:.2f}\n")
                    except Exception:
                        pass
                    
                    st.session_state["pending_approval"] = None
                    st.success("✅ Order approved and executed successfully!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"❌ Execution failed: {exec_res.get('message')}")
        
        with col2:
            if st.button("❌ Reject Order", use_container_width=True, key="reject_btn"):
                reject_msg = (
                    f"❌ **Order Rejected by Manager**\n\n"
                    f"The order for **{deal['quantity']} units** of **{deal['product_name']}** "
                    f"(Total: **${original_value:.2f}**) has been rejected. No action taken."
                )
                st.session_state["chat_history"].append({"role": "assistant", "content": reject_msg})
                
                try:
                    with open("approval_log.txt", "a", encoding="utf-8") as f:
                        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | REJECTED | {deal['product_name']} | {deal['quantity']} units | Total: ${original_value:.2f}\n")
                except Exception:
                    pass
                
                st.session_state["pending_approval"] = None
                st.warning("❌ Order rejected. No action taken.")
                time.sleep(1)
                st.rerun()

    # --- CHAT INPUT (Manual + Demo Auto-Fill) ---
    user_query_manual = st.chat_input("Ask: 'Check my store inventory...'")
    
    # Determine which query to process
    user_query = None
    if user_query_manual:
        user_query = user_query_manual
    elif st.session_state.get("demo_query"):
        user_query = st.session_state["demo_query"]
        st.session_state["demo_query"] = None
    
    if user_query:
        st.session_state["chat_history"].append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)

        with st.chat_message("assistant"):
            with st.status("🧠 **Orchestrator Executing Multi-Agent Graph...**", expanded=True) as status_box:
                status_box.write("🛠️ **Executing Tool:** `orchestrator_node` (Intent Classification)")
                time.sleep(0.3)
                
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
                result = veganflow_pipeline.invoke(init_state, config=config)
                
                for step in result.get("trace_steps", []):
                    status_box.write(f"⚙️ **Step:** {step}")
                    time.sleep(0.2)
                    
                status_box.update(label="✅ **Multi-Agent Task Completed!**", state="complete", expanded=False)

            reply = result.get("final_response", "Request completed.")
            st.session_state["chat_history"].append({"role": "assistant", "content": reply})
            
            # --- CHECK IF HUMAN APPROVAL IS NEEDED ---
            if result.get("human_approval_needed") and result.get("agreed_deal"):
                st.session_state["pending_approval"] = {
                    "deal": result["agreed_deal"],
                    "timestamp": time.time()
                }
            st.rerun()

# -------------------------------------------------------------
# TAB 3: LIVE STORE INVENTORY & POS
# -------------------------------------------------------------
with tab_pos:
    st.markdown("""
    <div class="optimizer-card">
        <h4 style="margin-top:0; color:#0f172a; font-weight:700;">📦 OptiVendor POS Database State (<code>veganflow_store.db</code>)</h4>
        <p style="color:#64748b; font-size:0.95rem;">Live inventory levels, velocity, and Days of Supply computed from SQLite.</p>
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