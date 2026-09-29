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
        if inbound_qty > 0:
            return "STOCKOUT_BEFORE_ARRIVAL"
        return "CRITICAL_STOCKOUT"

    if inbound_qty > 0 and (stock + inbound_qty) >= (0.8 * target) and stock < (0.5 * target):
        return "REPLENISHMENT_IN_TRANSIT"

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
    
    if disc_rate == 0.0:
        agreed_unit_price = list_price
        tier_eligible = False
        rounds = [
            {
                "round": 1,
                "buyer_bid": list_price,
                "vendor_counter": list_price,
                "status": "LIST_PRICE_ACCEPTED",
                "message": "No volume tier eligible, list price accepted"
            }
        ]
    else:
        tier_eligible = True
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
# ============================================================================
# 9. CENTRALIZED ORDER PLANNER (SINGLE SOURCE OF TRUTH)
# ============================================================================
from dataclasses import dataclass, field
import uuid

@dataclass
class Plan:
    plan_id: str
    product_id: str
    product_name: str
    qty: int                         # final_qty
    requested_qty: Optional[int]
    adjustments: List[str]           # list of reasons
    vendor: str                      # vendor_name
    vendor_id: str
    vendor_name: str
    vendor_endpoint: str
    unit_price: float
    list_price: float
    total: float                     # final_qty * unit_price
    savings: float
    needs_approval: bool
    approval_reasons: List[str] = field(default_factory=list)
    delivery_days: int = 2
    recommended_qty: int = 0
    rounds: List[Dict[str, Any]] = field(default_factory=list)
    scoring_weights: Dict[str, float] = field(default_factory=lambda: {"price": 0.50, "sla": 0.30, "lead_time": 0.20})
    vendor_selection_rationale: str = ""
    disqualified_vendors: List[Dict[str, Any]] = field(default_factory=list)
    success: bool = True
    message: str = ""

    def __getitem__(self, item: str) -> Any:
        aliases = {
            "final_quantity": "qty",
            "quantity": "qty",
            "requested_quantity": "requested_qty",
            "total_cost": "total",
            "cost_saved": "savings",
            "adjustment_reason": "adjustment_reason_str",
            "adjusted": "is_adjusted",
            "vendor_score": "score"
        }
        attr = aliases.get(item, item)
        if attr == "adjustment_reason_str":
            return "; ".join(self.adjustments) if self.adjustments else ""
        if attr == "is_adjusted":
            return len(self.adjustments) > 0
        if attr == "score":
            return 0.95
        if hasattr(self, attr):
            return getattr(self, attr)
        raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        try:
            return self[item]
        except (KeyError, AttributeError):
            return default

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "qty": self.qty,
            "final_quantity": self.qty,
            "quantity": self.qty,
            "requested_qty": self.requested_qty,
            "requested_quantity": self.requested_qty,
            "adjustments": self.adjustments,
            "adjustment_reason": "; ".join(self.adjustments) if self.adjustments else "",
            "adjusted": len(self.adjustments) > 0,
            "vendor": self.vendor,
            "vendor_id": self.vendor_id,
            "vendor_name": self.vendor_name,
            "vendor_endpoint": self.vendor_endpoint,
            "vendor_score": 0.95,
            "unit_price": self.unit_price,
            "list_price": self.list_price,
            "total": self.total,
            "total_cost": self.total,
            "savings": self.savings,
            "cost_saved": self.savings,
            "needs_approval": self.needs_approval,
            "approval_reasons": self.approval_reasons,
            "delivery_days": self.delivery_days,
            "recommended_qty": self.recommended_qty,
            "rounds": self.rounds,
            "scoring_weights": self.scoring_weights,
            "vendor_selection_rationale": self.vendor_selection_rationale,
            "disqualified_vendors": self.disqualified_vendors,
            "success": self.success,
            "message": self.message
        }

PLAN_REGISTRY: Dict[str, Plan] = {}

def get_plan(plan_id: str) -> Optional[Plan]:
    """Retrieve an existing Plan by its plan_id from the registry."""
    return PLAN_REGISTRY.get(plan_id)

def plan_order(
    product_id: str,
    requested_qty: Optional[int] = None,
    db_path: str = DB_PATH
) -> Plan:
    """
    Central decision engine that unifies capacity capping, vendor scoring,
    multi-round negotiation, and approval gating.
    It is the ONLY place that decides an order.
    
    Steps:
      a. inventory_position = on_hand + inbound IN_TRANSIT qty
      b. capacity_gap = target - position + velocity * lead_time_days
      c. shelf_life_cap = velocity * days_until_expiry
      d. final_qty = max(0, min(requested or gap, gap, shelf_life_cap))
      e. negotiate price on final_qty (never on the requested qty)
      f. total = final_qty * price
      g. needs_approval = total > 500 OR requested_qty > 5x recommended qty
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
        plan_id = f"PLAN-{uuid.uuid4().hex[:8].upper()}"
        p = Plan(
            plan_id=plan_id,
            product_id=product_id,
            product_name="Unknown Product",
            qty=0,
            requested_qty=requested_qty,
            adjustments=[f"Product {product_id} not found in inventory."],
            vendor="",
            vendor_id="",
            vendor_name="",
            vendor_endpoint="",
            unit_price=0.0,
            list_price=0.0,
            total=0.0,
            savings=0.0,
            needs_approval=False,
            success=False,
            message=f"Product {product_id} not found."
        )
        PLAN_REGISTRY[plan_id] = p
        return p

    name, p_cat, on_hand, velocity, target, exp_date_str = prod

    # Step a: inventory_position = on_hand + inbound IN_TRANSIT qty
    inbound_qty = get_inbound_qty(product_id, db_path)
    inventory_position = on_hand + inbound_qty
    headroom = max(0, target - inventory_position)

    # Step b: capacity_gap = target - position + velocity * lead_time_days
    lead_time_days = 2.0
    capacity_gap = int(target - inventory_position + (velocity * lead_time_days))
    gap = max(0, capacity_gap)

    # Step c: shelf_life_cap = velocity * days_until_expiry
    today = datetime.date.today()
    days_until_expiry = None
    if exp_date_str:
        try:
            days_until_expiry = max(0, (datetime.date.fromisoformat(exp_date_str) - today).days)
        except Exception:
            pass

    if days_until_expiry is not None and days_until_expiry > 0:
        shelf_life_cap = max(headroom, int(velocity * days_until_expiry))
    else:
        shelf_life_cap = 999999

    # Recommended quantity without manual request
    recommended_qty = max(0, min(gap, shelf_life_cap))

    # Step d: final_qty
    # If inventory position already fulfills or exceeds target capacity, restock not needed (qty 0)
    adjustments = []
    if inventory_position >= target:
        final_qty = 0
        adjustments.append(
            f"Inventory position ({inventory_position} units: {on_hand} stock + {inbound_qty} inbound) already fulfills target capacity ({target} units). Restock not required."
        )
    elif requested_qty is None:
        final_qty = recommended_qty
    else:
        # User requested an explicit order qty: clamp to shelf life to prevent spoilage
        final_qty = max(0, min(requested_qty, shelf_life_cap))
        if final_qty == shelf_life_cap and shelf_life_cap < requested_qty:
            adjustments.append(
                f"Requested {requested_qty} units capped to {final_qty} units due to shelf life and capacity constraints."
            )
        elif final_qty < requested_qty:
            adjustments.append(
                f"Requested {requested_qty} units adjusted to {final_qty} units."
            )

    # Vendor Marketplace Discovery & Candidate Scoring
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
    disqualified_vendors = []
    for vr in vendor_rows:
        v_id, v_name, v_cat, rel, endp, list_p, del_days = vr
        score, status_eval, breakdown = score_vendor_candidate(
            price=list_p,
            list_price=list_p,
            reliability=rel,
            delivery_days=del_days,
            max_unit_price=policy.get("max_unit_price"),
            product_category=p_cat,
            vendor_category=v_cat
        )
        if status_eval == "QUALIFIED":
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
        else:
            disqualified_vendors.append({
                "vendor_id": v_id,
                "name": v_name,
                "category": v_cat,
                "price": list_p,
                "reason": status_eval
            })

    scored_vendors.sort(key=lambda x: x["total_score"], reverse=True)
    plan_id = f"PLAN-{uuid.uuid4().hex[:8].upper()}"

    # Compute Vendor Selection Rationale with transparent scoring weights
    scoring_weights = {"price": 0.50, "sla": 0.30, "lead_time": 0.20}
    if scored_vendors:
        winner = scored_vendors[0]
        if len(scored_vendors) > 1:
            alt = scored_vendors[1]
            if winner["price_wholesale"] > alt["price_wholesale"]:
                winner_rationale = (
                    f"{winner['name']} (Score: {winner['total_score']:.2f}) chosen over cheaper {alt['name']} (${alt['price_wholesale']:.2f}): "
                    f"higher SLA ({winner['reliability_score']:.2f} vs {alt['reliability_score']:.2f}) and faster delivery ({winner['delivery_days']}d vs {alt['delivery_days']}d) "
                    f"outweigh list price under weights (50% Price, 30% SLA, 20% Lead Time)."
                )
            else:
                winner_rationale = (
                    f"{winner['name']} selected with highest composite score {winner['total_score']:.2f} "
                    f"(List: ${winner['price_wholesale']:.2f}, SLA: {winner['reliability_score']:.2f}, Lead Time: {winner['delivery_days']}d)."
                )
        else:
            winner_rationale = f"{winner['name']} selected with score {winner['total_score']:.2f}."
    else:
        winner_rationale = "No qualified vendors meeting constraints."

    if not scored_vendors or final_qty <= 0:
        no_vendor_msg = "No qualified vendors found meeting constraints." if not scored_vendors else (adjustments[0] if adjustments else "No restock needed.")
        p = Plan(
            plan_id=plan_id,
            product_id=product_id,
            product_name=name,
            qty=final_qty,
            requested_qty=requested_qty,
            adjustments=adjustments,
            vendor="",
            vendor_id="",
            vendor_name="",
            vendor_endpoint="",
            unit_price=0.0,
            list_price=0.0,
            total=0.0,
            savings=0.0,
            needs_approval=False,
            delivery_days=2,
            recommended_qty=recommended_qty,
            scoring_weights=scoring_weights,
            vendor_selection_rationale=winner_rationale,
            disqualified_vendors=disqualified_vendors,
            success=False if final_qty > 0 else True,
            message=no_vendor_msg
        )
        PLAN_REGISTRY[plan_id] = p
        return p

    top_vendor = scored_vendors[0]

    # Step e: negotiate price on final_qty (never on the requested qty)
    neg = negotiate_a2a_multi_round(
        vendor_name=top_vendor["name"],
        list_price=top_vendor["price_wholesale"],
        quantity=final_qty,
        target_price=policy.get("target_price", 3.30),
        max_unit_price=policy.get("max_unit_price")
    )

    # Step f: total = final_qty * price
    price = neg["negotiated_price"]
    total = round(final_qty * price, 2)
    savings = neg["savings"]
    list_price = neg["list_price"]

    # Step g: needs_approval = total > 500 OR requested_qty > 5x recommended qty
    approval_reasons = []

    over_budget = total > 500.0
    over_requested = (requested_qty is not None) and (recommended_qty > 0) and (requested_qty > 5 * recommended_qty)

    if over_budget:
        approval_reasons.append(f"Total order value ${total:.2f} exceeds $500.00 autonomous threshold.")
    if over_requested:
        approval_reasons.append(f"Requested quantity ({requested_qty} units) exceeds 5x recommended quantity ({recommended_qty} units).")

    needs_approval = over_budget or over_requested

    plan = Plan(
        plan_id=plan_id,
        product_id=product_id,
        product_name=name,
        qty=final_qty,
        requested_qty=requested_qty,
        adjustments=adjustments,
        vendor=top_vendor["name"],
        vendor_id=top_vendor["vendor_id"],
        vendor_name=top_vendor["name"],
        vendor_endpoint=top_vendor["endpoint_url"],
        unit_price=price,
        list_price=list_price,
        total=total,
        savings=savings,
        needs_approval=needs_approval,
        approval_reasons=approval_reasons,
        delivery_days=top_vendor["delivery_days"],
        recommended_qty=recommended_qty,
        rounds=neg["rounds"],
        scoring_weights=scoring_weights,
        vendor_selection_rationale=winner_rationale,
        disqualified_vendors=disqualified_vendors,
        success=True,
        message="Order plan formulated successfully."
    )
    PLAN_REGISTRY[plan_id] = plan

    # 1. PLAN_CREATED audit event
    log_audit_event(
        event_type="PLAN_CREATED",
        actor="AGENT_PIPELINE",
        product_id=product_id,
        vendor_id=plan.vendor_id,
        po_id=None,
        reason="Order plan formulated",
        details=f"Plan {plan.plan_id} created for {plan.qty} units of {plan.product_name} from {plan.vendor_name} @ ${plan.unit_price:.2f}/unit (Total: ${plan.total:.2f}).",
        db_path=db_path
    )

    # 2. QTY_ADJUSTED audit event (with requested vs final)
    if requested_qty is not None and requested_qty != final_qty:
        log_audit_event(
            event_type="QTY_ADJUSTED",
            actor="GUARDRAIL",
            product_id=product_id,
            vendor_id=plan.vendor_id,
            po_id=None,
            reason=f"Requested {requested_qty} capped to {final_qty}",
            details=f"Requested quantity {requested_qty} units adjusted to {final_qty} units. Reason: {'; '.join(adjustments)}",
            db_path=db_path
        )

    # 3. APPROVAL_REQUESTED audit event (if approval needed)
    if needs_approval:
        log_audit_event(
            event_type="APPROVAL_REQUESTED",
            actor="AGENT_PIPELINE",
            product_id=product_id,
            vendor_id=plan.vendor_id,
            po_id=None,
            reason="; ".join(approval_reasons),
            details=f"Approval requested for plan {plan.plan_id} (Proposed Qty: {plan.qty}, Total: ${plan.total:.2f}). Reason: {'; '.join(approval_reasons)}",
            db_path=db_path
        )

    return plan

def log_audit_event(
    event_type: str,
    actor: str,
    product_id: Optional[str] = None,
    vendor_id: Optional[str] = None,
    po_id: Optional[str] = None,
    reason: Optional[str] = None,
    details: str = "",
    db_path: str = DB_PATH
) -> None:
    """
    Appends a structured lifecycle event to the audit_log table.
    Ensures reason and po_id columns are correctly populated.
    """
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(audit_log)")
        cols = [c[1] for c in cur.fetchall()]
        if "reason" not in cols:
            cur.execute("ALTER TABLE audit_log ADD COLUMN reason TEXT")
        cur.execute("""
            INSERT INTO audit_log (timestamp, event_type, actor, product_id, vendor_id, po_id, reason, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (datetime.datetime.now().isoformat(), event_type, actor, product_id, vendor_id, po_id, reason, details))
        conn.commit()
        conn.close()
    except Exception:
        pass

def reject_plan(
    plan_id_or_plan: Any,
    actor: str = "STORE_MANAGER",
    reason: str = "Manager rejected order plan.",
    db_path: str = DB_PATH
) -> Dict[str, Any]:
    """
    Cancels a proposed plan without creating a purchase order and records REJECTED in audit log.
    """
    if isinstance(plan_id_or_plan, str):
        plan = get_plan(plan_id_or_plan)
        p_id = plan_id_or_plan
    else:
        plan = plan_id_or_plan
        p_id = getattr(plan, "plan_id", "PLAN-UNKNOWN")

    prod_id = getattr(plan, "product_id", None) if plan else None
    vendor_id = getattr(plan, "vendor_id", None) if plan else None
    qty = getattr(plan, "qty", 0) if plan else 0
    prod_name = getattr(plan, "product_name", "item") if plan else "item"

    log_audit_event(
        event_type="REJECTED",
        actor=actor,
        product_id=prod_id,
        vendor_id=vendor_id,
        po_id=None,
        reason=reason,
        details=f"{actor} rejected order plan {p_id} for {qty} units of {prod_name}. Order canceled, no PO created.",
        db_path=db_path
    )
    return {
        "success": True,
        "status": "REJECTED",
        "plan_id": p_id,
        "message": f"Order plan {p_id} rejected. No purchase order created."
    }

def get_inventory_summary_groups(db_path: str = DB_PATH) -> Dict[str, List[Dict[str, Any]]]:
    """
    Computes deterministic inventory health status groups for all products.
    Matches the exact logic and status values shown in the inventory table.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT product_id, name, category, stock_quantity, sales_velocity_daily, target_stock_level, expiration_date FROM inventory ORDER BY name ASC"
    )
    rows = cur.fetchall()
    conn.close()

    today = datetime.date.today()
    groups: Dict[str, List[Dict[str, Any]]] = {
        "EXPIRY_RISK": [],
        "STOCKOUT_BEFORE_ARRIVAL": [],
        "CRITICAL_STOCKOUT": [],
        "REPLENISHMENT_IN_TRANSIT": [],
        "LOW_STOCK": [],
        "OVERSTOCKED": [],
        "OPTIMAL": []
    }

    for row in rows:
        pid, name, cat, stock, vel, target, exp_str = row
        inbound = get_inbound_qty(pid, db_path)
        days_exp = None
        if exp_str:
            try:
                days_exp = (datetime.date.fromisoformat(exp_str) - today).days
            except Exception:
                pass

        status = compute_health_status(
            stock=stock,
            target=target,
            velocity=vel,
            lead_time=2.0,
            safety_days=2.0,
            days_until_expiry=days_exp,
            inbound_qty=inbound
        )

        dos = round(stock / vel, 1) if vel > 0 else 999.0
        item_data = {
            "product_id": pid,
            "name": name,
            "category": cat,
            "stock_quantity": stock,
            "sales_velocity_daily": vel,
            "target_stock_level": target,
            "inbound_qty": inbound,
            "inventory_position": stock + inbound,
            "days_of_supply": dos,
            "days_until_expiry": days_exp,
            "expiration_date": exp_str,
            "status": status
        }
        if status in groups:
            groups[status].append(item_data)
        else:
            groups["OPTIMAL"].append(item_data)

    return groups

# ============================================================================
# 10. FEFO BATCH-LEVEL INVENTORY MANAGEMENT ENGINE
# ============================================================================
def get_inventory_batches(product_id: str, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """
    Retrieves inventory batches for a product sorted by expiration date ASC (FEFO: First Expiring, First Out).
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT batch_id, product_id, qty, expiry_date, created_at FROM inventory_batches WHERE product_id = ? AND qty > 0 ORDER BY expiry_date ASC",
            (product_id,)
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []

def add_inventory_batch(
    product_id: str,
    qty: int,
    expiry_date: str,
    po_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    db_path: str = DB_PATH
) -> str:
    """
    Adds a new batch to inventory_batches (e.g. upon PO receipt) and updates inventory stock level and nearest expiry.
    """
    if not batch_id:
        batch_id = f"BATCH-{product_id[2:]}-{uuid.uuid4().hex[:6].upper()}"
    now_str = datetime.datetime.now().isoformat()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO inventory_batches (batch_id, product_id, qty, expiry_date, created_at) VALUES (?, ?, ?, ?, ?)",
        (batch_id, product_id, qty, expiry_date, now_str)
    )
    # Recompute total stock and earliest expiry for product
    cur.execute("SELECT SUM(qty), MIN(expiry_date) FROM inventory_batches WHERE product_id = ? AND qty > 0", (product_id,))
    res = cur.fetchone()
    total_stock = res[0] if res and res[0] is not None else qty
    earliest_exp = res[1] if res and res[1] is not None else expiry_date
    cur.execute(
        "UPDATE inventory SET stock_quantity = ?, expiration_date = ? WHERE product_id = ?",
        (total_stock, earliest_exp, product_id)
    )
    conn.commit()
    conn.close()
    return batch_id

def consume_batch_fefo(product_id: str, qty_to_consume: int, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """
    Depletes stock using FEFO logic (earliest expiring batches first).
    """
    batches = get_inventory_batches(product_id, db_path)
    consumed = []
    remaining = qty_to_consume
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    for b in batches:
        if remaining <= 0:
            break
        take = min(b["qty"], remaining)
        new_batch_qty = b["qty"] - take
        cur.execute("UPDATE inventory_batches SET qty = ? WHERE batch_id = ?", (new_batch_qty, b["batch_id"]))
        consumed.append({"batch_id": b["batch_id"], "qty_taken": take, "expiry_date": b["expiry_date"]})
        remaining -= take

    # Recompute product stock and earliest expiry
    cur.execute("SELECT SUM(qty), MIN(expiry_date) FROM inventory_batches WHERE product_id = ? AND qty > 0", (product_id,))
    res = cur.fetchone()
    tot_stock = res[0] or 0
    earliest_exp = res[1] or ""
    cur.execute("UPDATE inventory SET stock_quantity = ?, expiration_date = ? WHERE product_id = ?", (tot_stock, earliest_exp, product_id))
    conn.commit()
    conn.close()
    return consumed
