import sqlite3
from typing import List, Dict, Any, Optional
import datetime
import uuid
from engine import (
    compute_health_status,
    score_vendor_candidate,
    get_product_policy,
    negotiate_a2a_multi_round
)

DB_PATH = "optivendor_store.db"

def query_inventory(filter_type: str = "OUT_OF_STOCK", product_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Queries the SQLite inventory database and computes Days of Supply.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    norm_filter = (filter_type or "OUT_OF_STOCK").upper().strip()
    results = []

    if norm_filter == "OUT_OF_STOCK":
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
        cursor.execute("""
            SELECT product_id, name, category, stock_quantity, sales_velocity_daily, target_stock_level, vendor_id
            FROM inventory
            WHERE sales_velocity_daily > 0 AND (stock_quantity * 1.0 / sales_velocity_daily) < 2.0
        """)
        rows = cursor.fetchall()
        for r in rows:
            d = dict(r)
            d["days_of_supply"] = round(d["stock_quantity"] / d["sales_velocity_daily"], 1)
            d["status"] = "CRITICAL_STOCKOUT"
            results.append(d)

    elif norm_filter == "EXPIRING_SOON":
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
    Fetches competing vendors from database, scored transparently by composite vendor score.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if product_id:
        policy = get_product_policy(product_id)
        max_p = policy.get("max_unit_price")
        cursor.execute("""
            SELECT v.vendor_id, v.name, v.category, v.reliability_score, v.endpoint_url,
                   vo.price_wholesale, vo.delivery_days, vo.product_id
            FROM vendors v
            JOIN vendor_offers vo ON v.vendor_id = vo.vendor_id
            WHERE vo.product_id = ?
        """, (product_id,))
        rows = cursor.fetchall()
        conn.close()
        
        scored = []
        for r in rows:
            d = dict(r)
            list_p = d["price_wholesale"]
            score, status, breakdown = score_vendor_candidate(
                price=list_p,
                list_price=list_p,
                reliability=d["reliability_score"],
                delivery_days=d["delivery_days"],
                max_unit_price=max_p
            )
            d["total_score"] = score
            d["selection_status"] = status
            d["score_breakdown"] = breakdown
            scored.append(d)
            
        scored.sort(key=lambda x: x["total_score"], reverse=True)
        return scored
    elif category:
        cursor.execute("SELECT * FROM vendors WHERE category LIKE ? ORDER BY reliability_score DESC", (f"%{category}%",))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    else:
        cursor.execute("SELECT * FROM vendors ORDER BY reliability_score DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

def send_a2a_rfq(vendor_endpoint: str, product_id: str, quantity: int, target_unit_price: float = 3.30) -> Dict[str, Any]:
    """
    Executes unified multi-round A2A RFQ negotiation handshake.
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
    policy = get_product_policy(product_id)

    # Invoke single unified multi-round negotiation engine
    neg = negotiate_a2a_multi_round(
        vendor_name=v_name,
        list_price=list_price,
        quantity=quantity,
        target_price=target_unit_price,
        max_unit_price=policy.get("max_unit_price")
    )

    return {
        "vendor_name": v_name,
        "vendor_endpoint": vendor_endpoint,
        "product_id": product_id,
        "quantity": quantity,
        "list_price": list_price,
        "negotiated_price": neg["negotiated_price"],
        "total_cost": neg["total_cost"],
        "list_total": neg["list_total"],
        "delivery_days": base_delivery,
        "cost_saved": neg["savings"],
        "status": neg["status"],
        "policy_compliant": neg["policy_compliant"],
        "rounds": neg["rounds"]
    }

def execute_order(vendor_id: str, product_id: str, quantity: int, price: float, actor: str = "SYSTEM") -> Dict[str, Any]:
    """
    Executes PO, creates IN_TRANSIT purchase order record, and logs audit trail.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ensure tables exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            po_id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            vendor_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            total_cost REAL NOT NULL,
            list_price REAL NOT NULL,
            savings REAL NOT NULL,
            status TEXT NOT NULL,
            approved_by TEXT,
            expected_delivery TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor TEXT NOT NULL,
            product_id TEXT,
            vendor_id TEXT,
            po_id TEXT,
            details TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_movements (
            movement_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            product_id TEXT NOT NULL,
            change_qty INTEGER NOT NULL,
            new_stock INTEGER NOT NULL,
            reason TEXT NOT NULL,
            po_id TEXT
        )
    """)
    
    cursor.execute("SELECT name, stock_quantity, target_stock_level FROM inventory WHERE product_id = ?", (product_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"success": False, "message": f"Product {product_id} not found."}

    name, cur_stock, target_stock = row
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

    # Fetch vendor offer list price
    cursor.execute("SELECT price_wholesale, delivery_days FROM vendor_offers WHERE vendor_id = ? AND product_id = ?", (vendor_id, product_id))
    v_offer = cursor.fetchone()
    list_p = v_offer[0] if v_offer else price
    del_days = v_offer[1] if v_offer else 2

    total_cost = round(actual_qty * price, 2)
    list_total = round(actual_qty * list_p, 2)
    savings = max(0.0, round(list_total - total_cost, 2))
    
    now_dt = datetime.datetime.now()
    now_str = now_dt.isoformat()
    exp_del_str = (now_dt + datetime.timedelta(days=del_days)).strftime("%Y-%m-%d")
    po_id = f"PO-{uuid.uuid4().hex[:8].upper()}"

    # Insert into purchase_orders with status IN_TRANSIT
    cursor.execute("""
        INSERT INTO purchase_orders (po_id, product_id, vendor_id, quantity, unit_price, total_cost, list_price, savings, status, approved_by, expected_delivery, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (po_id, product_id, vendor_id, actual_qty, price, total_cost, list_p, savings, "IN_TRANSIT", actor, exp_del_str, now_str, now_str))

    # Insert into audit_log
    audit_msg = f"Created PO {po_id} (IN_TRANSIT): {actual_qty} units of {name} from {vendor_id} @ ${price:.2f}/unit (Total: ${total_cost:.2f}, Saved: ${savings:.2f})."
    if guard_msg:
        audit_msg += f" [{guard_msg}]"
        
    cursor.execute("""
        INSERT INTO audit_log (timestamp, event_type, actor, product_id, vendor_id, po_id, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (now_str, "PO_CREATED", actor, product_id, vendor_id, po_id, audit_msg))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "po_id": po_id,
        "product_id": product_id,
        "product_name": name,
        "ordered_quantity": actual_qty,
        "unit_price": price,
        "total_value": total_cost,
        "savings": savings,
        "previous_stock": cur_stock,
        "target_stock": target_stock,
        "status": "IN_TRANSIT",
        "expected_delivery": exp_del_str,
        "guard_warning": guard_msg,
        "message": f"PO {po_id} dispatched to {vendor_id} for {actual_qty} units of {name} (Status: IN_TRANSIT, Expected Delivery: {exp_del_str})."
    }

def receive_purchase_order(po_id: str, actor: str = "STORE_MANAGER") -> Dict[str, Any]:
    """
    Receives an IN_TRANSIT purchase order, updates inventory, and logs stock movements.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT po_id, product_id, vendor_id, quantity, status
        FROM purchase_orders
        WHERE po_id = ?
    """, (po_id,))
    po = cursor.fetchone()
    
    if not po:
        conn.close()
        return {"success": False, "message": f"PO {po_id} not found."}
        
    p_id, v_id, qty, status = po[1], po[2], po[3], po[4]
    
    if status == "RECEIVED":
        conn.close()
        return {"success": False, "message": f"PO {po_id} has already been received."}
        
    now_str = datetime.datetime.now().isoformat()
    
    # 1. Update Inventory Stock
    cursor.execute("UPDATE inventory SET stock_quantity = stock_quantity + ? WHERE product_id = ?", (qty, p_id))
    
    # 2. Update PO Status
    cursor.execute("UPDATE purchase_orders SET status = 'RECEIVED', updated_at = ? WHERE po_id = ?", (now_str, po_id))
    
    # Fetch new stock
    cursor.execute("SELECT name, stock_quantity FROM inventory WHERE product_id = ?", (p_id,))
    name, new_stock = cursor.fetchone()
    
    # 3. Log Stock Movement
    cursor.execute("""
        INSERT INTO stock_movements (timestamp, product_id, change_qty, new_stock, reason, po_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (now_str, p_id, qty, new_stock, f"Received PO {po_id}", po_id))
    
    # 4. Log Audit Event
    audit_msg = f"Received PO {po_id}: +{qty} units of {name} added to inventory. Stock updated: {new_stock - qty} ➔ {new_stock} units."
    cursor.execute("""
        INSERT INTO audit_log (timestamp, event_type, actor, product_id, vendor_id, po_id, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (now_str, "PO_RECEIVED", actor, p_id, v_id, po_id, audit_msg))
    
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "po_id": po_id,
        "product_id": p_id,
        "product_name": name,
        "received_qty": qty,
        "new_stock": new_stock,
        "message": f"PO {po_id} received! Added {qty} units of {name}. New POS stock: {new_stock} units."
    }
