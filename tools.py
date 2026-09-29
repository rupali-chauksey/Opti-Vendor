import sqlite3
from typing import List, Dict, Any, Optional
import datetime
import uuid
from engine import compute_health_status

DB_PATH = "optivendor_store.db"

def query_inventory(filter_type: str = "OUT_OF_STOCK", product_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Queries the SQLite inventory database and computes Days of Supply.
    
    Args:
        filter_type: One of 'OUT_OF_STOCK', 'CRITICAL_STOCKOUT', 'EXPIRING_SOON', or 'SPECIFIC_PRODUCT'.
        product_name: The name or substring of the product (required for 'SPECIFIC_PRODUCT').
        
    Returns:
        List of matching inventory dictionary records. Returns [] if no matching items exist.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    norm_filter = (filter_type or "OUT_OF_STOCK").upper().strip()
    results = []

    if norm_filter == "OUT_OF_STOCK":
        # 0 units stock
        cursor.execute("""
            SELECT product_id, name, category, stock_quantity, sales_velocity_daily, target_stock_level, vendor_id
            FROM inventory
            WHERE stock_quantity <= 0
        """)
        rows = cursor.fetchall()
        for r in rows:
            d = dict(r)
            d["days_of_supply"] = 0.0
            d["status"] = "OUT_OF_STOCK"
            results.append(d)

    elif norm_filter == "CRITICAL_STOCKOUT":
        # Days of Supply < 1.0 day
        cursor.execute("""
            SELECT product_id, name, category, stock_quantity, sales_velocity_daily, target_stock_level, vendor_id
            FROM inventory
            WHERE sales_velocity_daily > 0 AND (stock_quantity * 1.0 / sales_velocity_daily) < 1.0
        """)
        rows = cursor.fetchall()
        for r in rows:
            d = dict(r)
            d["days_of_supply"] = round(d["stock_quantity"] / d["sales_velocity_daily"], 1)
            d["status"] = "CRITICAL_STOCKOUT"
            results.append(d)

    elif norm_filter == "EXPIRING_SOON":
        # Calculate days_until_expiry = expiration_date - today and return items where days_until_expiry <= 7
        cursor.execute("""
            SELECT product_id, name, category, stock_quantity, sales_velocity_daily, target_stock_level, vendor_id, expiration_date
            FROM inventory
        """)
        rows = cursor.fetchall()
        today = datetime.date.today()
        
        for r in rows:
            d = dict(r)
            exp_str = d.get("expiration_date")
            if exp_str:
                try:
                    exp_date = datetime.date.fromisoformat(exp_str)
                    days_until_exp = (exp_date - today).days
                    if 0 <= days_until_exp <= 7:
                        d["days_until_expiry"] = days_until_exp
                        d["status"] = "EXPIRING_SOON"
                        results.append(d)
                except Exception:
                    pass
        # Sort by nearest expiry first
        results.sort(key=lambda x: x.get("days_until_expiry", 999))

    elif norm_filter == "SPECIFIC_PRODUCT":
        if not product_name:
            conn.close()
            return []
            
        cursor.execute("""
            SELECT product_id, name, category, stock_quantity, sales_velocity_daily, target_stock_level, vendor_id
            FROM inventory
            WHERE name LIKE ? OR product_id = ?
        """, (f"%{product_name}%", product_name))
        rows = cursor.fetchall()
        for r in rows:
            d = dict(r)
            velocity = d["sales_velocity_daily"]
            d["days_of_supply"] = round(d["stock_quantity"] / velocity, 1) if velocity > 0 else 999.0
            d["status"] = compute_health_status(d["stock_quantity"], d["target_stock_level"], velocity)
            results.append(d)

    conn.close()
    return results

def fetch_vendors(category: Optional[str] = None, product_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetches competing vendors from database, optionally filtered by category or product.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if product_id:
        cursor.execute("""
            SELECT v.vendor_id, v.name, v.category, v.reliability_score, v.endpoint_url,
                   vo.price_wholesale, vo.delivery_days, vo.product_id
            FROM vendors v
            JOIN vendor_offers vo ON v.vendor_id = vo.vendor_id
            WHERE vo.product_id = ?
            ORDER BY vo.price_wholesale ASC
        """, (product_id,))
    elif category:
        cursor.execute("SELECT * FROM vendors WHERE category LIKE ? ORDER BY reliability_score DESC", (f"%{category}%",))
    else:
        cursor.execute("SELECT * FROM vendors ORDER BY reliability_score DESC")

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def send_a2a_rfq(vendor_endpoint: str, product_id: str, quantity: int, target_unit_price: float = 3.30) -> Dict[str, Any]:
    """
    Simulates an Autonomous A2A (Agent-to-Agent) Request For Quotation negotiation handshake.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT v.name, v.reliability_score, vo.price_wholesale, vo.delivery_days
        FROM vendors v
        JOIN vendor_offers vo ON v.vendor_id = vo.vendor_id
        WHERE vo.product_id = ? AND v.endpoint_url = ?
    """, (product_id, vendor_endpoint))
    res = cursor.fetchone()
    conn.close()

    if not res:
        return {
            "vendor_endpoint": vendor_endpoint,
            "status": "REJECTED",
            "message": "Vendor does not stock this product SKU.",
            "final_price": 0.0,
            "delivery_days": 0
        }

    v_name, reliability, list_price, base_delivery = res

    # Vendor pricing logic based on volume and reliability
    vendor_floor = round(list_price * reliability * (0.95 if quantity >= 50 else 1.0), 2)
    
    if target_unit_price >= vendor_floor:
        agreed_price = target_unit_price
        status = "ACCEPTED"
    else:
        counter = round(vendor_floor * 1.02, 2)
        agreed_price = counter
        status = "COUNTER_ACCEPTED"

    total_cost = round(agreed_price * quantity, 2)
    standard_cost = round(list_price * quantity, 2)
    savings = round(standard_cost - total_cost, 2)

    return {
        "vendor_name": v_name,
        "vendor_endpoint": vendor_endpoint,
        "product_id": product_id,
        "quantity": quantity,
        "list_price": list_price,
        "negotiated_price": agreed_price,
        "total_cost": total_cost,
        "delivery_days": base_delivery,
        "cost_saved": max(0.0, savings),
        "status": status
    }

def execute_order(vendor_id: str, product_id: str, quantity: int, price: float) -> Dict[str, Any]:
    """
    Executes PO, logs purchase order & audit trail, and updates store inventory in SQLite with overstocking protection.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name, stock_quantity, target_stock_level FROM inventory WHERE product_id = ?", (product_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"success": False, "message": f"Product {product_id} not found."}

    name, cur_stock, target_stock = row

    # Overstocking Guard
    max_allowed = target_stock - cur_stock
    actual_qty = quantity
    guard_msg = None

    if max_allowed <= 0:
        conn.close()
        return {
            "success": False,
            "message": f"Stock is already at or above target capacity ({cur_stock} units vs target {target_stock} units). No restock needed."
        }

    if quantity > max_allowed and max_allowed > 0:
        actual_qty = max_allowed
        guard_msg = f"Overstocking blocked. Current stock: {cur_stock}, Target: {target_stock}. Maximum allowed order is {max_allowed} units. Order reduced from {quantity} to {max_allowed} units."

    total_cost = round(actual_qty * price, 2)
    now_str = datetime.datetime.now().isoformat()
    po_id = f"PO-{uuid.uuid4().hex[:8].upper()}"

    # 1. Update inventory
    cursor.execute("UPDATE inventory SET stock_quantity = stock_quantity + ? WHERE product_id = ?", (actual_qty, product_id))
    
    # 2. Insert into purchase_orders
    cursor.execute("""
        INSERT INTO purchase_orders (po_id, product_id, vendor_id, quantity, unit_price, total_cost, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (po_id, product_id, vendor_id, actual_qty, price, total_cost, "RECEIVED", now_str, now_str))

    # 3. Insert into audit_log
    audit_msg = f"Executed PO {po_id}: {actual_qty} units of {name} from {vendor_id} @ ${price:.2f}/unit (Total: ${total_cost:.2f})."
    if guard_msg:
        audit_msg += f" [{guard_msg}]"
        
    cursor.execute("""
        INSERT INTO audit_log (timestamp, event_type, product_id, vendor_id, details)
        VALUES (?, ?, ?, ?, ?)
    """, (now_str, "ORDER_EXECUTED", product_id, vendor_id, audit_msg))

    conn.commit()
    
    cursor.execute("SELECT stock_quantity FROM inventory WHERE product_id = ?", (product_id,))
    new_stock = cursor.fetchone()[0]
    conn.close()

    return {
        "success": True,
        "po_id": po_id,
        "product_id": product_id,
        "product_name": name,
        "ordered_quantity": actual_qty,
        "unit_price": price,
        "total_value": total_cost,
        "previous_stock": cur_stock,
        "target_stock": target_stock,
        "updated_stock": new_stock,
        "guard_warning": guard_msg,
        "message": f"Successfully replenished {actual_qty} units of {name}. New stock: {new_stock} units."
    }
