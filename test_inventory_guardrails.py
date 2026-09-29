import sys
import os
import sqlite3

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from database import init_database
from tools import query_inventory, execute_order, send_a2a_rfq, receive_purchase_order
from engine import plan_order, reject_plan, get_inventory_summary_groups
from agents import optivendor_pipeline

def test_inventory_query_guardrails():
    print("=" * 70)
    print("🧪 1. INVENTORY TOOL & DETERMINISTIC QUERY GUARDRAILS TEST")
    print("=" * 70)
    
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
    assert res_shrimp[0]["status"] in ["LOW_STOCK", "OPTIMAL"], "Status should be LOW_STOCK or OPTIMAL"
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
    
    init_database()

    # Oat Barista Blend: Target = 100, Current = 12. Headroom = 88 units.
    # Case A: Requesting 150 units (exceeds headroom of 88)
    order_a = execute_order(vendor_id="V-CLARK", product_id="P-OAT1", quantity=150, price=3.50)
    print(f"🔹 Overstock Attempt (Request 150 units when max allowed is 88):")
    print(f"   Output: {order_a}")
    assert order_a["success"] == True
    assert order_a["ordered_quantity"] == 88, f"Quantity should be capped at 88, got {order_a['ordered_quantity']}"
    assert "Overstocking blocked" in order_a["guard_warning"]
    assert order_a["status"] == "IN_TRANSIT"
    print("   ✅ PASS: Order clamped to target capacity (88 units) & status set to IN_TRANSIT.\n")

    # Receive PO to update stock
    receive_res = receive_purchase_order(order_a["po_id"])
    assert receive_res["success"] == True
    assert receive_res["new_stock"] == 100

    # Case B: Stock is now 100 (at capacity). Attempting another order.
    order_b = execute_order(vendor_id="V-CLARK", product_id="P-OAT1", quantity=20, price=3.50)
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
    res_budget = optivendor_pipeline.invoke(state_budget, config={"configurable": {"thread_id": "test_budget_guard"}})
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
    res_product = optivendor_pipeline.invoke(state_product, config={"configurable": {"thread_id": "test_product_guard"}})
    print("🔹 Test Specific Product Query:")
    print(f"   Response: {res_product.get('final_response')}")
    assert "Vegan Jumbo Shrimp" in res_product.get("final_response")
    assert "5 units" in res_product.get("final_response")
    assert "LOW_STOCK" in res_product.get("final_response") or "OPTIMAL" in res_product.get("final_response")
    print("   ✅ PASS: Specific product entity extracted and verified.\n")

def test_order_rejection_flow():
    print("=" * 70)
    print("🧪 4. ORDER REJECTION FLOW TEST (HITL CANCELLATION)")
    print("=" * 70)

    init_database()

    # 1. Formulate plan that requires approval (e.g. 1000 units of Brie)
    plan = plan_order("P-BRIE", requested_qty=1000)
    assert plan.needs_approval == True
    assert plan.qty == 22

    # Verify initial PO count before rejection
    conn = sqlite3.connect("optivendor_store.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM purchase_orders WHERE product_id = 'P-BRIE'")
    po_count_before = cur.fetchone()[0]
    assert po_count_before == 0

    # 2. Reject the proposed plan
    rej_res = reject_plan(plan.plan_id, actor="STORE_MANAGER", reason="Order rejected by store manager due to budget review.")
    assert rej_res["success"] == True
    assert rej_res["status"] == "REJECTED"

    # 3. Assert NO PO was created in purchase_orders table
    cur.execute("SELECT COUNT(*) FROM purchase_orders WHERE product_id = 'P-BRIE'")
    po_count_after = cur.fetchone()[0]
    assert po_count_after == 0, f"Expected 0 purchase orders after rejection, found {po_count_after}"

    # 4. Assert REJECTED event is recorded in audit_log with actor and reason
    cur.execute("SELECT event_type, actor, product_id, reason, details FROM audit_log ORDER BY log_id DESC LIMIT 1")
    last_audit = cur.fetchone()
    conn.close()

    assert last_audit is not None
    assert last_audit[0] == "REJECTED", f"Expected event_type 'REJECTED', got {last_audit[0]}"
    assert last_audit[1] == "STORE_MANAGER", f"Expected actor 'STORE_MANAGER', got {last_audit[1]}"
    assert last_audit[2] == "P-BRIE", f"Expected product_id 'P-BRIE', got {last_audit[2]}"
    assert "budget review" in last_audit[3].lower() or "rejected" in last_audit[3].lower()

    print("   ✅ PASS: Rejection successfully cancels order, prevents PO creation, and logs REJECTED in audit trail.\n")

def test_brie_shelf_life_capping_and_approval():
    print("=" * 70)
    print("🧪 5. BRIE SHELF LIFE CAPPING & APPROVAL REASON TEST")
    print("=" * 70)

    init_database()

    # Request 1000 units of Cultured Truffle Brie
    plan = plan_order("P-BRIE", requested_qty=1000)

    # 1. Assert quantity caps to shelf life / capacity (22 units)
    assert plan.qty == 22, f"Expected 22 units, got {plan.qty}"

    # 2. Assert total is ~$202.40 (22 * 9.20 = 202.40)
    assert abs(plan.total - 202.40) < 0.05, f"Expected total ~$202.40, got {plan.total}"

    # 3. Assert requires approval because requested > 5x recommended (not because total > 500)
    assert plan.needs_approval == True, "Plan should require approval"
    assert plan.total <= 500.0, f"Total (${plan.total}) is <= 500.0"
    assert any("5x recommended" in r.lower() for r in plan.approval_reasons), f"Expected 5x rule reason, got {plan.approval_reasons}"
    assert not any("500" in r for r in plan.approval_reasons), f"Did not expect $500 reason, got {plan.approval_reasons}"

    print(f"   Plan Qty: {plan.qty} units | Total: ${plan.total:.2f}")
    print(f"   Approval Reasons: {plan.approval_reasons}")
    print("   ✅ PASS: Brie 1000 units caps to shelf life, total is ~$202.40, requires approval because requested > 5x recommended (not total > 500).\n")

def test_inbound_reduces_recommended_qty():
    print("=" * 70)
    print("🧪 6. INBOUND ORDERS REDUCE RECOMMENDED QUANTITY TEST")
    print("=" * 70)

    init_database()

    # 1. Baseline Oat reorder quantity without inbound (should recommend 118 units)
    plan_clean = plan_order("P-OAT1")
    assert plan_clean.qty == 118, f"Expected 118 units baseline, got {plan_clean.qty}"

    # 2. Insert 138 inbound IN_TRANSIT units for Oat (e.g. earlier orders)
    conn = sqlite3.connect("optivendor_store.db")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO purchase_orders (po_id, product_id, vendor_id, quantity, unit_price, total_cost, list_price, savings, status, approved_by, expected_delivery, created_at, updated_at)
        VALUES ('PO-TEST-138', 'P-OAT1', 'V-CLARK', 138, 3.29, 454.02, 3.42, 17.94, 'IN_TRANSIT', 'TEST', '2026-10-02', datetime('now'), datetime('now'))
    """)
    conn.commit()
    conn.close()

    # 3. Assert that with 138 inbound units, recommended quantity drops to 0
    plan_with_inbound = plan_order("P-OAT1")
    assert plan_with_inbound.qty == 0, f"Expected 0 recommended units with 138 inbound, got {plan_with_inbound.qty}"

    print(f"   Baseline Recommended: {plan_clean.qty} units ➔ With 138 Inbound: {plan_with_inbound.qty} units")
    print("   ✅ PASS: Inbound orders reduce recommended quantity (Oat with 138 inbound recommends 0 units).\n")

def test_status_in_chat_summary_matches_inventory_table():
    print("=" * 70)
    print("🧪 7. CHAT SUMMARY TO INVENTORY TABLE 1:1 STATUS CONSISTENCY TEST")
    print("=" * 70)

    init_database()

    # 1. Fetch table statuses computed by inventory query tool
    all_table_items = query_inventory(filter_type="ALL")
    table_status_map = {item["name"]: item["status"] for item in all_table_items}

    # 2. Fetch summary groups computed by deterministic summary engine
    summary_groups = get_inventory_summary_groups()
    summary_status_map = {}
    for st_name, prod_list in summary_groups.items():
        for p in prod_list:
            summary_status_map[p["name"]] = st_name

    # 3. Assert 1:1 match for every single product
    for prod_name, tbl_st in table_status_map.items():
        sum_st = summary_status_map.get(prod_name)
        assert sum_st == tbl_st, f"Mismatch for '{prod_name}': Table has '{tbl_st}' while Summary has '{sum_st}'"

    print(f"   Verified {len(table_status_map)} products across all status categories.")
    print("   ✅ PASS: Status in chat summary matches status in inventory table for every product.\n")

def test_plan_order_and_approval_scenarios():
    print("=" * 70)
    print("🧪 8. PLAN_ORDER & COMPREHENSIVE APPROVAL LOGIC SCENARIOS")
    print("=" * 70)

    init_database()

    # Scenario 1: 1000 Brie -> qty 22, total $202.40, needs_approval only because requested > 5x recommended
    plan_brie = plan_order("P-BRIE", requested_qty=1000)
    assert plan_brie.qty == 22, f"Expected 22 units for Brie, got {plan_brie.qty}"
    assert abs(plan_brie.total - 202.40) < 0.05, f"Expected total $202.40, got {plan_brie.total}"
    assert plan_brie.needs_approval is True, "1000 Brie must require approval"
    assert plan_brie.total <= 500.0, "Total must not exceed $500"
    assert any("5x recommended" in r.lower() for r in plan_brie.approval_reasons), "Reason must be 5x rule"
    assert not any("500" in r for r in plan_brie.approval_reasons), "Reason must not be $500 threshold"

    # Scenario 2: 250 Oat with empty inbound -> needs_approval True (total over $500)
    plan_oat_250 = plan_order("P-OAT1", requested_qty=250)
    assert plan_oat_250.qty == 250, f"Expected 250 units, got {plan_oat_250.qty}"
    assert plan_oat_250.total > 500.0, f"Expected total > $500, got {plan_oat_250.total}"
    assert plan_oat_250.needs_approval is True, "250 Oat must require approval due to total > $500"
    assert any("500" in r for r in plan_oat_250.approval_reasons), "Reason must be over $500 threshold"

    # Scenario 3: 50 Oat -> auto-execute, price uses the 5% tier
    plan_oat_50 = plan_order("P-OAT1", requested_qty=50)
    assert plan_oat_50.qty == 50, f"Expected 50 units, got {plan_oat_50.qty}"
    assert plan_oat_50.needs_approval is False, "50 Oat (< $500) must auto-execute without approval"
    # 5% discount tier on vendor list price
    expected_5pct_price = round(plan_oat_50.list_price * 0.95, 2)
    assert plan_oat_50.unit_price == expected_5pct_price, f"Expected 5% tier price {expected_5pct_price}, got {plan_oat_50.unit_price}"
    assert abs(plan_oat_50.total - (50 * expected_5pct_price)) < 0.05

    # Scenario 4: Oat position already 100/100 -> qty 0, no PO created
    conn = sqlite3.connect("optivendor_store.db")
    cur = conn.cursor()
    cur.execute("UPDATE inventory SET stock_quantity = 100 WHERE product_id = 'P-OAT1'")
    conn.commit()
    conn.close()

    plan_oat_full = plan_order("P-OAT1")
    assert plan_oat_full.qty == 0, f"Expected 0 reorder units when position is 100/100, got {plan_oat_full.qty}"

    # Scenario 5: stock 0, velocity 0, total exactly $500, vendor quote above ceiling
    from engine import check_approval_required, score_vendor_candidate
    assert check_approval_required(500.0) is False, "Total exactly $500.00 must NOT require approval (> 500 threshold)"
    assert check_approval_required(500.01) is True, "Total $500.01 must require approval"

    # Test vendor quote above ceiling
    score, status, _ = score_vendor_candidate(
        price=4.20,
        list_price=4.20,
        reliability=0.95,
        delivery_days=2,
        max_unit_price=3.80 # Ceiling $3.80
    )
    assert score == 0.0, "Disqualified vendor must receive score 0.0"
    assert "DISQUALIFIED" in status and "Ceiling" in status, f"Expected ceiling disqualification, got {status}"

    # Scenario 6: Receiving a PO updates stock, writes a stock_movements row and an audit row
    init_database()
    order_res = execute_order(vendor_id="V-CLARK", product_id="P-OAT1", quantity=50, price=3.25, actor="TEST_AGENT")
    po_id = order_res["po_id"]
    
    rec_res = receive_purchase_order(po_id, actor="TEST_MANAGER")
    assert rec_res["success"] is True

    conn = sqlite3.connect("optivendor_store.db")
    cur = conn.cursor()
    # 6a. Check stock updated
    cur.execute("SELECT stock_quantity FROM inventory WHERE product_id = 'P-OAT1'")
    stock_val = cur.fetchone()[0]
    assert stock_val == 12 + 50, f"Expected stock 62, got {stock_val}"

    # 6b. Check stock_movements row
    cur.execute("SELECT change_qty, new_stock, po_id FROM stock_movements WHERE po_id = ?", (po_id,))
    mov_row = cur.fetchone()
    assert mov_row is not None, "Expected row in stock_movements for received PO"
    assert mov_row[0] == 50
    assert mov_row[1] == 62
    assert mov_row[2] == po_id

    # 6c. Check audit_log row
    cur.execute("SELECT event_type, actor, po_id FROM audit_log WHERE po_id = ? AND event_type = 'PO_RECEIVED'", (po_id,))
    audit_row = cur.fetchone()
    assert audit_row is not None, "Expected PO_RECEIVED row in audit_log"
    assert audit_row[0] == "PO_RECEIVED"
    assert audit_row[1] == "TEST_MANAGER"
    assert audit_row[2] == po_id

    # 6d. Check inventory_batches row created
    cur.execute("SELECT qty, product_id FROM inventory_batches WHERE batch_id LIKE ?", (f"%{po_id}%",))
    batch_row = cur.fetchone()
    assert batch_row is not None, "Expected new batch in inventory_batches for received PO"
    assert batch_row[0] == 50
    conn.close()

    print("   ✅ PASS: All 6 plan_order, approval, ceiling guard, and PO receipt scenarios passed.\n")

def test_stockout_before_arrival_detection():
    print("=" * 70)
    print("🧪 9. STOCKOUT_BEFORE_ARRIVAL STATUS DETECTION TEST")
    print("=" * 70)

    from engine import compute_health_status
    # Oat: on_hand=12, velocity=15 -> dos = 0.8 days.
    # Lead time = 2.0 days. With inbound orders (e.g. 50 units):
    st_with_inbound = compute_health_status(stock=12, target=100, velocity=15.0, lead_time=2.0, inbound_qty=50)
    assert st_with_inbound == "STOCKOUT_BEFORE_ARRIVAL", f"Expected STOCKOUT_BEFORE_ARRIVAL, got {st_with_inbound}"

    # Without inbound orders:
    st_no_inbound = compute_health_status(stock=12, target=100, velocity=15.0, lead_time=2.0, inbound_qty=0)
    assert st_no_inbound == "CRITICAL_STOCKOUT", f"Expected CRITICAL_STOCKOUT, got {st_no_inbound}"

    print(f"   With Inbound: {st_with_inbound} | Without Inbound: {st_no_inbound}")
    print("   ✅ PASS: Correctly flags STOCKOUT_BEFORE_ARRIVAL when stock runs out before shipment delivery.\n")

if __name__ == "__main__":
    test_inventory_query_guardrails()
    test_overstocking_and_execution_guardrails()
    test_langgraph_pipeline_guardrails()
    test_order_rejection_flow()
    test_brie_shelf_life_capping_and_approval()
    test_inbound_reduces_recommended_qty()
    test_status_in_chat_summary_matches_inventory_table()
    test_plan_order_and_approval_scenarios()
    test_stockout_before_arrival_detection()
    print("🎉 ALL INVENTORY, APPROVAL & GUARDRAIL TESTS PASSED SUCCESSFULLY!")
