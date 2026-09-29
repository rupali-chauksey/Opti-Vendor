import os
import re
import json
import logging
from typing import TypedDict, Annotated, Optional, List, Dict, Any
import operator
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from tools import query_inventory, fetch_vendors, send_a2a_rfq, execute_order
from engine import check_approval_required, get_product_policy, esc, plan_order, get_inbound_qty, get_inventory_summary_groups

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
    log_msg = f"🧠 [Node 1: Orchestrator] Ingested user query: '{query}'"
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
        if any(k in query for k in ["expir", "waste", "batch", "shelf life", "spoil"]):
            intent = "CHECK_EXPIRY"
            filter_type = "EXPIRING_SOON"
        elif any(k in query for k in ["out of stock", "empty", "zero stock", "no units"]):
            intent = "CHECK_STOCK"
            filter_type = "OUT_OF_STOCK"
        elif any(k in query for k in ["critical", "risk", "days of supply", "urgent"]):
            intent = "CHECK_STOCK"
            filter_type = "CRITICAL_STOCKOUT"
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
        "trace_steps": [f"Node 1 (Orchestrator): Classified intent '{intent}' for target_product='{target_product}' (Requested Qty={target_qty})."]
    }

def shelf_monitor_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 2: Scans Inventory Health & Ingests Strategic Procurement Policy.
    Suppresses product procurement policy trace line when target_product is None.
    """
    intent = state.get("intent")
    filter_type = state.get("filter_type", "OUT_OF_STOCK")
    target_product = state.get("target_product")

    log_msg = f"🛠️ [Node 2: Shelf Monitor] Calling query_inventory(filter_type='{filter_type}', product_name='{target_product}')"
    logging.info(log_msg)

    items = query_inventory(filter_type=filter_type, product_name=target_product)

    if target_product:
        active_name = items[0]["name"] if items else target_product
        pid = items[0]["product_id"] if items else "P-OAT1"
        if intent == "NEGOTIATE_RESTOCK":
            policy = get_product_policy(pid)
            trace_msg = (
                f"Node 2 (Shelf Monitor Agent): Ingested procurement policy for '{active_name}' (PID: {pid}). "
                f"Policy Ceiling Price: ${policy.get('max_unit_price'):.2f}/unit ✓. Scanned {len(items)} matching inventory records."
            )
        else:
            trace_msg = f"Node 2 (Shelf Monitor Agent): Scanned stock level for '{active_name}' ({len(items)} matching records)."
    else:
        active_name = None
        trace_msg = f"Node 2 (Shelf Monitor Agent): Completed full scan across all {len(items)} store catalog products ({len(items)} records monitored)."

    return {
        "inventory_results": items,
        "target_product": active_name,
        "trace_steps": [trace_msg]
    }

def negotiation_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 3: Autonomous Multi-Round A2A Negotiation Loop using Centralized Order Planner.
    Enforces capacity capping and price tier matching upfront (Approval Integrity).
    """
    prod_name = state.get("target_product", "Oat Barista Blend")
    qty = state.get("target_quantity", 100)

    conn_check = query_inventory(filter_type="SPECIFIC_PRODUCT", product_name=prod_name)
    pid = conn_check[0]["product_id"] if conn_check else "P-OAT1"

    # Use single source of truth order planner
    plan = plan_order(product_id=pid, requested_qty=qty)

    if not plan.get("success"):
        fail_msg = plan.get("message", "Could not formulate procurement plan.")
        return {
            "agreed_deal": None,
            "execution_result": {"success": False, "message": fail_msg},
            "trace_steps": [f"Node 3 (A2A Negotiator): Planning halted - {fail_msg}"]
        }

    deal = plan.to_dict()

    deliv_label = f"{plan['delivery_days']} day" if plan['delivery_days'] == 1 else f"{plan['delivery_days']} days"
    trace_list = []

    # Show disqualified vendors if quote exceeded ceiling
    for dq in plan.disqualified_vendors:
        trace_list.append(f"Node 3 (Marketplace Discovery): Disqualified '{dq['name']}': {dq['reason']}.")

    if plan.savings <= 0.0:
        trace_msg = (
            f"Node 3 (A2A Negotiator): Multi-round A2A handshake with '{plan['vendor_name']}' "
            f"(Score: {deal.get('vendor_score', 0.95):.2f}, Delivery: {deliv_label}). "
            f"No volume tier eligible, list price accepted (${plan['unit_price']:.2f}/unit)."
        )
    else:
        trace_msg = (
            f"Node 3 (A2A Negotiator): Multi-round A2A handshake with '{plan['vendor_name']}' "
            f"(Score: {deal.get('vendor_score', 0.95):.2f}, Delivery: {deliv_label}). Agreed Price ${plan['unit_price']:.2f}/unit "
            f"(List Price: ${plan['list_price']:.2f}, Savings: ${plan['cost_saved']:.2f})."
        )
    trace_list.append(trace_msg)

    if plan.get("adjusted"):
        trace_list.append(f"Node 3 (Order Planner Guardrail): {plan['adjustment_reason']}")

    return {
        "agreed_deal": deal,
        "trace_steps": trace_list
    }

def execution_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 4: Budget Guard & Order Execution.
    Ensures approval card matches exact negotiated payload without hidden execution modifications.
    """
    deal = state.get("agreed_deal")
    if not deal:
        return {
            "execution_result": {"success": False, "message": "No deal agreed."},
            "trace_steps": ["Node 4 (Safety Guardrails): Execution skipped - No vendor deal agreed."]
        }

    total_value = deal["total_cost"]

    # Approval Guard Check (> $500 threshold OR 5x recommended quantity rule)
    if deal.get("needs_approval"):
        reasons = deal.get("approval_reasons") or []
        reason_text = " ".join(reasons) if reasons else f"Order total ${total_value:.2f} exceeds $500.00 autonomous threshold."
        log_msg = f"🛑 [Node 4: Budget Guard] Approval required: {reason_text}"
        logging.warning(log_msg)
        return {
            "human_approval_needed": True,
            "execution_result": {
                "success": False,
                "status": "PENDING_APPROVAL",
                "message": f"Human approval required. {reason_text}"
            },
            "trace_steps": [f"Node 4 (Safety Guardrails): Intercepted for Manager Approval ({reason_text})."]
        }

    # Autonomous Execution (< $500 and compliant)
    exec_res = execute_order(
        vendor_id=deal["vendor_id"],
        product_id=deal["product_id"],
        quantity=deal["quantity"],
        price=deal["unit_price"],
        actor="AGENT_PIPELINE",
        savings=deal["cost_saved"],
        list_price=deal["list_price"],
        guard_msg=deal.get("adjustment_reason")
    )

    trace_msg = (
        f"Node 4 (Order Executor): Dispatched PO {exec_res.get('po_id')} "
        f"for {exec_res.get('ordered_quantity')} units of {exec_res.get('product_name')} "
        f"at ${exec_res.get('unit_price'):.2f}/unit (Total: ${exec_res.get('total_value'):.2f}, Status: IN_TRANSIT)."
    )

    return {
        "human_approval_needed": False,
        "execution_result": exec_res,
        "trace_steps": [trace_msg]
    }

def output_formatter_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 5: Deterministic Natural Language Output Formatter.
    Eliminates contradictions between critical, low stock, and optimal items.
    """
    intent = state.get("intent")
    filter_type = state.get("filter_type")
    items = state.get("inventory_results", [])
    deal = state.get("agreed_deal")
    exec_res = state.get("execution_result")
    human_needed = state.get("human_approval_needed", False)

    if intent in ["CHECK_STOCK", "CHECK_EXPIRY"]:
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
        elif intent == "CHECK_EXPIRY" or filter_type in ["EXPIRING_SOON", "EXPIRY_RISK"]:
            exp_items = items if items else query_inventory(filter_type="EXPIRING_SOON")
            if not exp_items:
                final_text = "I checked your store inventory. No items are expiring within the next 7 days."
            else:
                lines = []
                for it in exp_items:
                    days = it.get('days_until_expiry', 0)
                    day_lbl = f"{days} day" if days == 1 else f"{days} days"
                    waste_note = f" (Estimated Waste Risk: ~{it['waste_risk_units']} units)" if it.get("waste_risk_units", 0) > 0 else ""
                    lines.append(f"• **{it['name']} ({it['product_id']})**: {it['stock_quantity']} units left, expires in **{day_lbl}** ({it.get('expiration_date')}){waste_note}.")
                final_text = (
                    "I checked the inventory for expiration risks. Here are the items expiring soon (within 7 days):\n\n"
                    + "\n\n".join(lines)
                    + "\n\nI recommend prioritizing these batches or applying promotional discounts to prevent waste."
                )
        else:
            # Deterministic scan of all store inventory grouped by health status
            groups = get_inventory_summary_groups()
            stockout_arr_prods = groups.get("STOCKOUT_BEFORE_ARRIVAL", [])
            crit_prods = groups.get("CRITICAL_STOCKOUT", [])
            in_transit_prods = groups.get("REPLENISHMENT_IN_TRANSIT", [])
            exp_prods = groups.get("EXPIRY_RISK", [])
            low_prods = groups.get("LOW_STOCK", [])
            over_prods = groups.get("OVERSTOCKED", [])
            opt_prods = groups.get("OPTIMAL", [])

            lines = ["I checked your store inventory. Currently, no items are completely out of stock (0 units).\n"]

            if stockout_arr_prods:
                lines.append("⚠️ **Stockout Before Arrival Warning (Action Required)**:")
                for s in stockout_arr_prods:
                    dos_str = f"{s['days_of_supply']} day" if s['days_of_supply'] == 1.0 else f"{s['days_of_supply']} days"
                    lines.append(f"• **{s['name']} ({s['product_id']})**: Only **{s['stock_quantity']} units** on hand ({dos_str} of supply), but replenishment lead time is 2 days (+{s['inbound_qty']} units inbound). **Shelf will stock out before the shipment arrives!** Suggest expediting transit or ordering an emergency buffer.")
                lines.append("")

            if crit_prods:
                lines.append("🚨 **Critical Stockout Risk (< 1.0 Day of Supply)**:")
                for c in crit_prods:
                    dos_str = f"{c['days_of_supply']} day" if c['days_of_supply'] == 1.0 else f"{c['days_of_supply']} days"
                    lines.append(f"• **{c['name']} ({c['product_id']})**: Only **{c['stock_quantity']} units** left, with a daily sales velocity of **{c['sales_velocity_daily']:.1f} units/day**. This means it has less than 1 day of supply (**{dos_str}**) remaining.")
                lines.append("")

            if in_transit_prods:
                lines.append("🚚 **Replenishment In Transit**:")
                for it in in_transit_prods:
                    lines.append(f"• **{it['name']} ({it['product_id']})**: {it['stock_quantity']} units on-hand, **+{it['inbound_qty']} units IN_TRANSIT** (Target: {it['target_stock_level']}).")
                lines.append("")

            if exp_prods:
                lines.append("⏳ **Expiration Risk (Batch Spoilage Alert)**:")
                for ex in exp_prods:
                    d_exp = ex['days_until_expiry']
                    d_exp_str = f"{d_exp} day" if d_exp == 1 else f"{d_exp} days"
                    lines.append(f"• **{ex['name']} ({ex['product_id']})**: {ex['stock_quantity']} units on hand, expires in **{d_exp_str}** ({ex['expiration_date']}).")
                lines.append("")

            if low_prods:
                lines.append("⚠️ **Low Stock Warnings (< 50% target capacity)**:")
                for l in low_prods:
                    dos_str = f"{l['days_of_supply']} day" if l['days_of_supply'] == 1.0 else f"{l['days_of_supply']} days"
                    lines.append(f"• **{l['name']} ({l['product_id']})**: {l['stock_quantity']} units (Target: {l['target_stock_level']}, {dos_str} supply). Status: LOW_STOCK.")
                lines.append("")

            if over_prods:
                lines.append("📦 **Overstocked Items (> Target Capacity)**:")
                for o in over_prods:
                    lines.append(f"• **{o['name']} ({o['product_id']})**: {o['stock_quantity']} units (Target: {o['target_stock_level']}).")
                lines.append("")

            if opt_prods:
                opt_names = ", ".join([p["name"] for p in opt_prods[:4]])
                lines.append(f"✅ **Optimal / Well-Supplied Items**:\n• {opt_names} and others are operating at healthy inventory levels.")

            final_text = "\n".join(lines)

    elif intent == "NEGOTIATE_RESTOCK":
        if human_needed:
            adj_note = f"\n\nNote: {deal['adjustment_reason']}" if deal.get("adjusted") else ""
            total_val = deal['total_cost']
            reasons = deal.get('approval_reasons') or []
            if reasons:
                approval_cause = f"Because {reasons[0].lower() if (reasons[0].startswith('Total') or reasons[0].startswith('Requested') or reasons[0].startswith('Order')) else reasons[0]}, manager confirmation is required before placing the order."
            else:
                approval_cause = f"Because the order total is **${total_val:.2f}** (which exceeds the **$500.00** autonomous threshold), manager confirmation is required before placing the order."
            final_text = (
                f"⚠️ **Human Approval Required**\n\n"
                f"We negotiated a purchase deal with **{deal['vendor_name']}** for **{deal['quantity']} units** of **{deal['product_name']}** at **${deal['unit_price']:.2f}/unit** (Total: **${total_val:.2f}**).\n\n"
                f"{approval_cause}{adj_note}"
            )
        elif exec_res and exec_res.get("success"):
            warning = f"\n\nNote: {exec_res.get('guard_warning')}" if exec_res.get("guard_warning") else ""
            deliv_days = deal.get('delivery_days', 2)
            deliv_str = f"{deliv_days} day" if deliv_days == 1 else f"{deliv_days} days"
            final_text = (
                f"🤝 Restock Purchase Order Created & Dispatched!\n\n"
                f"- Product: {deal['product_name']}\n"
                f"- Vendor: {deal['vendor_name']}\n"
                f"- PO ID: {exec_res['po_id']}\n"
                f"- Quantity Purchased: {exec_res['ordered_quantity']} units\n"
                f"- Negotiated Price: ${deal['unit_price']:.2f} / unit\n"
                f"- Total PO Cost: ${exec_res['total_value']:.2f}\n"
                f"- Cost Savings: ${deal.get('cost_saved', 0.0):.2f} below standard list price\n"
                f"- Delivery Window: {deliv_str}\n"
                f"- PO Status: **IN_TRANSIT** (Expected Delivery: {exec_res['expected_delivery']}).{warning}"
            )
        else:
            msg = exec_res.get("message", "Negotiation completed without deal.") if exec_res else "No suitable deal could be agreed."
            final_text = f"Negotiation update: {msg}"
    else:
        final_text = "I have processed your store inventory request. All systems are operational."

    logging.info(f"📤 [Response Formatter] Formatted natural language response:\n{final_text}")
    return {"final_response": esc(final_text)}

# --- 3. Routing Conditional Edges ---

def route_after_shelf_monitor(state: AgentState) -> str:
    intent = state.get("intent")
    if intent == "NEGOTIATE_RESTOCK":
        return "negotiation_node"
    return "output_formatter_node"

def route_after_negotiation(state: AgentState) -> str:
    if state.get("agreed_deal"):
        return "execution_node"
    return "output_formatter_node"

# --- 4. Assemble Graph Pipeline ---

workflow = StateGraph(AgentState)

workflow.add_node("orchestrator_node", orchestrator_node)
workflow.add_node("shelf_monitor_node", shelf_monitor_node)
workflow.add_node("negotiation_node", negotiation_node)
workflow.add_node("execution_node", execution_node)
workflow.add_node("output_formatter_node", output_formatter_node)

workflow.set_entry_point("orchestrator_node")

workflow.add_edge("orchestrator_node", "shelf_monitor_node")
workflow.add_conditional_edges("shelf_monitor_node", route_after_shelf_monitor)
workflow.add_conditional_edges("negotiation_node", route_after_negotiation)
workflow.add_edge("execution_node", "output_formatter_node")
workflow.add_edge("output_formatter_node", END)

# Memory Checkpointer
memory = MemorySaver()
optivendor_pipeline = workflow.compile(checkpointer=memory)