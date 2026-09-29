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
from agents import optivendor_pipeline
from engine import esc, compute_health_status, compute_reorder_qty, check_approval_required, get_product_policy

# Auto-initialize SQLite database on Cloud Deployment if missing
try:
    conn = sqlite3.connect("optivendor_store.db")
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

# Theme State Initialization
if "app_theme" not in st.session_state:
    st.session_state["app_theme"] = "Dark"

# Theme Selector in Sidebar (processed first)
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
        /* Remove top Streamlit header gap */
        header[data-testid="stHeader"] {
            background: transparent !important;
        }
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 2rem !important;
            max-width: 100% !important;
        }

        /* High-End Cyber Control Tower Dark Theme */
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
        
        /* Sidebar Styling */
        section[data-testid="stSidebar"] {
            background-color: #0d1322 !important;
            border-right: 1px solid #1e293b !important;
        }
        section[data-testid="stSidebar"] * {
            color: #e2e8f0 !important;
        }
        
        /* Hero Header Banner */
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
        .hero-subtitle {
            color: #94a3b8 !important;
            font-size: 0.95rem;
            font-weight: 400;
        }
        
        /* Dark Optimizer Card Container */
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
        
        /* Step Header with Badges */
        .step-header {
            display: flex;
            align-items: center;
            margin-bottom: 16px;
        }
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
        .step-title-text {
            font-size: 1.15rem;
            font-weight: 700;
            color: #f8fafc !important;
        }
        .step-subtitle-text {
            font-size: 0.82rem;
            color: #94a3b8 !important;
            font-weight: 400;
            display: block;
        }
        
        /* Sub-Metric Boxes */
        .sub-metric-box {
            background: #1e293b !important;
            border: 1px solid #334155 !important;
            border-radius: 10px;
            padding: 14px 10px;
            text-align: center;
        }
        .sub-metric-label {
            font-size: 0.8rem;
            color: #94a3b8 !important;
            font-weight: 500;
            margin-bottom: 4px;
        }
        .sub-metric-val {
            font-size: 1.65rem;
            font-weight: 800;
            color: #38bdf8 !important;
            line-height: 1.1;
        }
        .sub-metric-unit {
            font-size: 0.78rem;
            color: #94a3b8 !important;
            margin-top: 2px;
        }
        .sub-metric-badge-low {
            display: inline-block;
            background: #451a03 !important;
            color: #f97316 !important;
            font-size: 0.72rem;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 6px;
            margin-top: 4px;
        }
        .sub-metric-badge-crit {
            display: inline-block;
            background: #450a0a !important;
            color: #ef4444 !important;
            font-size: 0.72rem;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 6px;
            margin-top: 4px;
        }
        
        /* Dialog Bubbles */
        .dialog-bubble-buyer {
            background-color: #064e3b !important;
            border-left: 4px solid #10b981 !important;
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 10px;
            color: #a7f3d0 !important;
            font-size: 0.93rem;
        }
        .dialog-bubble-vendor {
            background-color: #431407 !important;
            border-left: 4px solid #ea580c !important;
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 10px;
            color: #ffedd5 !important;
            font-size: 0.93rem;
        }
        .dialog-bubble-success {
            background-color: #042f2e !important;
            border-left: 4px solid #14b8a6 !important;
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 10px;
            color: #99f6e4 !important;
            font-size: 0.93rem;
        }
        
        /* Minimalist Cyber Dark Tabs */
        .stTabs [data-baseweb="tab-list"] {
            background: #0f172a !important;
            border-radius: 10px;
            padding: 4px;
            gap: 6px;
            border: 1px solid #1e293b !important;
        }
        .stTabs [data-baseweb="tab"] {
            color: #94a3b8 !important;
            font-weight: 600;
            border-radius: 8px;
            padding: 8px 18px;
            background: transparent;
            border: none;
            font-size: 0.92rem;
        }
        .stTabs [aria-selected="true"] {
            background: #1e293b !important;
            color: #10b981 !important;
            border-bottom: 2px solid #10b981 !important;
            box-shadow: 0 2px 8px rgba(16, 185, 129, 0.25) !important;
        }
        
        /* Button Customization & Text Visibility Fix */
        div.stButton > button {
            background: #0f172a !important;
            color: #f8fafc !important;
            border: 1px solid #334155 !important;
            border-radius: 10px !important;
            padding: 10px 14px !important;
            text-align: left !important;
            white-space: pre-line !important;
            font-size: 0.84rem !important;
            line-height: 1.35 !important;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25) !important;
        }
        div.stButton > button p, div.stButton > button span, div.stButton > button div {
            color: #f8fafc !important;
        }
        div.stButton > button:hover {
            background: #1e293b !important;
            color: #38bdf8 !important;
            border-color: #38bdf8 !important;
            box-shadow: 0 4px 12px rgba(56, 189, 248, 0.2) !important;
        }
        div.stButton > button:hover p, div.stButton > button:hover span, div.stButton > button:hover div {
            color: #38bdf8 !important;
        }
        
        div.stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            padding: 10px 20px !important;
            box-shadow: 0 2px 8px rgba(16, 185, 129, 0.25) !important;
        }
        div.stButton > button[kind="primary"] p, div.stButton > button[kind="primary"] span {
            color: #ffffff !important;
        }
        
        /* Chat Input & Messages Dark Mode Styling */
        div[data-testid="stChatInput"] {
            background-color: #0f172a !important;
            border: 1px solid #334155 !important;
            border-radius: 12px !important;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4) !important;
        }
        div[data-testid="stChatInput"] textarea {
            color: #f8fafc !important;
            background-color: transparent !important;
        }
        div[data-testid="stChatInput"] p, div[data-testid="stChatInput"] span {
            color: #94a3b8 !important;
        }
        
        /* Chat Messages Dark Mode High Contrast Fix */
        div[data-testid="stChatMessage"] {
            background-color: #0d1527 !important;
            border: 1px solid #1e293b !important;
            border-radius: 12px !important;
            padding: 14px 18px !important;
            margin-bottom: 12px !important;
            color: #f8fafc !important;
        }
        div[data-testid="stChatMessage"] * {
            color: #f8fafc !important;
        }
        div[data-testid="stChatMessage"] p, 
        div[data-testid="stChatMessage"] span, 
        div[data-testid="stChatMessage"] div,
        div[data-testid="stChatMessage"] li,
        div[data-testid="stChatMessage"] strong,
        div[data-testid="stChatMessage"] b {
            color: #f8fafc !important;
        }
        
        /* User Chat Message Bubble Distinction */
        div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) {
            background-color: #1e293b !important;
            border: 1px solid #334155 !important;
        }
        div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) * {
            color: #f8fafc !important;
        }
        
        /* Status Widget / Expander Dark Mode Fix */
        div[data-testid="stStatusWidget"], details[data-testid="stExpander"], div[data-testid="stExpander"] {
            background-color: #0b1329 !important;
            border: 1px solid #1e293b !important;
            border-radius: 10px !important;
            color: #f8fafc !important;
            margin-bottom: 12px !important;
        }
        div[data-testid="stStatusWidget"] *, details[data-testid="stExpander"] * {
            color: #cbd5e1 !important;
        }
        div[data-testid="stStatusWidget"] summary, details[data-testid="stExpander"] summary {
            background-color: #0f172a !important;
            color: #38bdf8 !important;
            font-weight: 700 !important;
            border-radius: 8px !important;
        }
        div[data-testid="stStatusWidget"] summary * {
            color: #38bdf8 !important;
        }
        div[data-testid="stStatusWidget"] code, details[data-testid="stExpander"] code {
            background-color: #1e293b !important;
            color: #34d399 !important;
            border: 1px solid #334155 !important;
            padding: 2px 6px !important;
            border-radius: 4px !important;
        }
        
        .qty-preview-badge {
            background: #1e293b !important;
            border: 1px solid #334155 !important;
            border-radius: 8px;
            text-align: center;
            padding: 8px;
            font-weight: 700;
            font-size: 1.05rem;
            color: #f8fafc !important;
            margin-top: 4px;
            margin-bottom: 14px;
        }
    </style>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <style>
        /* Remove top Streamlit header gap */
        header[data-testid="stHeader"] {
            background: transparent !important;
        }
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 2rem !important;
            max-width: 100% !important;
        }

        /* Full Page Background */
        .stApp {
            background-color: #f5f7fa !important;
            background-image: radial-gradient(#e2e8f0 1px, transparent 1px) !important;
            background-size: 24px 24px !important;
            color: #0f172a;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        
        /* Global Typography */
        .hero-header {
            text-align: left;
            padding: 10px 0 22px 0;
            border-bottom: 1px solid #e2e8f0;
            margin-bottom: 24px;
        }
        .hero-title {
            font-size: 2rem;
            font-weight: 800;
            color: #0f172a;
            letter-spacing: -0.5px;
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .hero-subtitle {
            color: #475569;
            font-size: 1rem;
            font-weight: 400;
        }
        
        /* White Card Container */
        .optimizer-card {
            background: #ffffff;
            border-radius: 14px;
            padding: 22px;
            box-shadow: 0 4px 16px rgba(15, 23, 42, 0.05);
            margin-bottom: 18px;
            border: 1px solid #e2e8f0;
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
        
        /* Secondary Buttons Light Mode Customization */
        div.stButton > button {
            background-color: #ffffff !important;
            color: #0f172a !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 10px !important;
            padding: 10px 14px !important;
            text-align: left !important;
            white-space: pre-line !important;
            font-size: 0.84rem !important;
            line-height: 1.35 !important;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04) !important;
        }
        div.stButton > button p, div.stButton > button span, div.stButton > button div {
            color: #0f172a !important;
        }
        div.stButton > button:hover {
            background-color: #f8fafc !important;
            color: #0284c7 !important;
            border-color: #0284c7 !important;
        }
        div.stButton > button:hover p, div.stButton > button:hover span, div.stButton > button:hover div {
            color: #0284c7 !important;
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
        div.stButton > button[kind="primary"] p, div.stButton > button[kind="primary"] span {
            color: #ffffff !important;
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

# Top Header with Status Pill
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

# Sidebar with Demo Scenarios
with st.sidebar:
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
        conn = sqlite3.connect("optivendor_store.db")
        cur = conn.cursor()
        cur.execute("SELECT product_id, stock_quantity, sales_velocity_daily, target_stock_level FROM inventory WHERE name LIKE ?", (f"%{target_prod}%",))
        row = cur.fetchone()
        conn.close()
        
        pid = row[0] if row else "P-OAT1"
        cur_stock = row[1] if row else 12
        velocity = row[2] if row else 15.0
        target_lvl = row[3] if row else 100
        days_left = round(cur_stock / velocity, 1) if velocity > 0 else 999.0
        health_code = compute_health_status(cur_stock, target_lvl, velocity)
        
        if health_code == "CRITICAL_STOCKOUT":
            status_badge = "🚨 CRITICAL STOCKOUT"
            alert_class = "sub-metric-badge-crit"
            banner_html = f'<div class="alert-banner-low">🚨 <b>Alert commanded by Shelf Monitor:</b> Critical Stockout risk detected for <code>{target_prod}</code> ({days_left} days supply remaining). Reorder required.</div>'
        elif health_code == "LOW_STOCK":
            status_badge = "⚠️ LOW STOCK"
            alert_class = "sub-metric-badge-low"
            banner_html = f'<div class="alert-banner-low" style="background:#fff7ed; border-color:#fed7aa; border-left-color:#f97316; color:#9a3412;">⚠️ <b>Alert commanded by Shelf Monitor:</b> Stock below safety threshold for <code>{target_prod}</code> ({days_left} days supply remaining). Reorder recommended.</div>'
        else:
            status_badge = "✅ OPTIMAL"
            alert_class = ""
            banner_html = f'<div class="alert-banner-low" style="background:#f0fdf4; border-color:#bbf7d0; border-left-color:#16a34a; color:#14532d;">✅ <b>Shelf Monitor Scan:</b> Stock level is healthy for <code>{target_prod}</code> ({cur_stock}/{target_lvl} units, {days_left} days supply).</div>'

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
                    <div class="sub-metric-val" style="color: {'#dc2626' if health_code == 'CRITICAL_STOCKOUT' else ('#d97706' if health_code == 'LOW_STOCK' else '#16a34a')};">{days_left}</div>
                    <div class="{alert_class}">
                        {status_badge}
                    </div>
                </div>
                <div class="sub-metric-box">
                    <div class="sub-metric-label">Target Stock</div>
                    <div class="sub-metric-val">{target_lvl}</div>
                    <div class="sub-metric-unit">units</div>
                </div>
            </div>
            {banner_html}
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
            
            # Step 5: Execute Order & POS Update (with Budget Guard Enforcement)
            po_total = rfq_res["total_cost"]
            if check_approval_required(po_total):
                st.markdown(f"""
                <div class="optimizer-card" style="border-left: 5px solid #f59e0b;">
                    <div class="step-header">
                        <div class="step-badge" style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);">5</div>
                        <div>
                            <span class="step-title-text">🛑 Human Approval Required</span>
                            <span class="step-subtitle-text">(Order Total ${po_total:.2f} Exceeds $500 Autonomous Threshold)</span>
                        </div>
                    </div>
                    <p style="font-size:0.9rem; color:{'#94a3b8' if is_dark_mode else '#64748b'};">
                        Order total of <b>${po_total:.2f}</b> ({order_qty} units @ ${rfq_res['negotiated_price']:.2f}/unit) requires manager approval. Please review and approve in Tab 2 (Chat Terminal).
                    </p>
                </div>
                """, unsafe_allow_html=True)
            else:
                exec_res = execute_order(top_v.get("vendor_id", "V-EARTH"), pid, order_qty, rfq_res["negotiated_price"])
                
                st.markdown(f"""
                <div class="optimizer-card">
                    <div class="step-header">
                        <div class="step-badge" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%);">5</div>
                        <div>
                            <span class="step-title-text">Atomic POS Store Execution</span>
                            <span class="step-subtitle-text">(SQLite Database State Update & Audit Logged)</span>
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
    # Welcome Assistant Card Bubble
    st.markdown(f"""
    <div style="display: flex; align-items: flex-start; gap: 14px; background: {'#0f172a' if is_dark_mode else '#f0f9ff'}; border: 1px solid {'#1e293b' if is_dark_mode else '#e0f2fe'}; border-radius: 12px; padding: 16px; margin-bottom: 20px;">
        <img src="https://img.icons8.com/color/96/bot.png" width="46" height="46" style="border-radius: 10px; background: #e0f2fe; padding: 4px; flex-shrink: 0;" />
        <div>
            <h4 style="margin: 0 0 4px 0; font-size: 1.02rem; font-weight: 700; color: {'#f8fafc' if is_dark_mode else '#0f172a'};">Hello! I'm the OptiVendor Store Manager Orchestrator.</h4>
            <p style="margin: 0; font-size: 0.88rem; color: {'#94a3b8' if is_dark_mode else '#334155'};">I can help you with store inventory, out-of-stock scans, vendor negotiations, and automated procurement. Try one of the demo queries below or ask me anything.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 5 Interactive Quick Action Cards Grid
    st.markdown("<p style='font-size:0.85rem; font-weight:700; margin-bottom:8px; text-transform:uppercase; letter-spacing:0.5px;'>⚡ Quick Action Cards</p>", unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        if st.button("🔍 Check my store inventory\nSee all products and risk status", use_container_width=True, key="quick_1"):
            st.session_state["demo_query"] = "Check my store inventory"
            st.rerun()
    with c2:
        if st.button("⚠️ Show out of stock items\nFind critical items (≤ 2 days)", use_container_width=True, key="quick_2"):
            st.session_state["demo_query"] = "Check my store inventory and find which items are out of stock"
            st.rerun()
    with c3:
        if st.button("📅 What's expiring soon?\nItems expiring in 7 days", use_container_width=True, key="quick_3"):
            st.session_state["demo_query"] = "Which items are expiring soon?"
            st.rerun()
    with c4:
        if st.button("🛒 Order 50 Oat Barista\nSmall order (auto-execute)", use_container_width=True, key="quick_4"):
            st.session_state["demo_query"] = "Order 50 units of Oat Barista Blend"
            st.rerun()
    with c5:
        if st.button("🛒 Order 500 Oat Barista\nLarge order (with approval)", use_container_width=True, key="quick_5"):
            st.session_state["demo_query"] = "Order 500 units of Oat Barista Blend"
            st.rerun()
    
    st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

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
        avatar_icon = "https://img.icons8.com/color/96/bot.png" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=avatar_icon):
            if msg.get("trace_steps"):
                with st.expander("🛠️ View Multi-Agent Execution Graph & Tool Traces (Open/Hide)", expanded=False):
                    for step in msg["trace_steps"]:
                        if "Orchestrator" in step:
                            st.markdown(f"🧠 **[Node 1: Intent Orchestrator]** `{step}`")
                        elif "Shelf Monitor" in step:
                            st.markdown(f"📊 **[Node 2: Shelf Monitor Agent]** `{step}`")
                        elif "A2A" in step or "RFQ" in step or "Negotiation" in step:
                            st.markdown(f"💬 **[Node 3: Autonomous A2A Negotiator]** `{step}`")
                        elif "Budget" in step or "Guard" in step or "Execution" in step:
                            st.markdown(f"🛡️ **[Node 4: Safety Guardrails Engine]** `{step}`")
                        else:
                            st.markdown(f"⚙️ **[Graph Step]** `{step}`")
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
                    
                    conn = sqlite3.connect("optivendor_store.db")
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

    # Determine which query to process
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
                result = optivendor_pipeline.invoke(init_state, config=config)
                
                for step in result.get("trace_steps", []):
                    if "Orchestrator" in step:
                        status_box.write(f"🧠 **[Node 1: Intent Orchestrator]** {step}")
                    elif "Shelf Monitor" in step:
                        status_box.write(f"📊 **[Node 2: Shelf Monitor Agent]** {step}")
                    elif "A2A" in step or "RFQ" in step or "Negotiation" in step:
                        status_box.write(f"💬 **[Node 3: Autonomous A2A Negotiator]** {step}")
                    elif "Budget" in step or "Guard" in step or "Execution" in step:
                        status_box.write(f"🛡️ **[Node 4: Safety Guardrails Engine]** {step}")
                    else:
                        status_box.write(f"⚙️ **[Graph Execution Step]** {step}")
                    time.sleep(0.25)
                    
                status_box.update(label="✅ **Multi-Agent Execution Pipeline Completed!**", state="complete", expanded=True)

            reply = result.get("final_response", "Request completed.")
            st.markdown(reply)
            st.session_state["chat_history"].append({
                "role": "assistant",
                "content": reply,
                "trace_steps": result.get("trace_steps", [])
            })
            
            # --- CHECK IF HUMAN APPROVAL IS NEEDED ---
            if result.get("human_approval_needed") and result.get("agreed_deal"):
                st.session_state["pending_approval"] = {
                    "deal": result["agreed_deal"],
                    "timestamp": time.time()
                }
            st.rerun()

    # --- CHAT INPUT (Pinned at Bottom) ---
    user_query_manual = st.chat_input("Ask: 'Check my store inventory...'")
    if user_query_manual:
        st.session_state["demo_query"] = user_query_manual
        st.rerun()

# -------------------------------------------------------------
# TAB 3: LIVE STORE INVENTORY & POS
# -------------------------------------------------------------
with tab_pos:
    st.markdown("""
    <div class="optimizer-card">
        <h4 style="margin-top:0; color:#0f172a; font-weight:700;">📦 OptiVendor POS Database State (<code>optivendor_store.db</code>)</h4>
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

    st.markdown("<div style='margin-top: 24px;'></div>", unsafe_allow_html=True)
    st.markdown(f"""
    <div class="optimizer-card">
        <h4 style="margin-top:0; color:{'#f8fafc' if is_dark_mode else '#0f172a'}; font-weight:700;">📜 Purchase Orders Lifecycle & Audit Log (<code>purchase_orders</code> & <code>audit_log</code>)</h4>
        <p style="font-size:0.9rem; color:{'#94a3b8' if is_dark_mode else '#64748b'};">Full audit history of executed purchase orders, manager approvals, and guardrail interventions.</p>
    </div>
    """, unsafe_allow_html=True)

    conn = sqlite3.connect("optivendor_store.db")
    try:
        df_po = pd.read_sql_query("SELECT po_id, product_id, vendor_id, quantity, unit_price, total_cost, status, created_at FROM purchase_orders ORDER BY created_at DESC", conn)
        df_audit = pd.read_sql_query("SELECT log_id, timestamp, event_type, product_id, vendor_id, details FROM audit_log ORDER BY timestamp DESC", conn)
    except Exception:
        df_po = pd.DataFrame()
        df_audit = pd.DataFrame()
    conn.close()

    col_po, col_log = st.columns(2)
    with col_po:
        st.markdown("**📋 Purchase Orders Lifecycle**")
        if not df_po.empty:
            st.dataframe(df_po, use_container_width=True, hide_index=True)
        else:
            st.info("No purchase orders executed yet. Run an order query in Chat or War Room!")
    with col_log:
        st.markdown("**🛡️ System Audit Trail**")
        if not df_audit.empty:
            st.dataframe(df_audit, use_container_width=True, hide_index=True)
        else:
            st.info("Audit log initialized. System actions will be logged here.")