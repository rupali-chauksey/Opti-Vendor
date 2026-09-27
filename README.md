# OptiVendor
### Autonomous Multi-Agent Inventory Procurement & Negotiation System

OptiVendor is a multi-agent system that autonomously detects stockout risks, negotiates with vendors via Agent-to-Agent (A2A) protocol, and executes procurement decisions with deterministic guardrails and human-in-the-loop governance.

---

## 📋 Problem Statement

Retail supply chains face two critical operational failures:

**1. Reactive Stockouts**
High-velocity products run out unexpectedly. Traditional systems only send alerts — they don't act. Store managers manually check spreadsheets and call vendors.

**2. Over-Purchasing & Waste**
Manual procurement over-orders perishable goods, blocking capital and creating waste. No intelligent reorder optimization.

**Root Cause:** Procurement is fragmented, reactive, and manual. Decisions take hours when they should take minutes.

---

## Demo Linlk

https://opti-vendor-unkmmdjpp3udeqrsdpxqds.streamlit.app/


## ✨ Solution

OptiVendor closes the loop. It autonomously:

1. **🔍 Detects** — Monitors inventory, calculates Days of Supply, triggers reorder signals
2. **💬 Negotiates** — Runs multi-round A2A negotiations with vendors
3. **🛡️ Validates** — Applies deterministic guardrails (budget, overstocking, loop limit)
4. **✅ Executes** — Places orders automatically OR routes to human approval
5. **📋 Audits** — Logs every decision to `approval_log.txt` for compliance

**What takes a manager 30 minutes, OptiVendor does in 3 seconds.**

---

## 🏗️ Architecture — LangGraph 5-Node State Machine

```text
┌───────────────────────────────────────────────────────────────┐
│                       ORCHESTRATOR NODE                       │
│ • Intent Classification (CHECK_STOCK / NEGOTIATE_RESTOCK)     │
│ • Entity Extraction (product name from query)                 │
│ • Quantity Extraction (regex-based number parsing)            │
└─────────────────────────────┬─────────────────────────────────┘
                              │
             ┌────────────────┴─────────────────────┐
             ▼                                      ▼
┌──────────────────────┐              ┌──────────────────────────┐
│  SHELF MONITOR NODE  │              │     NEGOTIATION NODE     │
│ • Query inventory    │              │ • Fetch vendors          │
│ • Days of Supply     │              │ • A2A RFQ handshake      │
│ • Risk detection     │              │ • Multi-round loop      │
└──────────┬───────────┘              │ • Max 3 iterations       │
           │                          └────────────┬─────────────┘
           │                                       │
           │                                       ▼
           │                          ┌──────────────────────────┐
           │                          │      EXECUTION NODE      │
           │                          │ • Budget Guard           │
           │                          │ • Overstocking Guard     │
           │                          │ • Human Approval (HITL)  │
           │                          └────────────┬─────────────┘
           │                                       │
           └──────────────────┬────────────────────┘
                              ▼
               ┌──────────────────────────┐
               │  OUTPUT FORMATTER NODE   │
               │ • Natural language       │
               │ • Never raw JSON         │
               └──────────────────────────┘
```

---

## 🛡️ Three Guardrails — Deterministic Defense

All guardrails are enforced in **Python code**, not in LLM prompts. This guarantees 100% reliability regardless of model behavior.

### 1. Loop Guard
- **Rule:** Maximum 3 tool calls per query
- **Purpose:** Prevents infinite negotiation loops
- **Location:** `negotiation_node()` in `agents.py`

### 2. Budget Guard
- **Rule:** Orders exceeding **$500** require Human Approval
- **Purpose:** Prevents autonomous execution of large financial decisions
- **Location:** `execution_node()` in `agents.py`
- **Key Detail:** Checks the **ORIGINAL requested value**, not the post-reduction value

### 3. Overstocking Guard
- **Rule:** Order quantity capped at `Target Stock - Current Stock`
- **Purpose:** Prevents over-ordering and capital blockage
- **Location:** `execute_order()` in `tools.py`

### 🎯 Layered Defense in Action

When both guardrails fire together:
User Request: Order 500 units of Oat Barista Blend
(500 × $3.15 = $1,575)

```text
▼
┌──────────────────────────────────────┐
│        LAYER 1: Budget Guard         │
│       $1,575 > $500 threshold        │
│   → HUMAN APPROVAL REQUIRED          │
└────────────────┬─────────────────────┘
                 │
                 │ Manager clicks ✅ Approve
                 ▼
┌──────────────────────────────────────┐
│     LAYER 2: Overstocking Guard      │
│     Target (100) - Current (12) = 88 │
│   → Order reduced from 500 to 88     │
└────────────────┬─────────────────────┘
                 │
                 ▼
Final: 88 units @ $3.15 = $277.20
New Stock Level: 100 units (target hit)
```

Even after manager approval, the second layer still prevents overstocking.

---

## 👤 Human-in-the-Loop (HITL) Approval

When an order exceeds $500, the system pauses and shows an approval card in the Streamlit UI.

### Order Details Card

| Field | Example |
|-------|---------|
| Product | Oat Barista Blend |
| Vendor | Clark Distributing |
| Requested Quantity | 500 units |
| Unit Price | $3.15 |
| **Original Order Value** | **$1,575.00** *(highlighted)* |
| Delivery Window | 2 days |

### Decision Controls
- ✅ **Approve Order** — Executes (with Overstocking Guard applied)
- ❌ **Reject Order** — Cancels, no action taken

### Audit Trail
Every decision is logged to `approval_log.txt`:
```text
2026-09-26 20:45:12 | APPROVED | Oat Barista Blend | Requested: 500 | Executed: 88 | Total: $277.20
2026-09-26 20:50:30 | REJECTED | Oat Barista Blend | 500 units | Total: $1575.00
```

---

## 🚀 Tech Stack

| Component | Technology |
|-----------|-----------|
| **Agent Orchestration** | LangGraph StateGraph + MemorySaver |
| **Local LLM** | Ollama (qwen2.5:7b + llama3.2) |
| **Database** | SQLite (`veganflow_store.db`) |
| **UI Framework** | Streamlit |
| **Data Processing** | Pandas |
| **Language** | Python 3.10+ |

---

## 📦 Installation

### Prerequisites
- Python 3.10 or higher
- Ollama installed and running (`ollama serve`)
- Ollama models pulled: `qwen2.5:7b` and `llama3.2`

### Setup Instructions

```bash
# 1. Clone the repository
git clone https://github.com/rupali-chauksey/SupplyChain.git
cd SupplyChain

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate          # macOS/Linux
# venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Pull Ollama models
ollama pull qwen2.5:7b
ollama pull llama3.2

# 5. Initialize the database
python database.py

# 6. Launch the application
streamlit run app.py
```
App will be available at: **`http://localhost:8501`**

---

## 🎬 Demo Scenarios

The sidebar contains 7 pre-built demo buttons for live demonstration.

### 📊 Basic Queries — No Approval Required
| # | Demo | Query | Expected Result |
|---|---|---|---|
| 1 | Specific Product | `"Check stock for Vegan Jumbo Shrimp"` | 5 units, OPTIMAL |
| 2 | Out of Stock | `"Check my store inventory..."` | Oat Barista critical risk |
| 3 | Expiring Soon | `"Which items are expiring soon?"` | 3 items with dates |

### 🟢 Small Orders — Auto-Execute (Under $500)
| # | Demo | Query | Expected Result |
|---|---|---|---|
| 4 | Small Order | `"Order 50 units of Oat Barista Blend"` | $157.50 — auto-executed |
| 5 | Overstocking Reduce | `"Order 50 units of Almond Milk"` | Reduced to 15 units |

### 🟠 Large Orders — Human Approval Required (Over $500)
| # | Demo | Query | Expected Result |
|---|---|---|---|
| 6 | Budget Guard | `"Order 200 units of Cultured Truffle Brie"` | $1,656 approval card |
| 7 | Layered Defense | `"Order 500 units of Oat Barista Blend"` | $1,575 → 88 units |

---

## 📸 Test Evidence — Live Screenshots

### ✅ Test 1: Specific Product Query
![Test 1 — Specific Product](screenshots/test1_specific_product.png)

**Query:** `Check stock for Vegan Jumbo Shrimp`
**Result:** 5 units, 1 unit/day velocity, OPTIMAL health status
**Proves:** Entity extraction + specific product filter works correctly

---

### ✅ Test 2: Out of Stock Detection
![Test 2 — Out of Stock](screenshots/test2_out_of_stock.png)

**Query:** `Check my store inventory and find which items are out of stock`
**Result:** No items fully out of stock, but Oat Barista Blend identified as critical risk (0.8 days remaining)
**Proves:** Proactive reasoning — agent detects risks beyond the literal query

---

### ✅ Test 3: Expiring Soon Detection
![Test 3 — Expiring Soon](screenshots/test3_expiring_soon.png)

**Query:** `Which items are expiring soon?`
**Result:** 3 items identified with exact expiry dates (Vanilla Coconut Yogurt, Cultured Truffle Brie, Artisanal Organic Tempeh)
**Proves:** Waste prevention via expiry tracking

---

### ✅ Test 4: Small Order Auto-Execute
![Test 4 — Small Order](screenshots/test4_small_order.png)

**Query:** `Order 50 units of Oat Barista Blend`
**Result:**
- A2A Negotiation: $3.15/unit (savings $13.50)
- Total PO Cost: $157.50 (< $500, no approval needed)
- Executed automatically
- New stock: 62 units
**Proves:** Small orders execute autonomously without human intervention

---

### ✅ Test 5: Overstocking Guard
![Test 5 — Overstocking Reduce](screenshots/test5_overstocking.png)

**Query:** `Order 50 units of Almond Milk Unsweetened`
**Result:**
- Requested: 50 units
- Actual Ordered: 15 units (reduced by Overstocking Guard)
- Reason: Target (60) - Current (45) = 15 units max
- New stock: 60 units
**Proves:** System prevents over-ordering, protects capital

---

### ✅ Test 6: Budget Guard — Human Approval Required
![Test 6 — Budget Guard](screenshots/test6_budget_guard.png)

**Query:** `Order 200 units of Cultured Truffle Brie`
**Result:**
- Original order value: $1,656 (200 × $8.28)
- Exceeds $500 threshold
- Approval card displayed with Approve/Reject buttons
- Order paused pending manager decision
**Proves:** Large financial decisions require human approval

---

### ✅ Test 7: Approve Flow — Layered Defense
![Test 7 — Approve Flow](screenshots/test7_approve_flow.png)

**Action:** Manager clicks ✅ Approve on Test 6's pending order
**Result:**
- Requested Quantity: 200 units
- Actual Ordered Quantity: 22 units (reduced by Overstocking Guard)
- Reason: Target (30) - Previous (8) = 22 units max allowed
- Total PO Cost: $182.16 (vs $1,656 requested)
**Proves:** Even after approval, second layer prevents overstocking

---

### ✅ Test 8: Reject Flow
![Test 8 — Reject Flow](screenshots/test8_reject_flow.png)

**Action:** Manager clicks ❌ Reject on pending order
**Result:** Order cancelled, no action taken, audit log entry created
**Proves:** Manager can override agent decisions, full audit trail

---

### ✅ Test 9: Layered Defense — Budget + Overstocking
![Test 9 — Layered Defense](screenshots/test9_layered_defense.png)

**Query:** `Order 500 units of Oat Barista Blend` → Manager clicks ✅ Approve
**Result:**
- Requested: 500 units ($1,575)
- Actual Ordered: 88 units ($277.20)
- New Stock Level: 100 units (target hit)
**Proves:** Two guards fire in sequence — Budget then Overstocking

---

## 🖥️ Application Interface

### Tab 1: 🚀 Live Visual War Room
Real-time step-by-step visualization:
- Step 1: Shelf Monitor scans inventory
- Step 2: Strategic Memory loads budget rules
- Step 3: Vendor marketplace discovery
- Step 4: A2A Negotiation handshake (buyer ↔ vendor)
- Step 5: Atomic POS execution + database update

### Tab 2: 🤖 Multi-Agent Chat Terminal
Natural language interface:
- Live tool execution trace
- Human-in-the-Loop approval cards
- Persistent chat history
- Sidebar demo buttons for auto-run

### Tab 3: 📦 Live Store Inventory & POS
Real-time SQLite database view:
- Days of Supply computation
- Health Status (CRITICAL / LOW / OPTIMAL)
- Color-coded alerts
- Live updates after each order

---

## 📁 Project Structure

```text
optivendor/
├── app.py                    # Streamlit UI (3 tabs + sidebar demos)
├── agents.py                 # LangGraph 5-node state machine
├── tools.py                  # Database queries + A2A simulation
├── database.py               # SQLite schema + seed data
├── requirements.txt          # Python dependencies
├── README.md                 # Project documentation
├── agent_trace.log           # Runtime logs (auto-generated)
├── approval_log.txt          # HITL audit trail (auto-generated)
└── veganflow_store.db        # SQLite database (auto-generated)
```

---

## 🧪 Testing

### Manual Testing (7 Scenarios)
Use the sidebar demo buttons for live testing.

### Evaluation Suite
```bash
python evals.py
```
Runs 6 test cases:
1. Out of Stock & Empty List Guardrail
2. Critical Stockout Detection (< 1.0 day supply)
3. Waste Risk & Expiring Soon Filter
4. A2A Restock Negotiation (< $500 budget)
5. Budget & Overstocking Guardrails Protection
6. Specific Product Entity Extraction

### Guardrail Unit Tests
```bash
python test_inventory_guardrails.py
```

---

## 💡 Key Design Decisions

### 1. Deterministic Guardrails over LLM Reasoning
Guardrails are enforced in Python code, not in LLM prompts. If the LLM suggests an action that violates a guardrail, the code wins. This ensures 100% reliability.

### 2. Original Value Check for Budget Guard
The Budget Guard checks the original requested value, not the reduced value. A 200-unit order at $8.28/unit ($1,656) triggers approval even if the Overstocking Guard would later reduce it to 22 units. This ensures the human sees the true scope of the request.

### 3. Layered Defense Architecture
Multiple independent guardrails run in sequence. If one fails, another catches the issue:
- Budget Guard $\rightarrow$ Human Approval
- Overstocking Guard $\rightarrow$ Quantity Reduction
- Loop Guard $\rightarrow$ Iteration Cap

### 4. Audit-First Design
Every decision (approval, rejection, execution) is logged to `approval_log.txt` and `agent_trace.log` for full traceability.

-
## 📝 License
MIT License — see LICENSE file for details.

*Status: Multi-agent prototype with 7 passing test scenarios and complete Human-in-the-Loop approval workflow.*
