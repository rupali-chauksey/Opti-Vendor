import math
import sqlite3
import datetime
from typing import Dict, Any, List, Tuple, Optional

DB_PATH = "optivendor_store.db"

# ============================================================================
# 1. LATEX / STYLING HELPER
# ============================================================================
def esc(s: Any) -> str:
    """
    Escapes literal $ characters in Markdown text strings to prevent Streamlit
    from accidentally parsing dollar amounts as KaTeX LaTeX math blocks.
    Note: Do NOT call on HTML strings passed to unsafe_allow_html=True.
    """
    if s is None:
        return ""
    return str(s).replace("$", "\\$")

# ============================================================================
# 2. INVENTORY POSITION & INBOUND HELPERS
# ============================================================================
def get_inbound_qty(product_id: str, db_path: str = DB_PATH) -> int:
    """
    Computes total units currently on order (status IN_TRANSIT) for a product.
    """
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT SUM(quantity) FROM purchase_orders WHERE product_id = ? AND status = 'IN_TRANSIT'",
            (product_id,)
        )
        row = cur.fetchone()
        conn.close()
        return int(row[0]) if (row and row[0] is not None) else 0
    except Exception:
        return 0

def get_inventory_position(product_id: str, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Returns inventory position = physical stock on hand + inbound orders.
    """
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT stock_quantity, target_stock_level, sales_velocity_daily FROM inventory WHERE product_id = ?",
            (product_id,)
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return {"stock": 0, "inbound": 0, "position": 0, "target": 100, "velocity": 0.0}
        stock, target, vel = row
        inbound = get_inbound_qty(product_id, db_path)
        return {
            "stock": stock,
            "inbound": inbound,
            "position": stock + inbound,
            "target": target,
            "velocity": vel
        }
    except Exception:
        return {"stock": 0, "inbound": 0, "position": 0, "target": 100, "velocity": 0.0}

# ============================================================================
# 3. DETERMINISTIC HEALTH STATUS ENGINE (EXPIRY & INBOUND AWARE)
# ============================================================================
def compute_health_status(
    stock: float,
    target: float,
    velocity: float = 0.0,
    lead_time: float = 2.0,
    safety_days: float = 2.0,
    days_until_expiry: Optional[int] = None,
    inbound_qty: int = 0
) -> str:
    """
    Computes deterministic inventory health status based on:
    - Expiration Waste Risk: days_until_expiry <= 7 and stock > (velocity * days_until_expiry)
    - Stockout Risk: stock <= 0 OR days_of_supply < lead_time
    - Replenishment in Flight: critical on hand but covered by inbound orders
    - Low Stock: days_of_supply < (lead_time + safety_days) OR stock <= 0.5 * target
    - Overstocked: stock > target
    - Optimal: healthy stock level
    """
    # 1. Expiration Risk check (batch spoilage before it can be sold)
    if days_until_expiry is not None and 0 <= days_until_expiry <= 7:
        units_sellable = velocity * max(1, days_until_expiry)
        if stock > units_sellable:
            return "EXPIRY_RISK"

    # 2. Stockout checks
    if stock <= 0:
        return "CRITICAL_STOCKOUT"

    dos = (stock / velocity) if velocity > 0 else float("inf")

    if dos < lead_time:
        if inbound_qty > 0 and (stock + inbound_qty) >= (0.8 * target):
            return "REPLENISHMENT_IN_TRANSIT"
        return "CRITICAL_STOCKOUT"

    if stock > target:
        return "OVERSTOCKED"

    if dos < (lead_time + safety_days) or stock <= (0.5 * target):
        return "LOW_STOCK"

    return "OPTIMAL"

# ============================================================================
# 4. LEAD-TIME-AWARE REORDER QUANTITY ENGINE
# ============================================================================
def compute_reorder_qty(
    stock: float,
    target: float,
    velocity: float = 0.0,
    lead_time: float = 2.0,
    moq: int = 1,
    inbound_qty: int = 0
) -> int:
    """
    Computes exact reorder quantity accounting for inventory position and lead time sales:
    Formula: Needed = (Target - (Stock + Inbound)) + (Sales Velocity * Lead Time)
    """
    position = stock + inbound_qty
    needed = (target - position) + (velocity * lead_time)
    if needed <= 0:
        return 0
    if moq > 1:
        return math.ceil(needed / moq) * moq
    return int(needed)

# ============================================================================
# 5. DETERMINISTIC APPROVAL GUARD ENGINE
# ============================================================================
def check_approval_required(total_value: float, threshold: float = 500.0) -> bool:
    """
    Single source of truth for human-in-the-loop approval guard.
    Returns True if total order value exceeds the autonomous threshold ($500.00).
    """
    return total_value > threshold

# ============================================================================
# 6. PRODUCT PROCUREMENT POLICY & PRICE CEILING ENFORCEMENT
# ============================================================================
PRODUCT_POLICIES = {
    "P-OAT1": {"name": "Oat Barista Blend", "target_price": 3.30, "max_unit_price": 3.80, "target_stock": 100},
    "P-ALMD": {"name": "Almond Milk Unsweetened", "target_price": 2.70, "max_unit_price": 3.20, "target_stock": 60},
    "P-BRIE": {"name": "Cultured Truffle Brie", "target_price": 8.00, "max_unit_price": 9.20, "target_stock": 30},
    "P-CHED": {"name": "Aged Smoked Cheddar Block", "target_price": 6.20, "max_unit_price": 7.50, "target_stock": 50},
    "P-SHMP": {"name": "Vegan Jumbo Shrimp", "target_price": 12.00, "max_unit_price": 14.50, "target_stock": 25},
    "P-PEPR": {"name": "Seitan Pepperoni (Bulk)", "target_price": 6.80, "max_unit_price": 8.20, "target_stock": 80},
    "P-SAUS": {"name": "Plant-Based Sausage Links", "target_price": 5.50, "max_unit_price": 6.80, "target_stock": 100},
    "P-YGRT": {"name": "Vanilla Coconut Yogurt", "target_price": 2.80, "max_unit_price": 3.50, "target_stock": 40},
    "P-TEMH": {"name": "Artisanal Organic Tempeh", "target_price": 3.80, "max_unit_price": 4.80, "target_stock": 35},
    "P-MAYO": {"name": "Egg-Free Mayo Large Jar", "target_price": 4.20, "max_unit_price": 5.20, "target_stock": 60},
}

def get_product_policy(product_id: str) -> Dict[str, Any]:
    """Returns product policy rules or default safeguards."""
    return PRODUCT_POLICIES.get(
        product_id,
        {"name": "Unknown Product", "target_price": 5.0, "max_unit_price": 999.0, "target_stock": 100}
    )

# Category Compatibility Rules (Prevents e.g. Dry Goods vendors supplying Fresh Dairy Alternatives)
CATEGORY_COMPATIBILITY = {
    "Beverage": ["Beverage", "Dairy Alternative"],
    "Dairy Alternative": ["Dairy Alternative", "Beverage"],
    "Cheese Alternative": ["Cheese Alternative", "Dairy Alternative"],
    "Meat Alternative": ["Meat Alternative"],
    "Seafood Alternative": ["Seafood Alternative"],
    "Dry Goods": ["Dry Goods", "General Grocery"],
}

# ============================================================================
# 7. WEIGHTED VENDOR SELECTION & SCORING ENGINE
# ============================================================================
def score_vendor_candidate(
    price: float,
    list_price: float,
    reliability: float,
    delivery_days: int,
    max_unit_price: Optional[float] = None,
    product_category: Optional[str] = None,
    vendor_category: Optional[str] = None
) -> Tuple[float, str, Dict[str, float]]:
    """
    Computes composite vendor score:
    - Price Score (50%): Savings relative to standard list price
    - Reliability Score (30%): Historical vendor SLA & fulfillment rate
    - Delivery Speed Score (20%): Fast shipping penalty reduction
    
    Disqualification triggers:
    1. Category mismatch (e.g. Dry Goods vendor quoting on Dairy Alternative)
    2. Price exceeds product policy ceiling
    """
    # Check category compatibility
    if product_category and vendor_category:
        allowed_cats = CATEGORY_COMPATIBILITY.get(product_category, [product_category])
        if vendor_category not in allowed_cats:
            return 0.0, f"DISQUALIFIED (Category mismatch: Vendor is '{vendor_category}', Product requires '{product_category}')", {}

    # Check policy ceiling
    if max_unit_price and price > max_unit_price:
        return 0.0, f"DISQUALIFIED (Price ${price:.2f} > Policy Ceiling ${max_unit_price:.2f})", {}
    
    list_ref = max(list_price, price)
    price_score = max(0.0, min(1.0, 1.0 - ((price - (list_ref * 0.7)) / max(0.01, (list_ref * 0.6)))))
    reliability_score = max(0.0, min(1.0, reliability))
    speed_score = max(0.0, min(1.0, 1.0 - (delivery_days / 10.0)))
    
    total_score = round((price_score * 0.50) + (reliability_score * 0.30) + (speed_score * 0.20), 3)
    
    breakdown = {
        "price_score": round(price_score, 2),
        "reliability_score": round(reliability_score, 2),
        "speed_score": round(speed_score, 2),
        "total_score": total_score
    }
    
    return total_score, "QUALIFIED", breakdown

# ============================================================================
# 8. UNIFIED MULTI-ROUND A2A NEGOTIATION ENGINE
# ============================================================================
def negotiate_a2a_multi_round(
    vendor_name: str,
    list_price: float,
    quantity: int,
    target_price: float = 3.30,
    max_unit_price: Optional[float] = None
) -> Dict[str, Any]:
    """
    Single source of truth multi-round negotiation engine.
    Price tier strictly matches the FINAL quantity negotiated:
    - >= 100 units: 10% volume discount tier
    - >= 50 units: 5% bulk discount tier
    - < 50 units: 0% standard list price
    """
    vendor_floor = round(list_price * 0.82, 2)
    
    if quantity >= 100:
        disc_rate = 0.10
    elif quantity >= 50:
        disc_rate = 0.05
    else:
        disc_rate = 0.00
        
    agreed_unit_price = max(vendor_floor, round(list_price * (1.0 - disc_rate), 2))
    
    rounds = [
        {
            "round": 1,
            "buyer_bid": round(list_price * 0.88, 2),
            "vendor_counter": round(list_price * 0.96, 2),
            "status": "COUNTER_OFFER"
        },
        {
            "round": 2,
            "buyer_bid": round(target_price, 2),
            "vendor_counter": agreed_unit_price,
            "status": "COUNTER_OFFER"
        },
        {
            "round": 3,
            "buyer_bid": agreed_unit_price,
            "vendor_counter": agreed_unit_price,
            "status": "DEAL_SEALED"
        }
    ]
    
    exceeds_ceiling = max_unit_price is not None and (agreed_unit_price > max_unit_price)
    status = "REJECTED_CEILING_EXCEEDED" if exceeds_ceiling else "ACCEPTED"
    
    total_cost = round(agreed_unit_price * quantity, 2)
    list_total = round(list_price * quantity, 2)
    savings = round(list_total - total_cost, 2)
    
    return {
        "vendor_name": vendor_name,
        "negotiated_price": agreed_unit_price,
        "list_price": list_price,
        "quantity": quantity,
        "total_cost": total_cost,
        "list_total": list_total,
        "savings": max(0.0, savings),
        "status": status,
        "policy_compliant": not exceeds_ceiling,
        "max_unit_price": max_unit_price,
        "rounds": rounds
    }

negotiate_a2a_round = negotiate_a2a_multi_round

# ============================================================================
# 9. CENTRALIZED ORDER PLANNER (APPROVAL INTEGRITY & INVENTORY POSITION AWARE)
# ============================================================================
def plan_order(
    product_id: str,
    requested_quantity: Optional[int] = None,
    db_path: str = DB_PATH
) -> Dict[str, Any]:
    """
    Central decision engine that unifies capacity capping, vendor scoring,
    multi-round negotiation, and approval gating.
    Both Chat and War Room use this to ensure what is negotiated, displayed,
    and approved is EXACTLY what gets executed.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT name, category, stock_quantity, sales_velocity_daily, target_stock_level, expiration_date FROM inventory WHERE product_id = ?",
        (product_id,)
    )
    prod = cur.fetchone()
    if not prod:
        conn.close()
        return {"success": False, "message": f"Product {product_id} not found."}

    name, p_cat, stock, vel, target, exp_date_str = prod
    inbound = get_inbound_qty(product_id, db_path)
    position = stock + inbound
    headroom = max(0, target - position)

    # Shelf life constraint: units that can be sold before current batch expires
    shelf_life_days = 999
    if exp_date_str:
        try:
            exp_date = datetime.date.fromisoformat(exp_date_str)
            shelf_life_days = max(1, (exp_date - datetime.date.today()).days)
        except Exception:
            pass

    # 1. Determine Final Quantity Upfront (Approval Integrity)
    adjusted = False
    adjustment_reason = None

    if requested_quantity is not None:
        if headroom <= 0:
            final_quantity = 0
            adjusted = True
            adjustment_reason = f"Inventory position ({position} units: {stock} on hand + {inbound} inbound) already fulfills target capacity ({target} units). Restock not required."
        elif requested_quantity > headroom:
            final_quantity = headroom
            adjusted = True
            adjustment_reason = f"Requested {requested_quantity} units exceeds available target capacity ({headroom} units headroom). Order capped to {final_quantity} units."
        else:
            final_quantity = requested_quantity
    else:
        # Auto-recommend reorder quantity accounting for inbound and lead-time sales
        suggested = compute_reorder_qty(stock, target, vel, lead_time=2.0, inbound_qty=inbound)
        final_quantity = max(0, min(headroom, suggested))

    if final_quantity <= 0:
        conn.close()
        return {
            "success": False,
            "product_id": product_id,
            "product_name": name,
            "current_stock": stock,
            "inbound_qty": inbound,
            "inventory_position": position,
            "target_stock": target,
            "final_quantity": 0,
            "adjusted": adjusted,
            "adjustment_reason": adjustment_reason or "No reorder needed.",
            "message": adjustment_reason or "Stock level is already optimal."
        }

    # 2. Vendor Marketplace Discovery & Scoring
    policy = get_product_policy(product_id)
    cur.execute("""
        SELECT v.vendor_id, v.name, v.category, v.reliability_score, v.endpoint_url,
               vo.price_wholesale, vo.delivery_days
        FROM vendors v
        JOIN vendor_offers vo ON v.vendor_id = vo.vendor_id
        WHERE vo.product_id = ?
    """, (product_id,))
    vendor_rows = cur.fetchall()
    conn.close()

    scored_vendors = []
    for vr in vendor_rows:
        v_id, v_name, v_cat, rel, endp, list_p, del_days = vr
        score, status, breakdown = score_vendor_candidate(
            price=list_p,
            list_price=list_p,
            reliability=rel,
            delivery_days=del_days,
            max_unit_price=policy.get("max_unit_price"),
            product_category=p_cat,
            vendor_category=v_cat
        )
        if status == "QUALIFIED":
            scored_vendors.append({
                "vendor_id": v_id,
                "name": v_name,
                "category": v_cat,
                "reliability_score": rel,
                "endpoint_url": endp,
                "price_wholesale": list_p,
                "delivery_days": del_days,
                "total_score": score,
                "breakdown": breakdown
            })

    scored_vendors.sort(key=lambda x: x["total_score"], reverse=True)
    if not scored_vendors:
        return {
            "success": False,
            "product_id": product_id,
            "product_name": name,
            "final_quantity": final_quantity,
            "message": "No qualified vendors found meeting category and policy ceiling constraints."
        }

    top_vendor = scored_vendors[0]

    # 3. Multi-Round Negotiation on the FINAL Quantity
    neg = negotiate_a2a_multi_round(
        vendor_name=top_vendor["name"],
        list_price=top_vendor["price_wholesale"],
        quantity=final_quantity,
        target_price=policy.get("target_price", 3.30),
        max_unit_price=policy.get("max_unit_price")
    )

    total_cost = neg["total_cost"]
    raw_requested_val = round((requested_quantity or final_quantity) * neg["negotiated_price"], 2)
    needs_approval = check_approval_required(total_cost, threshold=500.0) or check_approval_required(raw_requested_val, threshold=500.0)

    return {
        "success": True,
        "product_id": product_id,
        "product_name": name,
        "category": p_cat,
        "current_stock": stock,
        "inbound_qty": inbound,
        "inventory_position": position,
        "target_stock": target,
        "requested_quantity": requested_quantity or final_quantity,
        "final_quantity": final_quantity,
        "adjusted": adjusted,
        "adjustment_reason": adjustment_reason,
        "vendor_id": top_vendor["vendor_id"],
        "vendor_name": top_vendor["name"],
        "vendor_endpoint": top_vendor["endpoint_url"],
        "vendor_score": top_vendor["total_score"],
        "unit_price": neg["negotiated_price"],
        "list_price": neg["list_price"],
        "total_cost": total_cost,
        "list_total": neg["list_total"],
        "cost_saved": neg["savings"],
        "delivery_days": top_vendor["delivery_days"],
        "needs_approval": needs_approval,
        "rounds": neg["rounds"],
        "status": neg["status"],
        "scored_vendors": scored_vendors
    }
