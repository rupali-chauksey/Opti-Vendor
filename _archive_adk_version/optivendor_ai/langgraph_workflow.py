import sqlite3
import asyncio
from typing import TypedDict, Annotated, Optional, List, Dict, Any
import operator
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# --- 1. Define the Global State Schema ---
class SupplyChainState(TypedDict):
    query: str
    product_name: str
    quantity: int
    target_price: float
    ceiling_price: float
    stock_status: Optional[Dict[str, Any]]
    vendor_offers: List[Dict[str, Any]]
    current_vendor_index: int
    iteration_count: int
    max_iterations: int
    negotiation_history: Annotated[List[Dict[str, Any]], operator.add]
    accepted_deal: Optional[Dict[str, Any]]
    requires_human_approval: bool
    approval_status: str  # "APPROVED", "REJECTED", "PENDING", "NO_DEAL"
    final_summary: str

# --- 2. Node Implementations ---

def monitor_inventory_node(state: SupplyChainState) -> Dict[str, Any]:
    """Node 1: Inspect SQLite POS database for product stock & velocity."""
    conn = sqlite3.connect('veganflow_store.db')
    cursor = conn.cursor()
    
    prod_query = state.get("product_name")
    
    # Deterministic Guardrail for generic "out of stock" / "low stock" queries
    if not prod_query or any(k in prod_query.lower() for k in ["out of stock", "low stock", "all", "risks", "inventory"]):
        cursor.execute("SELECT name, stock_quantity, sales_velocity_daily FROM products WHERE stock_quantity <= 0 OR (sales_velocity_daily > 0 AND (stock_quantity / sales_velocity_daily) < 1.0)")
        out_items = cursor.fetchall()
        if not out_items:
            conn.close()
            return {
                "stock_status": None,
                "final_summary": "All items are in stock. No restock needed."
            }
        prod_query = out_items[0][0]
    
    cursor.execute("SELECT product_id, name, stock_quantity, sales_velocity_daily, target_stock_level FROM products WHERE name LIKE ?", (f"%{prod_query}%",))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return {
            "stock_status": None,
            "final_summary": "Product not found in inventory."
        }
    
    pid, name, stock, velocity, target = row
    days_supply = round(stock / velocity, 1) if velocity > 0 else 999.0
    
    return {
        "stock_status": {
            "product_id": pid,
            "name": name,
            "stock_quantity": stock,
            "velocity": velocity,
            "target_stock_level": target,
            "days_of_supply": days_supply,
            "is_critical": days_supply < 1.0
        },
        "iteration_count": 0,
        "max_iterations": 3
    }

def fetch_market_vendors_node(state: SupplyChainState) -> Dict[str, Any]:
    """Node 2: Fetch all competing vendors sorted by cheapest wholesale price."""
    stock = state.get("stock_status")
    if not stock:
        return {"vendor_offers": []}
    
    pid = stock["product_id"]
    conn = sqlite3.connect('veganflow_store.db')
    cursor = conn.cursor()
    
    sql = """
    SELECT v.name, o.price_wholesale, o.delivery_days, v.reliability_score, v.contact_endpoint, v.vendor_id
    FROM vendor_offers o
    JOIN vendors v ON o.vendor_id = v.vendor_id
    WHERE o.product_id = ?
    ORDER BY o.price_wholesale ASC
    """
    cursor.execute(sql, (pid,))
    offers = cursor.fetchall()
    conn.close()
    
    formatted_offers = [
        {
            "vendor_name": o[0],
            "price_wholesale": o[1],
            "delivery_days": o[2],
            "reliability": o[3],
            "endpoint": o[4],
            "vendor_id": o[5]
        }
        for o in offers
    ]
    
    return {
        "vendor_offers": formatted_offers,
        "current_vendor_index": 0
    }

def load_strategy_memory_node(state: SupplyChainState) -> Dict[str, Any]:
    """Node 3: Ingest strategic bounds from Long-Term Memory Policy."""
    prod_name = state.get("product_name", "Oat Barista Blend")
    
    # Business logic defaults
    target = 3.40
    ceiling = 3.60
    
    if "Brie" in prod_name:
        target, ceiling = 9.00, 10.00
    elif "Pepperoni" in prod_name:
        target, ceiling = 10.50, 12.00
    elif "Shrimp" in prod_name:
        target, ceiling = 12.50, 14.00
        
    return {
        "target_price": target,
        "ceiling_price": ceiling
    }

def a2a_negotiation_node(state: SupplyChainState) -> Dict[str, Any]:
    """Node 4: Send autonomous A2A Purchase Order offer to currently selected vendor microservice."""
    offers = state.get("vendor_offers", [])
    idx = state.get("current_vendor_index", 0)
    current_iter = state.get("iteration_count", 0) + 1
    
    if idx >= len(offers) or current_iter > state.get("max_iterations", 3):
        return {
            "iteration_count": current_iter,
            "negotiation_history": [{
                "vendor_name": "None",
                "round": current_iter,
                "offered_price": 0.0,
                "status": "EXHAUSTED",
                "message": "Max negotiation iterations reached or vendors exhausted."
            }]
        }
        
    vendor = offers[idx]
    product = state.get("product_name", "Oat Barista Blend")
    qty = state.get("quantity", 100)
    target_price = state.get("target_price", 3.40)
    
    offer_price = min(round(vendor["price_wholesale"] * 0.90, 2), target_price)
    
    reliability = vendor["reliability"]
    base_market = vendor["price_wholesale"]
    min_acceptable = base_market * reliability
    if qty > 50:
        min_acceptable *= 0.95  # Bulk discount
        
    round_log = {
        "vendor_name": vendor["vendor_name"],
        "endpoint": vendor["endpoint"],
        "round": current_iter,
        "offered_price": offer_price,
        "quantity": qty,
        "vendor_floor": round(min_acceptable, 2),
        "message": f"Buyer offered ${offer_price:.2f}/unit"
    }
    
    if offer_price >= min_acceptable:
        days = int((1 / reliability) * 2)
        round_log["status"] = "ACCEPTED"
        round_log["final_price"] = offer_price
        round_log["delivery_days"] = days
        accepted = {
            "vendor_name": vendor["vendor_name"],
            "unit_price": offer_price,
            "quantity": qty,
            "total_cost": round(offer_price * qty, 2),
            "delivery_days": days,
            "vendor_id": vendor["vendor_id"]
        }
        return {
            "iteration_count": current_iter,
            "negotiation_history": [round_log],
            "accepted_deal": accepted
        }
    else:
        counter_offer = round(min_acceptable * 1.05, 2)
        round_log["status"] = "COUNTER_OFFER"
        round_log["counter_offer"] = counter_offer
        round_log["message"] = f"Vendor countered with ${counter_offer:.2f}/unit"
        return {
            "iteration_count": current_iter,
            "negotiation_history": [round_log],
            "accepted_deal": None
        }

def evaluate_deal_node(state: SupplyChainState) -> Dict[str, Any]:
    """Node 5: Evaluate vendor counter-offer against competitor price catalog."""
    if not state.get("negotiation_history"):
        return {}
        
    last_log = state["negotiation_history"][-1]
    
    if last_log.get("status") == "ACCEPTED":
        return {}
        
    counter_price = last_log.get("counter_offer", 999.0)
    offers = state.get("vendor_offers", [])
    idx = state.get("current_vendor_index", 0)
    qty = state.get("quantity", 100)
    ceiling = state.get("ceiling_price", 3.60)
    
    next_idx = idx + 1
    next_vendor_price = offers[next_idx]["price_wholesale"] if next_idx < len(offers) else 999.0
    
    if counter_price <= ceiling and counter_price < next_vendor_price:
        vendor = offers[idx]
        days = int((1 / vendor["reliability"]) * 2)
        accepted = {
            "vendor_name": vendor["vendor_name"],
            "unit_price": counter_price,
            "quantity": qty,
            "total_cost": round(counter_price * qty, 2),
            "delivery_days": days,
            "vendor_id": vendor["vendor_id"]
        }
        return {
            "accepted_deal": accepted,
            "negotiation_history": [{
                "vendor_name": vendor["vendor_name"],
                "round": state.get("iteration_count", 1),
                "offered_price": counter_price,
                "status": "ACCEPTED_COUNTER",
                "final_price": counter_price,
                "message": f"Buyer accepted vendor counter-offer of ${counter_price:.2f}"
            }]
        }
    else:
        return {
            "current_vendor_index": idx + 1
        }

def human_approval_gate_node(state: SupplyChainState) -> Dict[str, Any]:
    """Node 6: Human-in-the-Loop (HITL) Safety Gate for High-Value Purchase Orders (> $500)."""
    deal = state.get("accepted_deal")
    if not deal:
        return {"requires_human_approval": False, "approval_status": "NO_DEAL"}
        
    total_cost = deal.get("total_cost", 0.0)
    if total_cost >= 500.0:
        return {
            "requires_human_approval": True,
            "approval_status": "PENDING"
        }
    else:
        return {
            "requires_human_approval": False,
            "approval_status": "APPROVED"
        }

def execute_order_node(state: SupplyChainState) -> Dict[str, Any]:
    """Node 7: Finalize PO and atomically increment SQLite store inventory."""
    deal = state.get("accepted_deal")
    if not deal or state.get("approval_status") == "REJECTED":
        return {
            "final_summary": "Order cancelled or rejected by Human Gate."
        }
        
    prod_name = state.get("product_name") or state.get("target_product", "Oat Barista Blend")
    qty = deal.get("quantity", state.get("quantity", 100))
    unit_price = deal.get("unit_price", deal.get("final_price_per_unit", 3.30))
    vendor = deal.get("vendor_name", deal.get("vendor", "Earthly Gourmet"))
    total = deal.get("total_cost", qty * unit_price)
    
    try:
        conn = sqlite3.connect('veganflow_store.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET stock_quantity = stock_quantity + ? WHERE name LIKE ?", (qty, f"%{prod_name}%"))
        conn.commit()
        conn.close()
        db_msg = "✅ SQLite POS Inventory successfully updated."
    except Exception as e:
        db_msg = f"⚠️ SQLite write warning: {e}"
        
    summary = (
        f"### 🤝 Deal Finalized & Executed Successfully!\n\n"
        f"- **Supplier:** `{vendor}`\n"
        f"- **Item:** `{prod_name}`\n"
        f"- **Units Purchased:** `{qty}`\n"
        f"- **Negotiated Unit Price:** `${unit_price:.2f}`\n"
        f"- **Total PO Cost:** `${total:.2f}`\n"
        f"- **Delivery Window:** `{deal.get('delivery_days', 2)} days`\n"
        f"- **Inventory Status:** {db_msg}"
    )
    return {"final_summary": summary}

def format_final_response_node(state: SupplyChainState) -> Dict[str, Any]:
    """Node 8: Output formatting node that ensures natural language response and NEVER raw JSON."""
    final_sum = state.get("final_summary")
    if final_sum and not final_sum.startswith("{"):
        return {"final_summary": final_sum}
        
    deal = state.get("accepted_deal")
    if deal:
        clean_text = (
            f"Great news! We have successfully secured a restock deal with {deal['vendor_name']}.\n"
            f"• Product: {state.get('product_name', 'Item')}\n"
            f"• Quantity: {deal['quantity']} units\n"
            f"• Price: ${deal['unit_price']:.2f} per unit (Total: ${deal['total_cost']:.2f})\n"
            f"• Delivery: Within {deal['delivery_days']} business days."
        )
    elif state.get("stock_status") is None:
        clean_text = "All items are in stock. No restock needed."
    else:
        clean_text = "Negotiation concluded without an agreement within budget limits. The store manager will review manually."
        
    return {"final_summary": clean_text}

# --- 3. Routing Conditional Edges ---

def route_after_evaluation(state: SupplyChainState) -> str:
    """
    Cyclic decision edge with strict max_iterations = 3 guardrail.
    Breaks loop immediately if agent cycles 3 times.
    """
    if state.get("accepted_deal"):
        return "human_approval_gate"
    
    idx = state.get("current_vendor_index", 0)
    offers = state.get("vendor_offers", [])
    iter_count = state.get("iteration_count", 0)
    max_iter = state.get("max_iterations", 3)
    
    # Strict cycle breaker: max 3 iterations
    if iter_count >= max_iter or idx >= len(offers) or idx >= 3:
        return "end_no_deal"
        
    return "a2a_negotiate"

def route_after_human_gate(state: SupplyChainState) -> str:
    """Branch based on approval gate status."""
    if state.get("approval_status") == "APPROVED":
        return "execute_order"
    return "format_response"

# --- 4. Build and Compile the LangGraph ---

def build_supply_chain_graph():
    builder = StateGraph(SupplyChainState)
    
    # Register Nodes
    builder.add_node("monitor_inventory", monitor_inventory_node)
    builder.add_node("fetch_vendors", fetch_market_vendors_node)
    builder.add_node("load_strategy_memory", load_strategy_memory_node)
    builder.add_node("a2a_negotiate", a2a_negotiation_node)
    builder.add_node("evaluate_deal", evaluate_deal_node)
    builder.add_node("human_approval_gate", human_approval_gate_node)
    builder.add_node("execute_order", execute_order_node)
    builder.add_node("format_response", format_final_response_node)
    
    # Wire Edges
    builder.set_entry_point("monitor_inventory")
    builder.add_edge("monitor_inventory", "fetch_vendors")
    builder.add_edge("fetch_vendors", "load_strategy_memory")
    builder.add_edge("load_strategy_memory", "a2a_negotiate")
    builder.add_edge("a2a_negotiate", "evaluate_deal")
    
    # Conditional Edge (Loop with max_iterations=3 breaker)
    builder.add_conditional_edges(
        "evaluate_deal",
        route_after_evaluation,
        {
            "human_approval_gate": "human_approval_gate",
            "a2a_negotiate": "a2a_negotiate",
            "end_no_deal": "format_response"
        }
    )
    
    # Conditional Edge (After Human Approval Gate)
    builder.add_conditional_edges(
        "human_approval_gate",
        route_after_human_gate,
        {
            "execute_order": "execute_order",
            "format_response": "format_response"
        }
    )
    
    builder.add_edge("execute_order", "format_response")
    builder.add_edge("format_response", END)
    
    memory = MemorySaver()
    return builder.compile(checkpointer=memory)

supply_chain_graph = build_supply_chain_graph()
