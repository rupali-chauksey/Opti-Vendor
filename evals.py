import sys
import os
import sqlite3
import time

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from database import init_database
from tools import query_inventory, fetch_vendors, send_a2a_rfq, execute_order
from agents import veganflow_pipeline

def run_evals():
    print("=" * 75)
    print("🧪 VEGANFLOW MULTI-AGENT EVALUATION & BENCHMARK SUITE")
    print("=" * 75)
    
    # 1. Reset database to known baseline state
    init_database()
    
    test_cases = [
        {
            "id": "EVAL-01",
            "name": "Out of Stock & Empty List Guardrail",
            "query": "Check my store inventory and find which items are out of stock",
            "expected_intent": "CHECK_STOCK",
            "validate": lambda res: (
                "out of stock" in res["final_response"].lower() or 
                "all items are in stock" in res["final_response"].lower() or 
                "critical stockout risk" in res["final_response"].lower()
            ) and "product not found" not in res["final_response"].lower()
        },
        {
            "id": "EVAL-02",
            "name": "Critical Stockout Detection (< 1.0 Day of Supply)",
            "query": "Analyze critical stockout risks and urgent reorders",
            "expected_intent": "CHECK_STOCK",
            "validate": lambda res: "oat barista blend" in res["final_response"].lower() and "critical" in res["final_response"].lower()
        },
        {
            "id": "EVAL-03",
            "name": "Waste Risk & Expiring Soon Filter",
            "query": "Which items are expiring soon?",
            "expected_intent": "CHECK_STOCK",
            "validate": lambda res: (
                "expir" in res["final_response"].lower() and
                ("yogurt" in res["final_response"].lower() or "brie" in res["final_response"].lower() or "tempeh" in res["final_response"].lower())
            )
        },
        {
            "id": "EVAL-04",
            "name": "Autonomous A2A Restock Negotiation (< $500 Budget)",
            "query": "Negotiate and restock Oat Barista Blend for 100 units",
            "expected_intent": "NEGOTIATE_RESTOCK",
            "validate": lambda res: "replenished" in res["final_response"].lower() or "deal finalized" in res["final_response"].lower() or "po cost" in res["final_response"].lower()
        },
        {
            "id": "EVAL-05",
            "name": "Budget & Overstocking Guardrails Protection (> $500 HITL)",
            "query": "Buy and restock 1000 units of Cultured Truffle Brie",
            "expected_intent": "NEGOTIATE_RESTOCK",
            "validate": lambda res: (
                "human approval required" in res["final_response"].lower() or 
                "overstocking blocked" in res["final_response"].lower() or
                "exceeds" in res["final_response"].lower()
            )
        },
        {
            "id": "EVAL-06",
            "name": "Specific Product Entity Extraction & Scan",
            "query": "Check stock for Vegan Jumbo Shrimp",
            "expected_intent": "CHECK_STOCK",
            "validate": lambda res: (
                "vegan jumbo shrimp" in res["final_response"].lower() and 
                "5 units" in res["final_response"].lower() and
                "optimal" in res["final_response"].lower()
            )
        }
    ]

    passed_count = 0
    total_count = len(test_cases)

    for tc in test_cases:
        print(f"\n▶ Running [{tc['id']}] {tc['name']}...")
        print(f"  👤 User Query : '{tc['query']}'")
        
        init_state = {
            "user_query": tc["query"],
            "intent": "CHECK_STOCK",
            "filter_type": "OUT_OF_STOCK",
            "target_product": None,
            "target_quantity": 1000 if "1000" in tc["query"] else 100,
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
        
        config = {"configurable": {"thread_id": f"eval_{tc['id']}_{int(time.time())}"}}
        result = veganflow_pipeline.invoke(init_state, config=config)
        
        is_passed = tc["validate"](result)
        if is_passed:
            passed_count += 1
            print(f"  ✅ Status     : PASSED")
        else:
            print(f"  ❌ Status     : FAILED")
            
        print(f"  🤖 Response   :\n     {result['final_response'].replace(chr(10), chr(10) + '     ')}")

    success_rate = (passed_count / total_count) * 100
    print("\n" + "=" * 75)
    print(f"📊 EVALUATION SUMMARY: {passed_count}/{total_count} PASSED | SUCCESS RATE: {success_rate:.1f}%")
    print("=" * 75)
    
    # Check trace log existence
    if os.path.exists("agent_trace.log"):
        print("📁 Trace logging verified in 'agent_trace.log'.")

if __name__ == "__main__":
    run_evals()
