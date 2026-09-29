import sqlite3
import os
import sys
import datetime

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

DB_PATH = "optivendor_store.db"

def init_database(db_path: str = DB_PATH):
    """
    Initializes the SQLite database with schemas and dummy data
    for 10 Vegan grocery products, 11 competing vendor microservices,
    purchase orders lifecycle, system audit log, and stock movements ledger.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Drop existing tables if re-initializing
    cursor.execute("DROP TABLE IF EXISTS inventory")
    cursor.execute("DROP TABLE IF EXISTS vendors")
    cursor.execute("DROP TABLE IF EXISTS vendor_offers")
    cursor.execute("DROP TABLE IF EXISTS purchase_orders")
    cursor.execute("DROP TABLE IF EXISTS audit_log")
    cursor.execute("DROP TABLE IF EXISTS stock_movements")

    # 1. Create Table: inventory
    cursor.execute("""
    CREATE TABLE inventory (
        product_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        stock_quantity INTEGER NOT NULL,
        sales_velocity_daily REAL NOT NULL,
        target_stock_level INTEGER NOT NULL,
        vendor_id TEXT NOT NULL,
        expiration_date TEXT NOT NULL
    )
    """)

    # 2. Create Table: vendors
    cursor.execute("""
    CREATE TABLE vendors (
        vendor_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        reliability_score REAL NOT NULL,
        endpoint_url TEXT NOT NULL
    )
    """)

    # 3. Create Table: vendor_offers
    cursor.execute("""
    CREATE TABLE vendor_offers (
        offer_id INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_id TEXT NOT NULL,
        product_id TEXT NOT NULL,
        price_wholesale REAL NOT NULL,
        delivery_days INTEGER NOT NULL,
        batch_expiry_date TEXT NOT NULL,
        FOREIGN KEY (vendor_id) REFERENCES vendors (vendor_id),
        FOREIGN KEY (product_id) REFERENCES inventory (product_id)
    )
    """)

    # 4. Create Table: purchase_orders
    cursor.execute("""
    CREATE TABLE purchase_orders (
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
        updated_at TEXT NOT NULL,
        FOREIGN KEY (vendor_id) REFERENCES vendors (vendor_id),
        FOREIGN KEY (product_id) REFERENCES inventory (product_id)
    )
    """)

    # 5. Create Table: audit_log
    cursor.execute("""
    CREATE TABLE audit_log (
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

    # 6. Create Table: stock_movements
    cursor.execute("""
    CREATE TABLE stock_movements (
        movement_id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        product_id TEXT NOT NULL,
        change_qty INTEGER NOT NULL,
        new_stock INTEGER NOT NULL,
        reason TEXT NOT NULL,
        po_id TEXT
    )
    """)

    # 7. Insert 11 Vendor Records
    vendors_data = [
        ("V-EARTH", "Earthly Gourmet", "Dairy Alternative", 0.98, "http://localhost:8001/a2a"),
        ("V-CLARK", "Clark Distributing", "Dairy Alternative", 0.95, "http://localhost:8002/a2a"),
        ("V-OATLY", "Oatly Direct Supply", "Beverage", 0.99, "http://localhost:8003/a2a"),
        ("V-MIYOK", "Miyoko Artisan Creamery", "Cheese Alternative", 0.96, "http://localhost:8004/a2a"),
        ("V-TREEL", "Treeline Cheese Co.", "Cheese Alternative", 0.93, "http://localhost:8005/a2a"),
        ("V-FEESE", "Feesers Food Supply", "General Grocery", 0.91, "http://localhost:8006/a2a"),
        ("V-UNFI", "UNFI Green Logistics", "General Grocery", 0.97, "http://localhost:8007/a2a"),
        ("V-BEYND", "Beyond Meat Hub", "Meat Alternative", 0.94, "http://localhost:8008/a2a"),
        ("V-SEATN", "Seitanic Craft Meats", "Meat Alternative", 0.89, "http://localhost:8009/a2a"),
        ("V-OCEAN", "Ocean Hugger Seafood", "Seafood Alternative", 0.92, "http://localhost:8010/a2a"),
        ("V-LCG", "LCG Foods Wholesale", "Dry Goods", 0.90, "http://localhost:8011/a2a"),
    ]
    cursor.executemany("INSERT INTO vendors VALUES (?, ?, ?, ?, ?)", vendors_data)

    today = datetime.date.today()
    def get_date(days_offset):
        return (today + datetime.timedelta(days=days_offset)).isoformat()

    # 8. Insert 10 Vegan Grocery Products
    inventory_data = [
        ("P-OAT1", "Oat Barista Blend", "Beverage", 12, 15.0, 100, "V-CLARK", get_date(45)),
        ("P-ALMD", "Almond Milk Unsweetened", "Beverage", 45, 5.0, 60, "V-CLARK", get_date(30)),
        ("P-BRIE", "Cultured Truffle Brie", "Cheese Alternative", 8, 2.0, 30, "V-MIYOK", get_date(2)),
        ("P-CHED", "Aged Smoked Cheddar Block", "Cheese Alternative", 35, 4.0, 50, "V-TREEL", get_date(40)),
        ("P-SHMP", "Vegan Jumbo Shrimp", "Seafood Alternative", 5, 1.0, 25, "V-OCEAN", get_date(25)),
        ("P-PEPR", "Seitan Pepperoni (Bulk)", "Meat Alternative", 40, 8.0, 80, "V-SEATN", get_date(20)),
        ("P-SAUS", "Plant-Based Sausage Links", "Meat Alternative", 75, 10.0, 100, "V-BEYND", get_date(35)),
        ("P-YGRT", "Vanilla Coconut Yogurt", "Dairy Alternative", 30, 3.0, 40, "V-FEESE", get_date(1)),
        ("P-TEMH", "Artisanal Organic Tempeh", "Meat Alternative", 20, 2.0, 35, "V-UNFI", get_date(3)),
        ("P-MAYO", "Egg-Free Mayo Large Jar", "Dry Goods", 50, 4.0, 60, "V-LCG", get_date(90)),
    ]
    cursor.executemany("INSERT INTO inventory VALUES (?, ?, ?, ?, ?, ?, ?, ?)", inventory_data)

    # 9. Insert Competing Vendor Offers
    offers_data = [
        ("V-CLARK", "P-OAT1", 3.42, 2, get_date(65)),
        ("V-OATLY", "P-OAT1", 3.65, 1, get_date(70)),
        ("V-EARTH", "P-OAT1", 3.80, 2, get_date(60)),
        ("V-LCG", "P-OAT1", 3.90, 4, get_date(50)),
        ("V-MIYOK", "P-BRIE", 9.80, 3, get_date(30)),
        ("V-TREEL", "P-BRIE", 9.20, 2, get_date(35)),
        ("V-OCEAN", "P-SHMP", 13.50, 2, get_date(45)),
        ("V-UNFI", "P-SHMP", 14.20, 3, get_date(50)),
        ("V-SEATN", "P-PEPR", 11.50, 2, get_date(40)),
        ("V-BEYND", "P-PEPR", 12.00, 3, get_date(45)),
        ("V-CLARK", "P-ALMD", 2.80, 2, get_date(60)),
        ("V-TREEL", "P-CHED", 5.50, 3, get_date(60)),
        ("V-BEYND", "P-SAUS", 6.20, 2, get_date(50)),
        ("V-FEESE", "P-YGRT", 3.10, 2, get_date(25)),
        ("V-UNFI", "P-TEMH", 4.00, 3, get_date(30)),
        ("V-LCG", "P-MAYO", 4.50, 4, get_date(120)),
    ]
    cursor.executemany("INSERT INTO vendor_offers (vendor_id, product_id, price_wholesale, delivery_days, batch_expiry_date) VALUES (?, ?, ?, ?, ?)", offers_data)

    # 10. Initial Baseline Audit Entry
    now_str = datetime.datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO audit_log (timestamp, event_type, actor, product_id, vendor_id, po_id, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (now_str, "SYSTEM_INIT", "SYSTEM", None, None, None, "Database reset to baseline demo state (10 products, 11 vendors)."))

    conn.commit()
    conn.close()
    print(f"✅ SQLite Database '{db_path}' initialized with baseline schema & demo seed data.")

if __name__ == "__main__":
    init_database()
