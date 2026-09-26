import sys
import os
import time

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from database import init_database
from agents import veganflow_pipeline

def run_sanity_check():
    print("=" * 75)
    print("🔍 VEGANFLOW MULTI-AGENT SYSTEM: SANITY CHECK SUITE")
    print("=" * 75)

    # Initialize / reset DB
    init_database()

    scenarios = [
        {
            "id": "SANITY-01",
            "name": "Inventory Out of Stock / Critical Stockout Risk Detection",
            "query": "Check my store inventory and find which items are out of stock",
            "check": lambda resp: (
                "oat barista blend" in resp.lower() and 
                "critical stockout" in resp.lower() and
                "product not found" not in resp.lower()
            ),
            "expected_desc": "Mentions Oat Barista Blend critical stockout risk without product not found error"
        },
        {
            "id": "SANITY-02",
            "name": "Specific Product Stock Query (Vegan Jumbo Shrimp)",
            "query": "Check stock for Vegan Jumbo Shrimp",
            "check": lambda resp: (
                "vegan jumbo shrimp" in resp.lower() and
                "5 units" in resp.lower() and
                "optimal" in resp.lower()
            ),
            "expected_desc": "Mentions Vegan Jumbo Shrimp, 5 units left, and OPTIMAL status"
        },
        {
            "id": "SANITY-03",
            "name": "Expiring Soon Query (Batch Waste Risk)",
            "query": "Which items are expiring soon?",
            "check": lambda resp: (
                "oat barista blend" not in resp.lower() and
                "expir" in resp.lower() and
                ("yogurt" in resp.lower() or "brie" in resp.lower() or "tempeh" in resp.lower())
            ),
            "expected_desc": "Lists expiring items (Yogurt, Brie, Tempeh) and does NOT return Oat Barista Blend message"
        }
    ]

    all_passed = True

    for sc in scenarios:
        print(f"\n▶ [{sc['id']}] {sc['name']}")
        print(f"  💬 Query   : \"{sc['query']}\"")
        
        state = {
            "user_query": sc["query"],
            "intent": "CHECK_STOCK",
            "filter_type": "OUT_OF_STOCK",
            "target_product": None,
            "target_quantity": 100,
            "inventory_results": [],
            "vendor_candidates": [],
            "current_vendor_index": 0,
            "iteration_count": 0,
            "max_iterations": 3,
            "negotiation_log": [],
            "agreed_deal": None,
            "execution_result": None,
            "human_approval_needed": False,
            "final_response": "",
            "trace_steps": []
        }
        
        config = {"configurable": {"thread_id": f"sanity_{sc['id']}_{int(time.time())}"}}
        res = veganflow_pipeline.invoke(state, config=config)
        resp_text = res.get("final_response", "")
        
        passed = sc["check"](resp_text)
        if passed:
            print(f"  ✅ STATUS  : PASS")
        else:
            print(f"  ❌ STATUS  : FAIL")
            all_passed = False
            
        print(f"  📋 Output  :\n{resp_text}\n")

    print("=" * 75)
    if all_passed:
        print("🎯 SANITY CHECK RESULT: ALL 3 SCENARIOS PASSED (100%)")
    else:
        print("⚠️ SANITY CHECK RESULT: SOME SCENARIOS FAILED")
    print("=" * 75)

if __name__ == "__main__":
    run_sanity_check()
