import os
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import uvicorn
import threading
from veganflow_ai.external_vendor.vendor_agent import create_vendor_agent

VENDORS = [
    ("Earthly Gourmet", 8001, 0.98),
    ("Feesers Food Dst", 8002, 0.92),
    ("Clark Distributing", 8003, 0.88),
    ("LCG Foods", 8004, 0.95),
    ("Miyokos Creamery", 8005, 0.99),
    ("Rebel Cheese", 8006, 0.96),
    ("Treeline Cheese", 8007, 0.94),
    ("The Vreamery", 8008, 0.97),
    ("The BE Hive", 8009, 0.93),
    ("All Vegetarian Inc", 8010, 0.85),
    ("FakeMeats.com", 8011, 0.99)
]

def run_single_vendor(name, port, reliability):
    try:
        app = create_vendor_agent(name, reliability, port)
        config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)
        server.run()
    except Exception as e:
        print(f"Error starting vendor {name} on port {port}: {e}")

def start_ecosystem():
    print("🌱 Starting all 11 VeganFlow Vendor Microservices (Ports 8001-8011)...")
    threads = []
    for name, port, rel in VENDORS:
        t = threading.Thread(target=run_single_vendor, args=(name, port, rel), daemon=True)
        t.start()
        threads.append(t)
        print(f"   ✅ Active: {name} on http://localhost:{port}")
    
    print("🚀 All 11 Vendor Agents are listening live via A2A!")
    # Keep main thread alive
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n👋 Stopping vendor ecosystem.")

if __name__ == "__main__":
    start_ecosystem()
