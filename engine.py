import math
import sqlite3
import datetime
from typing import Dict, Any, List, Tuple, Optional

# ============================================================================
# 1. LATEX / STYLING HELPER
# ============================================================================
def esc(s: Any) -> str:
    """
    Escapes literal $ characters in text strings to prevent Streamlit
    from accidentally parsing dollar amounts as KaTeX LaTeX math blocks.
    """
    if s is None:
        return ""
    return str(s).replace("$", "\\$")

# ============================================================================
# 2. DETERMINISTIC HEALTH STATUS ENGINE
# ============================================================================
def compute_health_status(stock: float, target: float, velocity: float = 0.0, lead_time: float = 2.0, safety_days: float = 2.0) -> str:
    """
    Computes deterministic inventory health status based on Days of Supply (DoS) and stock level %:
    - CRITICAL_STOCKOUT: stock <= 0 OR days_of_supply < lead_time
    - OVERSTOCKED: stock > target
    - LOW_STOCK: days_of_supply < (lead_time + safety_days) OR stock <= 0.5 * target
    - OPTIMAL: stock level is healthy and well-supplied
    """
    if stock <= 0:
        return "CRITICAL_STOCKOUT"
    if stock > target:
        return "OVERSTOCKED"
    
    dos = (stock / velocity) if velocity > 0 else float("inf")
    
    if dos < lead_time:
        return "CRITICAL_STOCKOUT"
    
    if dos < (lead_time + safety_days) or stock <= (0.5 * target):
        return "LOW_STOCK"
    
    return "OPTIMAL"

# ============================================================================
# 3. LEAD-TIME-AWARE REORDER QUANTITY ENGINE
# ============================================================================
def compute_reorder_qty(stock: float, target: float, velocity: float = 0.0, lead_time: float = 2.0, moq: int = 1) -> int:
    """
    Computes exact reorder quantity required to reach target stock accounting for lead time sales demand.
    Formula: Needed = (Target - Stock) + (Sales Velocity * Lead Time)
    """
    needed = (target - stock) + (velocity * lead_time)
    if needed <= 0:
        return 0
    if moq > 1:
        return math.ceil(needed / moq) * moq
    return int(needed)

# ============================================================================
# 4. DETERMINISTIC APPROVAL GUARD ENGINE
# ============================================================================
def check_approval_required(total_value: float, threshold: float = 500.0) -> bool:
    """
    Single source of truth for human-in-the-loop approval guard.
    Returns True if total order value exceeds the autonomous threshold ($500.00).
    """
    return total_value > threshold

# ============================================================================
# 5. PRODUCT PROCUREMENT POLICY & PRICE CEILING ENFORCEMENT
# ============================================================================
PRODUCT_POLICIES = {
    "P-OAT1": {"name": "Oat Barista Blend", "max_unit_price": 4.50, "target_stock": 100},
    "P-ALMD": {"name": "Almond Milk Unsweetened", "max_unit_price": 3.20, "target_stock": 60},
    "P-BRIE": {"name": "Cultured Truffle Brie", "max_unit_price": 10.50, "target_stock": 30},
    "P-CHED": {"name": "Aged Smoked Cheddar Block", "max_unit_price": 8.00, "target_stock": 50},
    "P-SHMP": {"name": "Vegan Jumbo Shrimp", "max_unit_price": 16.00, "target_stock": 25},
    "P-PEPR": {"name": "Seitan Pepperoni (Bulk)", "max_unit_price": 9.00, "target_stock": 80},
    "P-SAUS": {"name": "Plant-Based Sausage Links", "max_unit_price": 7.50, "target_stock": 100},
    "P-YGRT": {"name": "Vanilla Coconut Yogurt", "max_unit_price": 4.00, "target_stock": 40},
    "P-TEMH": {"name": "Artisanal Organic Tempeh", "max_unit_price": 5.00, "target_stock": 35},
    "P-MAYO": {"name": "Egg-Free Mayo Large Jar", "max_unit_price": 6.00, "target_stock": 60},
}

def get_product_policy(product_id: str) -> Dict[str, Any]:
    """Returns product policy rules or default safeguards."""
    return PRODUCT_POLICIES.get(product_id, {"name": "Unknown Product", "max_unit_price": 999.0, "target_stock": 100})

# ============================================================================
# 6. WEIGHTED VENDOR SELECTION & SCORING ENGINE
# ============================================================================
def score_vendor_candidate(
    price: float,
    list_price: float,
    reliability: float,
    delivery_days: int,
    max_unit_price: Optional[float] = None
) -> Tuple[float, str, Dict[str, float]]:
    """
    Computes composite vendor score:
    - Price Score (50%): Savings relative to standard list price
    - Reliability Score (30%): Historical vendor SLA & fulfillment rate
    - Delivery Speed Score (20%): Fast shipping penalty reduction
    
    If unit price exceeds product ceiling policy, candidate is disqualified.
    """
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
# 7. UNIFIED MULTI-ROUND A2A NEGOTIATION ENGINE (SHARED FOR ALL PATHS)
# ============================================================================
def negotiate_a2a_multi_round(
    vendor_name: str,
    list_price: float,
    quantity: int,
    target_price: float = 3.30,
    max_unit_price: Optional[float] = None
) -> Dict[str, Any]:
    """
    Single source of truth multi-round negotiation engine used by BOTH War Room and Chat.
    - Round 1: Buyer opening bid (list_price * 0.88), Vendor counter (list_price * 0.96)
    - Round 2: Buyer target bid, Vendor volume discount counter
    - Round 3: Sealed final deal if compliant with max_unit_price policy ceiling.
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
