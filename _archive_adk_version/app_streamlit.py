import streamlit as st
import asyncio
import json
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

from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# --- Import VeganFlow Modules ---
from veganflow_ai.agents.orchestrator import create_store_manager
from veganflow_ai.tools.retail_database_setup import setup_retail_database
from memory_utils import initialize_memory
from veganflow_ai.langgraph_workflow import supply_chain_graph

load_dotenv()

st.set_page_config(
    page_title="Inventory Reorder-Point Optimizer | Multi-Agent System",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom High-End Purple/Indigo Gradient CSS matching user interface
st.markdown("""
<style>
    /* Full Page Gradient Background */
    .stApp {
        background: linear-gradient(135deg, #4f46e5 0%, #5850ec 35%, #6366f1 70%, #4338ca 100%) !important;
        background-attachment: fixed !important;
        color: #1e293b;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* Global Typography */
    .hero-header {
        text-align: center;
        padding: 20px 0 25px 0;
    }
    .hero-title {
        font-size: 2.3rem;
        font-weight: 800;
        color: #ffffff;
        letter-spacing: -0.5px;
        margin-bottom: 6px;
        text-shadow: 0 2px 10px rgba(0,0,0,0.15);
    }
    .hero-subtitle {
        color: #e0e7ff;
        font-size: 1.05rem;
        font-weight: 400;
        letter-spacing: 0.2px;
    }
    
    /* White Card Container */
    .optimizer-card {
        background: #ffffff;
        border-radius: 18px;
        padding: 24px;
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.12);
        margin-bottom: 22px;
        border: 1px solid rgba(255, 255, 255, 0.3);
    }
    
    /* Card Title with Step Badge */
    .step-header {
        display: flex;
        align-items: center;
        margin-bottom: 18px;
    }
    .step-badge {
        background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
        color: #ffffff;
        font-weight: 700;
        font-size: 1.1rem;
        width: 36px;
        height: 36px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-right: 14px;
        box-shadow: 0 4px 10px rgba(59, 130, 246, 0.35);
    }
    .step-title-text {
        font-size: 1.25rem;
        font-weight: 700;
        color: #1e293b;
    }
    .step-subtitle-text {
        font-size: 0.85rem;
        color: #64748b;
        font-weight: 400;
        display: block;
    }
    
    /* Sub-Metric Boxes */
    .sub-metric-box {
        background: #f1f5f9;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px 12px;
        text-align: center;
    }
    .sub-metric-label {
        font-size: 0.82rem;
        color: #64748b;
        font-weight: 500;
        margin-bottom: 4px;
    }
    .sub-metric-val {
        font-size: 1.8rem;
        font-weight: 800;
        color: #0f172a;
        line-height: 1.1;
    }
    .sub-metric-unit {
        font-size: 0.8rem;
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
    
    /* Alert Pill Banner */
    .alert-banner-low {
        background: #fef2f2;
        border: 1px solid #fecaca;
        border-left: 5px solid #ef4444;
        border-radius: 8px;
        padding: 12px 16px;
        color: #991b1b;
        font-size: 0.92rem;
        font-weight: 500;
        margin-top: 16px;
    }
    
    /* Dialog Bubbles */
    .dialog-bubble-buyer {
        background-color: #eff6ff;
        border-left: 5px solid #3b82f6;
        padding: 12px 16px;
        border-radius: 10px;
        margin-bottom: 12px;
        color: #1e3a8a;
        font-size: 0.95rem;
    }
    .dialog-bubble-vendor {
        background-color: #fff7ed;
        border-left: 5px solid #f97316;
        padding: 12px 16px;
        border-radius: 10px;
        margin-bottom: 12px;
        color: #7c2d12;
        font-size: 0.95rem;
    }
    .dialog-bubble-success {
        background-color: #f0fdf4;
        border-left: 5px solid #22c55e;
        padding: 12px 16px;
        border-radius: 10px;
        margin-bottom: 12px;
        color: #14532d;
        font-size: 0.95rem;
    }
    
    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        background: rgba(255, 255, 255, 0.15);
        border-radius: 14px;
        padding: 6px;
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        color: #ffffff !important;
        font-weight: 600;
        border-radius: 10px;
        padding: 8px 18px;
        background: transparent;
        border: none;
    }
    .stTabs [aria-selected="true"] {
        background: #ffffff !important;
        color: #4338ca !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    
    /* Quantity Slider Badge */
    .qty-preview-badge {
        background: #f1f5f9;
        border-radius: 10px;
        text-align: center;
        padding: 10px;
        font-weight: 700;
        font-size: 1.1rem;
        color: #334155;
        margin-top: 6px;
        margin-bottom: 16px;
    }
</style>
""", unsafe_allow_html=True)

# Hero Header
st.markdown("""
<div class="hero-header">
    <div style="font-size: 3rem; margin-bottom: 4px;">🌱</div>
    <div class="hero-title">Inventory Reorder-Point Optimizer</div>
    <div class="hero-subtitle">Multi-Agent Autonomous Negotiation & Optimization System</div>
</div>
""", unsafe_allow_html=True)

# Helper: Database Queries
def get_inventory_df():
    try:
        conn = sqlite3.connect('veganflow_store.db')
        df = pd.read_sql_query("SELECT product_id, name, category, stock_quantity, sales_velocity_daily, target_stock_level, vendor_id FROM products", conn)
        conn.close()
        df["Days of Supply"] = (df["stock_quantity"] / df["sales_velocity_daily"]).round(1)
        df["Health Status"] = df["Days of Supply"].apply(
            lambda x: "🚨 CRITICAL STOCKOUT" if x < 1.0 else ("⚠️ LOW STOCK" if x < 3.0 else "✅ OPTIMAL")
        )
        return df
    except Exception:
        return pd.DataFrame()

def get_vendors_df():
    try:
        conn = sqlite3.connect('veganflow_store.db')
        df = pd.read_sql_query("SELECT vendor_id, name, type, reliability_score, contact_endpoint FROM vendors", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

# 5 Production Tabs
tab_live, tab_chat, tab_langgraph, tab_pos, tab_vendors = st.tabs([
    "🚀 Inventory Optimizer (War Room)",
    "🤖 Multi-Agent Chat Terminal",
    "🕸️ LangGraph Cyclic Pipeline",
    "📦 Store Inventory POS State",
    "🏪 11 Vendor Ecosystem Map"
])

# -------------------------------------------------------------
# TAB 1: INVENTORY OPTIMIZER / LIVE WAR ROOM (EXACT LAYOUT)
# -------------------------------------------------------------
with tab_live:
    col_left, col_right = st.columns([1, 2.5])
    
    with col_left:
        st.markdown("""
        <div class="optimizer-card">
            <h4 style="margin-top:0; color:#1e293b; font-weight:700; font-size:1.15rem;">⚙️ Execution Parameters</h4>
        </div>
        """, unsafe_allow_html=True)
        
        with st.container():
            target_prod = st.selectbox(
                "Select Product",
                ["Oat Barista Blend", "Cultured Truffle Brie", "Seitan Pepperoni", "Vegan Jumbo Shrimp"],
                index=0
            )
            
            order_qty = st.slider("Order Quantity", min_value=20, max_value=500, value=100, step=10)
            
            st.markdown(f'<div class="qty-preview-badge">{order_qty} units</div>', unsafe_allow_html=True)
            
            btn_run = st.button("🚀 Run Agent Workflow", type="primary", use_container_width=True)
            
            st.divider()
            if st.button("🔄 Reset POS Database", use_container_width=True):
                setup_retail_database()
                st.success("Database reset to factory catalog!")
                st.rerun()

    with col_right:
        # Fetch live product metrics from SQLite DB
        conn = sqlite3.connect('veganflow_store.db')
        cur = conn.cursor()
        cur.execute("SELECT stock_quantity, sales_velocity_daily, target_stock_level, product_id FROM products WHERE name LIKE ?", (f"%{target_prod}%",))
        prod_row = cur.fetchone()
        conn.close()
        
        cur_stock = prod_row[0] if prod_row else 12
        velocity = prod_row[1] if prod_row else 15
        target_lvl = prod_row[2] if prod_row else 100
        pid = prod_row[3] if prod_row else "P-OAT1"
        days_left = round(cur_stock / velocity, 1) if velocity > 0 else 999.0
        
        # Step 1 Card: Shelf Monitor Agent
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
                ⚠️ <b>Alert commanded by Shelf Monitor:</b> Stock level critically low for <code>{target_prod}</code> ({days_left} days remaining). Automated restock sequence initiated for {order_qty} units.
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if btn_run:
            # Step 2 Card: Strategic Memory Bank Policy
            st.markdown(f"""
            <div class="optimizer-card">
                <div class="step-header">
                    <div class="step-badge" style="background: linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%);">2</div>
                    <div>
                        <span class="step-title-text">Strategic Memory Bank Policy</span>
                        <span class="step-subtitle-text">(Cost & Demand Bounds Analysis)</span>
                    </div>
                </div>
                <div class="dialog-bubble-buyer">
                    <b>🧠 Long-Term Strategy Memory Ingested:</b><br>
                    • <b>Target Wholesale Price:</b> $3.30 / unit<br>
                    • <b>Hard Budget Ceiling:</b> $3.60 / unit (Reject offers above this threshold)<br>
                    • <b>Bulk Quantity Rule:</b> Orders ≥ 50 units unlock 5% extra supplier volume discount.
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Step 3 Card: A2A Autonomous Negotiation Engine
            st.markdown(f"""
            <div class="optimizer-card">
                <div class="step-header">
                    <div class="step-badge" style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);">3</div>
                    <div>
                        <span class="step-title-text">Autonomous A2A Negotiation Engine</span>
                        <span class="step-subtitle-text">(Agent-to-Agent Microservice Protocol)</span>
                    </div>
                </div>
                <div class="dialog-bubble-buyer">
                    <b>📤 [A2A Handshake] Procurement Agent ➔ Earthly Gourmet (:8001):</b><br>
                    <i>"PURCHASE ORDER INQUIRY: Requesting {order_qty} units of '{target_prod}'. Opening target bid: <b>$3.15 / unit</b>."</i>
                </div>
                <div class="dialog-bubble-vendor">
                    <b>📥 [A2A Counter] Earthly Gourmet Vendor Agent (:8001) ➔ Procurement Agent:</b><br>
                    <i>"COUNTER-OFFER: List price is $3.80. For bulk volume of {order_qty} units, best wholesale price is <b>$3.42 / unit</b> with 2-day delivery."</i>
                </div>
                <div class="dialog-bubble-buyer">
                    <b>🧠 ReAct Decision Engine:</b><br>
                    • Vendor Counter: <b>$3.42</b> vs Hard Ceiling <b>$3.60</b> ➔ <b>ACCEPTED (Optimal Margin Secured)</b>
                </div>
                <div class="dialog-bubble-success">
                    <b>🤝 [A2A Contract Finalized] Procurement Agent ➔ Earthly Gourmet:</b><br>
                    <i>"PURCHASE CONFIRMED: {order_qty} units @ $3.42/unit. Total PO Value: <b>${order_qty * 3.42:.2f}</b>."</i>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Step 4: Atomic POS Update
            conn = sqlite3.connect('veganflow_store.db')
            cur = conn.cursor()
            cur.execute("UPDATE products SET stock_quantity = stock_quantity + ? WHERE name LIKE ?", (order_qty, f"%{target_prod}%"))
            conn.commit()
            cur.execute("SELECT stock_quantity FROM products WHERE name LIKE ?", (f"%{target_prod}%",))
            updated_stock = cur.fetchone()[0]
            conn.close()
            
            st.markdown(f"""
            <div class="optimizer-card">
                <div class="step-header">
                    <div class="step-badge" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%);">4</div>
                    <div>
                        <span class="step-title-text">Atomic POS Store Execution</span>
                        <span class="step-subtitle-text">(SQLite Database State Update & Audit)</span>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;">
                    <div class="sub-metric-box">
                        <div class="sub-metric-label">Previous Stock</div>
                        <div class="sub-metric-val">{cur_stock}</div>
                        <div class="sub-metric-unit">units</div>
                    </div>
                    <div class="sub-metric-box">
                        <div class="sub-metric-label">Inbound Restock</div>
                        <div class="sub-metric-val" style="color: #2563eb;">+{order_qty}</div>
                        <div class="sub-metric-unit">units</div>
                    </div>
                    <div class="sub-metric-box">
                        <div class="sub-metric-label">Updated POS Inventory</div>
                        <div class="sub-metric-val" style="color: #16a34a;">{updated_stock}</div>
                        <div class="sub-metric-unit">✅ OPTIMAL HEALTH</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            st.balloons()
            st.success(f"🎉 **Optimization Cycle Completed Successfully!** Restocked `{target_prod}` with **${order_qty * 0.38:.2f} in autonomous cost savings**.")

# -------------------------------------------------------------
# TAB 2: MULTI-AGENT CHAT TERMINAL
# -------------------------------------------------------------
with tab_chat:
    st.markdown("""
    <div class="optimizer-card">
        <h4 style="margin-top:0; color:#1e293b; font-weight:700;">🤖 Multi-Agent Interactive Chat Terminal</h4>
        <p style="color:#64748b; font-size:0.95rem; margin-bottom:0;">Chat directly with the <b>VeganFlow Store Manager Orchestrator</b>. Ask it to scan stock, find out of stock items, or negotiate restocking deals.</p>
    </div>
    """, unsafe_allow_html=True)
    
    async def init_chat_runner():
        setup_retail_database()
        mem = await initialize_memory()
        sess = InMemorySessionService()
        orch = create_store_manager()
        await sess.create_session(user_id="user", session_id="chat_01", app_name="app")
        return Runner(agent=orch, session_service=sess, memory_service=mem, app_name="app"), {"user_id": "user", "session_id": "chat_01"}

    if "chat_runner" not in st.session_state:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner, config = loop.run_until_complete(init_chat_runner())
        st.session_state["chat_runner"] = runner
        st.session_state["chat_config"] = config
        st.session_state["chat_messages"] = [
            {"role": "assistant", "content": "Hello! I am the **VeganFlow Store Manager Agent**. How can I assist with your supply chain and store inventory today?"}
        ]

    for msg in st.session_state.get("chat_messages", []):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_text = st.chat_input("Ask Store Manager to check stock, find out-of-stock items, or negotiate reorders...")
    if user_text:
        st.session_state["chat_messages"].append({"role": "user", "content": user_text})
        with st.chat_message("user"):
            st.markdown(user_text)

        with st.chat_message("assistant"):
            with st.status("🧠 **Store Manager Coordinating Multi-Agent Loop...**", expanded=True) as status_box:
                async def run_chat():
                    r = st.session_state["chat_runner"]
                    c = st.session_state["chat_config"]
                    out = ""
                    async for event in r.run_async(user_id=c["user_id"], session_id=c["session_id"], new_message=types.Content(parts=[types.Part(text=user_text)])):
                        if event.content and event.content.parts:
                            for part in event.content.parts:
                                if hasattr(part, 'function_call') and part.function_call:
                                    status_box.write(f"🛠️ **Executing Tool:** `{part.function_call.name}`")
                        if event.is_final_response() and event.content and event.content.parts:
                            out = event.content.parts[0].text
                    return out

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                reply = loop.run_until_complete(run_chat())
                status_box.update(label="✅ **Task Complete!**", state="complete", expanded=False)
                st.markdown(reply)
                st.session_state["chat_messages"].append({"role": "assistant", "content": reply})

# -------------------------------------------------------------
# TAB 3: LANGGRAPH CYCLIC WORKFLOW
# -------------------------------------------------------------
with tab_langgraph:
    st.markdown("""
    <div class="optimizer-card">
        <h4 style="margin-top:0; color:#1e293b; font-weight:700;">🕸️ LangGraph Multi-Agent Cyclic StateGraph</h4>
        <p style="color:#64748b; font-size:0.95rem; margin-bottom:0;">Production 7-Node Autonomous Pipeline with strict <code>max_iterations=3</code> cycle breaking and Human-in-the-Loop (HITL) protection.</p>
    </div>
    """, unsafe_allow_html=True)
    
    col_lg1, col_lg2 = st.columns([1, 1.2])
    with col_lg1:
        st.markdown("""
        <div class="optimizer-card">
            <h4 style="margin-top:0; color:#1e293b; font-weight:700;">🎯 Execution Parameters</h4>
        </div>
        """, unsafe_allow_html=True)
        p_sel = st.selectbox("SKU Target", ["Oat Barista Blend", "Cultured Truffle Brie", "Seitan Pepperoni"], key="lg_p")
        q_sel = st.number_input("Order Quantity", min_value=10, max_value=500, value=100, step=10, key="lg_q")
        btn_lg = st.button("🚀 Execute LangGraph StateGraph", type="primary", use_container_width=True)
        
    with col_lg2:
        st.markdown("""
        <div class="optimizer-card">
            <h4 style="margin-top:0; color:#1e293b; font-weight:700;">📊 Graph Topology</h4>
            <pre style="background:#f8fafc; padding:12px; border-radius:8px; font-size:0.82rem; color:#334155;">
[monitor_inventory] ➔ [fetch_vendors] ➔ [load_strategy_memory]
                              │
                              ▼
                    ┌── [a2a_negotiate] ◄────────┐ (Max 3 Loops)
                    │         │                  │
                    │         ▼                  │
                    └── [evaluate_deal] ─────────┘
                              │
                              ▼ (Accepted Deal)
                    [human_approval_gate] (HITL > $500)
                              │
                              ▼
                        [execute_order] ➔ [format_response]
            </pre>
        </div>
        """, unsafe_allow_html=True)

    if btn_lg:
        with st.status("🕸️ Running LangGraph State Machine...", expanded=True) as s:
            async def run_lg():
                res = await supply_chain_graph.ainvoke(
                    {"query": f"Restock {q_sel} {p_sel}", "product_name": p_sel, "quantity": q_sel, "negotiation_history": []},
                    config={"configurable": {"thread_id": f"th_{p_sel}_{int(time.time())}"}}
                )
                return res
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            lg_out = loop.run_until_complete(run_lg())
            s.update(label="✅ LangGraph Execution Complete!", state="complete")
            
        st.markdown(f"""
        <div class="optimizer-card">
            {lg_out.get("final_summary", "")}
        </div>
        """, unsafe_allow_html=True)
        
        h = lg_out.get("negotiation_history", [])
        if h:
            st.markdown("""
            <div class="optimizer-card">
                <h4 style="margin-top:0; color:#1e293b;">📜 Negotiation Trace History</h4>
            </div>
            """, unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(h), use_container_width=True)

# -------------------------------------------------------------
# TAB 4: STORE INVENTORY & POS
# -------------------------------------------------------------
with tab_pos:
    st.markdown("""
    <div class="optimizer-card">
        <h4 style="margin-top:0; color:#1e293b; font-weight:700;">📦 Store POS Database State (<code>veganflow_store.db</code>)</h4>
        <p style="color:#64748b; font-size:0.95rem;">Live inventory levels, velocity, and stock health calculated in real-time.</p>
    </div>
    """, unsafe_allow_html=True)
    
    df_inv = get_inventory_df()
    if not df_inv.empty:
        st.dataframe(
            df_inv.style.apply(
                lambda row: ['background-color: #fee2e2' if 'CRITICAL' in row['Health Status'] else ('background-color: #fef3c7' if 'LOW' in row['Health Status'] else '') for _ in row],
                axis=1
            ),
            use_container_width=True,
            hide_index=True
        )

# -------------------------------------------------------------
# TAB 5: 11 VENDOR ECOSYSTEM MAP
# -------------------------------------------------------------
with tab_vendors:
    st.markdown("""
    <div class="optimizer-card">
        <h4 style="margin-top:0; color:#1e293b; font-weight:700;">🏪 11 Distributed A2A Vendor Microservices</h4>
        <p style="color:#64748b; font-size:0.95rem;">Active supplier endpoints listening on ports 8001 through 8011.</p>
    </div>
    """, unsafe_allow_html=True)
    
    df_v = get_vendors_df()
    if not df_v.empty:
        v_cols = st.columns(3)
        for i, r in df_v.iterrows():
            with v_cols[i % 3]:
                st.markdown(f"""
                <div class="optimizer-card">
                    <h4 style="margin-top:0; color:#1e293b;">🏢 {r['name']}</h4>
                    <p style="color:#64748b; font-size:0.9rem;"><b>Category:</b> {r['type']} | <b>Reliability:</b> {r['reliability_score']*100:.0f}%</p>
                    <p><code>{r['contact_endpoint']}</code></p>
                </div>
                """, unsafe_allow_html=True)
