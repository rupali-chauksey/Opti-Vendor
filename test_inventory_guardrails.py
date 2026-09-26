import sys
import os
import sqlite3

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from database import init_database
from tools import query_inventory, execute_order, send_a2a_rfq
from agents import veganflow_pipeline

def test_inventory_query_guardrails():
    print("=" * 70)
    print("🧪 1. INVENTORY TOOL & DETERMINISTIC QUERY GUARDRAILS TEST")
    print("=" * 70)
    
    # Initialize baseline database
    init_database()

    # 1. Non-existent product query
    res_non_existent = query_inventory(filter_type="SPECIFIC_PRODUCT", product_name="NonExistentUnicornMilk")
    print(f"🔹 Query: Specific Product 'NonExistentUnicornMilk'")
    print(f"   Output: {res_non_existent}")
    assert res_non_existent == [], "Non-existent product should return empty list []"
    print("   ✅ PASS: Returns empty list [] without hallucination.\n")

    # 2. Specific existing product query
    res_shrimp = query_inventory(filter_type="SPECIFIC_PRODUCT", product_name="Vegan Jumbo Shrimp")
    print(f"🔹 Query: Specific Product 'Vegan Jumbo Shrimp'")
    print(f"   Output: {res_shrimp}")
    assert len(res_shrimp) == 1, "Should find exactly 1 record for Vegan Jumbo Shrimp"
    assert res_shrimp[0]["stock_quantity"] == 5, "Stock quantity should be 5"
    assert res_shrimp[0]["status"] == "OPTIMAL", "Status should be OPTIMAL"
    print("   ✅ PASS: Correctly extracted and fetched product details.\n")

    # 3. Critical stockout check
    res_crit = query_inventory(filter_type="CRITICAL_STOCKOUT")
    print(f"🔹 Query: 'CRITICAL_STOCKOUT'")
    print(f"   Output: {[r['name'] for r in res_crit]}")
    assert any(r["product_id"] == "P-OAT1" for r in res_crit), "Oat Barista Blend must be identified as critical stockout"
    print("   ✅ PASS: Oat Barista Blend correctly flagged as Critical Stockout (0.8 days supply).\n")

    # 4. Expiring soon check
    res_exp = query_inventory(filter_type="EXPIRING_SOON")
    print(f"🔹 Query: 'EXPIRING_SOON'")
    print(f"   Output: {[r['name'] for r in res_exp]}")
    assert len(res_exp) >= 3, "Should return at least 3 expiring items (Yogurt, Brie, Tempeh)"
    print("   ✅ PASS: Returns items expiring within 7 days.\n")

def test_overstocking_and_execution_guardrails():
    print("=" * 70)
    print("🧪 2. OVERSTOCKING & EXECUTION GUARDRAIL TEST")
    print("=" * 70)
    
    # Reset DB
    init_database()

    # Oat Barista Blend: Target = 100, Current = 12. Headroom = 88 units.
    # Case A: Requesting 150 units (exceeds headroom of 88)
    order_a = execute_order(vendor_id="V-EARTH", product_id="P-OAT1", quantity=150, price=3.50)
    print(f"🔹 Overstock Attempt (Request 150 units when max allowed is 88):")
    print(f"   Output: {order_a}")
    assert order_a["success"] == True
    assert order_a["ordered_quantity"] == 88, f"Quantity should be capped at 88, got {order_a['ordered_quantity']}"
    assert "Overstocking blocked" in order_a["guard_warning"]
    assert order_a["updated_stock"] == 100
    print("   ✅ PASS: Order clamped to target capacity (88 units).\n")

    # Case B: Stock is now 100 (at capacity). Attempting another order.
    order_b = execute_order(vendor_id="V-EARTH", product_id="P-OAT1", quantity=20, price=3.50)
    print(f"🔹 Overstock Attempt (When stock is already 100/100):")
    print(f"   Output: {order_b}")
    assert order_b["success"] == False
    assert "already at or above target capacity" in order_b["message"]
    print("   ✅ PASS: Order rejected because stock is already at full capacity.\n")

def test_langgraph_pipeline_guardrails():
    print("=" * 70)
    print("🧪 3. LANGGRAPH AGENT PIPELINE GUARDRAIL TEST")
    print("=" * 70)
    
    init_database()

    # 1. Budget Guard: > $500 order requires human approval
    state_budget = {
        "user_query": "Buy and restock 1000 units of Cultured Truffle Brie",
        "intent": "NEGOTIATE_RESTOCK",
        "filter_type": "SPECIFIC_PRODUCT",
        "target_product": "Cultured Truffle Brie",
        "target_quantity": 1000,
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
    res_budget = veganflow_pipeline.invoke(state_budget, config={"configurable": {"thread_id": "test_budget_guard"}})
    print("🔹 Test Budget Guard (> $500 PO):")
    print(f"   Human Approval Needed: {res_budget.get('human_approval_needed')}")
    print(f"   Response Preview: {res_budget.get('final_response')[:120]}...")
    assert res_budget.get("human_approval_needed") == True or "Human Approval Required" in res_budget.get("final_response")
    print("   ✅ PASS: Intercepted by Budget Guard (> $500 threshold).\n")

    # 2. Specific product stock query
    state_product = {
        "user_query": "Check stock for Vegan Jumbo Shrimp",
        "intent": "CHECK_STOCK",
        "filter_type": "SPECIFIC_PRODUCT",
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
    res_product = veganflow_pipeline.invoke(state_product, config={"configurable": {"thread_id": "test_product_guard"}})
    print("🔹 Test Specific Product Query:")
    print(f"   Response: {res_product.get('final_response')}")
    assert "Vegan Jumbo Shrimp" in res_product.get("final_response")
    assert "5 units" in res_product.get("final_response")
    assert "OPTIMAL" in res_product.get("final_response")
    print("   ✅ PASS: Specific product entity extracted and verified.\n")

if __name__ == "__main__":
    test_inventory_query_guardrails()
    test_overstocking_and_execution_guardrails()
    test_langgraph_pipeline_guardrails()
    print("🎉 ALL INVENTORY & AGENT GUARDRAIL TESTS PASSED SUCCESSFULLY!")
