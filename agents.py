import os
import re
import json
import logging
from typing import TypedDict, Annotated, Optional, List, Dict, Any
import operator
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from tools import query_inventory, fetch_vendors, send_a2a_rfq, execute_order

# Configure Trace Logging
logging.basicConfig(
    filename="agent_trace.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

# --- 1. Define Global State Schema ---
class AgentState(TypedDict):
    user_query: str
    intent: str
    filter_type: str
    target_product: Optional[str]
    target_quantity: int
    inventory_results: List[Dict[str, Any]]
    vendor_candidates: List[Dict[str, Any]]
    current_vendor_index: int
    iteration_count: int
    max_iterations: int
    negotiation_log: Annotated[List[Dict[str, Any]], operator.add]
    agreed_deal: Optional[Dict[str, Any]]
    execution_result: Optional[Dict[str, Any]]
    human_approval_needed: bool
    final_response: str
    trace_steps: Annotated[List[str], operator.add]

# --- 2. Node Implementations ---

def orchestrator_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 1: Classifies Intent with strict Entity Extraction & Quantity Extraction.
    """
    query = state.get("user_query", "").strip().lower()
    log_msg = f"🧠 [Orchestrator] Ingested user query: '{query}'"
    logging.info(log_msg)

    intent = "CHECK_STOCK"
    filter_type = "OUT_OF_STOCK"
    target_product = None
    target_qty = state.get("target_quantity", 100) or 100

    # --- QUANTITY EXTRACTION ---
    extracted_qty = None
    m_qty = re.search(r'(?:order\s*quantity|quantity|order|qty|units?|amount|count)\s*[:=]?\s*(\d+)', query)
    if m_qty:
        extracted_qty = int(m_qty.group(1))
    else:
        m_unit = re.search(r'(\d+)\s*(?:units?|pieces?|pcs?|packs?|quantity|qty|set karein|set)', query)
        if m_unit:
            extracted_qty = int(m_unit.group(1))
        else:
            m_num = re.search(r'\b(\d+)\b', query)
            if m_num and any(k in query for k in ["order", "buy", "purchase", "restock", "negotiate", "replenish", "set"]):
                extracted_qty = int(m_num.group(1))

    if extracted_qty and extracted_qty > 0:
        target_qty = extracted_qty

    # --- PRODUCT CATALOG ---
    catalog_map = [
        ("Vegan Jumbo Shrimp", ["vegan jumbo shrimp", "jumbo shrimp", "shrimp"]),
        ("Oat Barista Blend", ["oat barista blend", "oat barista", "oat milk"]),
        ("Cultured Truffle Brie", ["cultured truffle brie", "truffle brie", "brie"]),
        ("Aged Smoked Cheddar Block", ["aged smoked cheddar", "smoked cheddar", "cheddar"]),
        ("Seitan Pepperoni (Bulk)", ["seitan pepperoni", "pepperoni"]),
        ("Plant-Based Sausage Links", ["plant-based sausage", "sausage links", "sausage"]),
        ("Vanilla Coconut Yogurt", ["vanilla coconut yogurt", "coconut yogurt", "yogurt"]),
        ("Artisanal Organic Tempeh", ["artisanal organic tempeh", "organic tempeh", "tempeh"]),
        ("Egg-Free Mayo Large Jar", ["egg-free mayo", "vegan mayo", "mayo"]),
        ("Almond Milk Unsweetened", ["almond milk unsweetened", "almond milk"])
    ]

    for canonical_name, aliases in catalog_map:
        if any(alias in query for alias in aliases):
            target_product = canonical_name
            break

    if target_product:
        filter_type = "SPECIFIC_PRODUCT"
        if any(k in query for k in ["negotiate", "buy", "purchase", "order", "restock", "replenish", "set karein", "set", "quantity"]):
            intent = "NEGOTIATE_RESTOCK"
        else:
            intent = "CHECK_STOCK"
    else:
        if any(k in query for k in ["out of stock", "empty", "zero stock", "no units"]):
            intent = "CHECK_STOCK"
            filter_type = "OUT_OF_STOCK"
        elif any(k in query for k in ["critical", "risk", "days of supply", "urgent"]):
            intent = "CHECK_STOCK"
            filter_type = "CRITICAL_STOCKOUT"
        elif any(k in query for k in ["expir", "waste", "batch"]):
            intent = "CHECK_STOCK"
            filter_type = "EXPIRING_SOON"
        elif any(k in query for k in ["negotiate", "buy", "purchase", "order", "restock", "replenish", "set"]):
            intent = "NEGOTIATE_RESTOCK"
            filter_type = "SPECIFIC_PRODUCT"
            target_product = "Oat Barista Blend"
        else:
            intent = "CHECK_STOCK"
            filter_type = "OUT_OF_STOCK"

    return {
        "intent": intent,
        "filter_type": filter_type,
        "target_product": target_product,
        "target_quantity": target_qty,
        "iteration_count": 0,
        "max_iterations": 3,
        "trace_steps": [f"Orchestrator identified target_product='{target_product}' with filter '{filter_type}', quantity={target_qty}"]
    }


def shelf_monitor_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 2: Executes query_inventory tool and checks Days of Supply.
    """
    filter_type = state.get("filter_type", "OUT_OF_STOCK")
    target_product = state.get("target_product")

    log_msg = f"🛠️ [Shelf Monitor] Calling query_inventory(filter_type='{filter_type}', product_name='{target_product}')"
    logging.info(log_msg)

    items = query_inventory(filter_type=filter_type, product_name=target_product)

    if filter_type == "OUT_OF_STOCK" and not items:
        crit_items = query_inventory(filter_type="CRITICAL_STOCKOUT")
    else:
        crit_items = []

    trace_msg = f"Shelf Monitor scanned database. Found {len(items)} matching items."
    if crit_items:
        trace_msg += f" (Identified {len(crit_items)} critical risk SKUs)."

    return {
        "inventory_results": items,
        "target_product": items[0]["name"] if items else (crit_items[0]["name"] if crit_items else target_product),
        "trace_steps": [trace_msg]
    }


def negotiation_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 3: Autonomous Multi-Round A2A Negotiation Loop with Vendors.
    """
    prod_name = state.get("target_product", "Oat Barista Blend")
    qty = state.get("target_quantity", 100)
    cur_iter = state.get("iteration_count", 0) + 1
    idx = state.get("current_vendor_index", 0)

    vendors = state.get("vendor_candidates", [])
    if not vendors:
        conn_check = query_inventory(filter_type="SPECIFIC_PRODUCT", product_name=prod_name)
        pid = conn_check[0]["product_id"] if conn_check else "P-OAT1"
        vendors = fetch_vendors(product_id=pid)

    if idx >= len(vendors) or cur_iter > state.get("max_iterations", 3):
        log_msg = f"⚠️ [Negotiation] Loop limit ({cur_iter}) reached or vendors exhausted."
        logging.warning(log_msg)
        return {
            "iteration_count": cur_iter,
            "trace_steps": ["Negotiation loop reached maximum iterations limit (3)."]
        }

    vendor = vendors[idx]
    endpoint = vendor.get("endpoint_url", "http://localhost:8001/a2a")
    pid = vendor.get("product_id", "P-OAT1")
    list_p = vendor.get("price_wholesale", 3.80)
    target_p = round(list_p * 0.90, 2)

    rfq_result = send_a2a_rfq(vendor_endpoint=endpoint, product_id=pid, quantity=qty, target_unit_price=target_p)

    log_msg = f"💬 [A2A Handshake] Round {cur_iter} with {rfq_result.get('vendor_name')}: Status={rfq_result.get('status')}, Price=${rfq_result.get('negotiated_price')}"
    logging.info(log_msg)

    deal = None
    if rfq_result.get("status") in ["ACCEPTED", "COUNTER_ACCEPTED"]:
        deal = {
            "vendor_id": vendor.get("vendor_id", "V-EARTH"),
            "vendor_name": rfq_result.get("vendor_name"),
            "product_id": pid,
            "product_name": prod_name,
            "quantity": qty,
            "unit_price": rfq_result.get("negotiated_price"),
            "total_cost": rfq_result.get("total_cost"),
            "cost_saved": rfq_result.get("cost_saved"),
            "delivery_days": rfq_result.get("delivery_days")
        }

    return {
        "vendor_candidates": vendors,
        "iteration_count": cur_iter,
        "current_vendor_index": idx + 1,
        "negotiation_log": [rfq_result],
        "agreed_deal": deal,
        "trace_steps": [f"A2A RFQ sent to {rfq_result.get('vendor_name')}: Agreed Price ${rfq_result.get('negotiated_price')}/unit (Savings: ${rfq_result.get('cost_saved')})"]
    }


def execution_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 4: Budget Guard (checks ORIGINAL value) → Human Approval OR Execute Order.
    Overstocking Guard fires inside execute_order().
    """
    deal = state.get("agreed_deal")
    if not deal:
        return {
            "execution_result": {"success": False, "message": "No deal agreed."},
            "trace_steps": ["Execution skipped: No finalized vendor deal."]
        }

    raw_qty = deal.get("quantity", 100)
    unit_p = deal.get("unit_price", 3.42)
    # ORIGINAL requested value (before any overstocking reduction)
    original_value = round(raw_qty * unit_p, 2)

    # ============================================
    # GUARD: BUDGET (checks ORIGINAL value)
    # ============================================
    if original_value > 500.0:
        log_msg = f"🛑 [Budget Guard] Original order value ${original_value:.2f} ({raw_qty} units @ ${unit_p:.2f}) > $500. Human approval required."
        logging.warning(log_msg)
        return {
            "human_approval_needed": True,
            "execution_result": {
                "success": False,
                "status": "PENDING_APPROVAL",
                "message": f"Human approval required. Original order value ${original_value:.2f} exceeds the $500 autonomous threshold."
            },
            "trace_steps": [f"Budget Guard: Original value ${original_value:.2f} > $500 requires manager authorization."]
        }

    # ============================================
    # EXECUTE ORDER (Overstocking Guard fires inside)
    # ============================================
    exec_res = execute_order(
        vendor_id=deal.get("vendor_id", "V-EARTH"),
        product_id=deal.get("product_id", "P-OAT1"),
        quantity=raw_qty,
        price=unit_p
    )

    logging.info(f"📦 [Execution] Order committed to SQLite: {exec_res.get('message')}")

    return {
        "execution_result": exec_res,
        "trace_steps": [f"Executed order: {exec_res.get('message')}"]
    }


def output_formatter_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 5: Synthesizes raw outputs into natural language. NEVER outputs raw JSON.
    """
    intent = state.get("intent")
    filter_type = state.get("filter_type")
    items = state.get("inventory_results", [])
    deal = state.get("agreed_deal")
    exec_res = state.get("execution_result")
    human_needed = state.get("human_approval_needed", False)

    # --- STOCK CHECK ---
    if intent == "CHECK_STOCK":
        if filter_type == "SPECIFIC_PRODUCT":
            if not items:
                final_text = f"Product '{state.get('target_product', 'requested item')}' not found in store inventory."
            else:
                it = items[0]
                vel = it['sales_velocity_daily']
                vel_str = f"{vel:.0f} unit/day" if vel == 1 else f"{vel:.1f} units/day"
                dos = it['days_of_supply']
                days_str = f"{dos:.0f}" if float(dos).is_integer() else f"{dos:.1f}"
                final_text = (
                    f"**{it['name']}** has **{it['stock_quantity']} units left**, "
                    f"**{vel_str} velocity**, and **{days_str} days of supply**. "
                    f"Status: **{it.get('status', 'OPTIMAL')}**."
                )
        elif filter_type == "EXPIRING_SOON":
            if not items:
                final_text = "I checked your store inventory. No items are expiring within the next 7 days."
            else:
                lines = [
                    f"• **{it['name']} ({it['product_id']})**: {it['stock_quantity']} units left, expires in **{it['days_until_expiry']} day{'s' if it['days_until_expiry'] != 1 else ''}** ({it.get('expiration_date')})."
                    for it in items
                ]
                final_text = (
                    "I checked the inventory for expiration risks. Here are the items expiring soon (within 7 days):\n\n"
                    + "\n".join(lines)
                    + "\n\nI recommend prioritizing these batches or applying promotional discounts to prevent waste."
                )
        elif not items:
            crit = query_inventory(filter_type="CRITICAL_STOCKOUT")
            if not crit:
                final_text = (
                    "I checked your store inventory. Currently, all items are in stock and operating at optimal levels. "
                    "No immediate restock is required."
                )
            else:
                c = crit[0]
                final_text = (
                    "I checked your store inventory. Currently, no items are completely out of stock (0 units).\n\n"
                    "However, I found one **Critical Stockout Risk**:\n\n"
                    f"• **{c['name']} ({c['product_id']})**: Only **{c['stock_quantity']} units** left, with a daily sales velocity of **{c['sales_velocity_daily']} units/day**. "
                    f"This means it has less than 1 day of supply (**{c['days_of_supply']} days**) remaining.\n\n"
                    f"I strongly recommend immediately initiating a reorder for {c['name']}. All other products are at optimal levels."
                )
        else:
            lines = [f"• **{it['name']} ({it['product_id']})**: {it['stock_quantity']} units in stock (Status: {it.get('status', 'CRITICAL')}, Days of Supply: {it.get('days_of_supply', 0)} days)." for it in items]
            final_text = f"Here are the Critical Stockout and inventory scan results:\n\n" + "\n".join(lines)

    # --- NEGOTIATE RESTOCK ---
    elif intent == "NEGOTIATE_RESTOCK":
        if human_needed:
            final_text = (
                f"⚠️ **Human Approval Required**\n\n"
                f"We negotiated a purchase deal with **{deal['vendor_name']}** for **{deal['quantity']} units** of **{deal['product_name']}** at **${deal['unit_price']:.2f}/unit**.\n\n"
                f"Because the total order value is **${deal['total_cost']:.2f}** (which exceeds the **$500.00** autonomous threshold), manager confirmation is required before placing the order."
            )
        elif exec_res and exec_res.get("success"):
            warning = f"\n\nNote: {exec_res.get('guard_warning')}" if exec_res.get("guard_warning") else ""
            final_text = (
                f"🤝 Restock Deal Finalized & Inventory Replenished!\n\n"
                f"- Product: {deal['product_name']}\n"
                f"- Vendor: {deal['vendor_name']}\n"
                f"- Quantity Purchased: {exec_res['ordered_quantity']} units\n"
                f"- Negotiated Price: ${deal['unit_price']:.2f} / unit\n"
                f"- Total PO Cost: ${exec_res['total_value']:.2f}\n"
                f"- Cost Savings: ${deal.get('cost_saved', 0.0):.2f} below standard list price\n"
                f"- Inventory Status: Successfully updated in POS. New stock: {exec_res['updated_stock']} units.{warning}"
            )
        else:
            msg = exec_res.get("message", "Negotiation completed without deal.") if exec_res else "No suitable deal could be agreed."
            final_text = f"Negotiation update: {msg}"
    else:
        final_text = "I have processed your store inventory request. All systems are operational."

    logging.info(f"📤 [Response Formatter] Formatted natural language response:\n{final_text}")
    return {"final_response": final_text}


# --- 3. Routing Conditional Edges ---

def route_after_orchestrator(state: AgentState) -> str:
    intent = state.get("intent")
    if intent == "NEGOTIATE_RESTOCK":
        return "negotiation_node"
    return "shelf_monitor_node"


def route_after_negotiation(state: AgentState) -> str:
    if state.get("agreed_deal"):
        return "execution_node"

    cur_iter = state.get("iteration_count", 0)
    max_iter = state.get("max_iterations", 3)
    if cur_iter >= max_iter:
        return "output_formatter_node"

    return "negotiation_node"


# --- 4. Build StateGraph ---

def build_veganflow_agent_graph():
    builder = StateGraph(AgentState)

    builder.add_node("orchestrator_node", orchestrator_node)
    builder.add_node("shelf_monitor_node", shelf_monitor_node)
    builder.add_node("negotiation_node", negotiation_node)
    builder.add_node("execution_node", execution_node)
    builder.add_node("output_formatter_node", output_formatter_node)

    builder.set_entry_point("orchestrator_node")

    builder.add_conditional_edges(
        "orchestrator_node",
        route_after_orchestrator,
        {
            "shelf_monitor_node": "shelf_monitor_node",
            "negotiation_node": "negotiation_node"
        }
    )

    builder.add_edge("shelf_monitor_node", "output_formatter_node")

    builder.add_conditional_edges(
        "negotiation_node",
        route_after_negotiation,
        {
            "execution_node": "execution_node",
            "negotiation_node": "negotiation_node",
            "output_formatter_node": "output_formatter_node"
        }
    )

    builder.add_edge("execution_node", "output_formatter_node")
    builder.add_edge("output_formatter_node", END)

    memory = MemorySaver()
    return builder.compile(checkpointer=memory)


veganflow_pipeline = build_veganflow_agent_graph()