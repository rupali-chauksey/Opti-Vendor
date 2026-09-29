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
    Computes deterministic inventory health status:
    - CRITICAL_STOCKOUT: stock <= 0 OR days_of_supply < lead_time
    - LOW_STOCK: days_of_supply < (lead_time + safety_days) OR stock <= 0.5 * target
    - OVERSTOCKED: stock > target
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
# 3. DETERMINISTIC REORDER QUANTITY ENGINE
# ============================================================================
def compute_reorder_qty(stock: float, target: float, velocity: float = 0.0, lead_time: float = 2.0, moq: int = 1) -> int:
    """
    Computes exact reorder quantity required to reach target inventory level
    accounting for lead time sales velocity and minimum order quantity (MOQ).
    """
    needed = (target - stock) + (velocity * lead_time)
    if needed <= 0:
        return 0
    return math.ceil(needed / moq) * moq

# ============================================================================
# 4. DETERMINISTIC APPROVAL GUARD ENGINE
# ============================================================================
def check_approval_required(total_value: float, threshold: float = 500.0) -> bool:
    """
    Single source of truth for human-in-the-loop approval guard.
    Returns True if order value exceeds the autonomous threshold ($500.00).
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
    
    # Calculate component scores (0.0 to 1.0)
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
# 7. REALISTIC MULTI-ROUND A2A NEGOTIATION MATH
# ============================================================================
def negotiate_a2a_round(
    vendor_offer: Dict[str, Any],
    quantity: int,
    round_num: int = 1,
    max_unit_price: Optional[float] = None
) -> Dict[str, Any]:
    """
    Simulates multi-round A2A negotiation logic:
    - Round 1: Vendor standard list price / offer
    - Round 2: Buyer requests volume discount (-10%), vendor counters based on floor margin
    - Round 3: Final buyer target deal or walkaway
    """
    list_price = vendor_offer.get("price_wholesale", 5.0)
    vendor_floor = list_price * 0.82  # Vendor minimum acceptable margin (18% max discount)
    
    if round_num == 1:
        if quantity >= 50:
            offered_price = max(vendor_floor, list_price * 0.90)
        else:
            offered_price = list_price
    elif round_num == 2:
        offered_price = max(vendor_floor, list_price * 0.85)
    else:
        offered_price = max(vendor_floor, list_price * 0.83)
    
    offered_price = round(offered_price, 2)
    
    # Check policy ceiling
    exceeds_policy = max_unit_price and (offered_price > max_unit_price)
    
    return {
        "round": round_num,
        "negotiated_price": offered_price,
        "list_price": list_price,
        "unit_savings": round(list_price - offered_price, 2),
        "total_savings": round((list_price - offered_price) * quantity, 2),
        "total_cost": round(offered_price * quantity, 2),
        "list_total": round(list_price * quantity, 2),
        "policy_compliant": not exceeds_policy
    }
