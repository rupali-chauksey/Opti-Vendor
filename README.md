# 🌿 VeganFlow: Autonomous Multi-Agent Supply Chain System

> Production-grade autonomous multi-agent intelligence system for dynamic grocery inventory monitoring, supplier negotiation, and purchase execution.

---

## 🎯 Problem Statement

Traditional retail grocery supply chains suffer from delayed replenishment, costly stockouts, and perishable goods waste due to slow manual procurement workflows. **VeganFlow** replaces rigid, error-prone manual spreadsheets with autonomous cooperating AI agents that monitor inventory health in real-time, anticipate stockouts, negotiate wholesale prices with competing vendors, and securely execute replenishment purchase orders under strict deterministic guardrails.

---

## 🏗️ Architecture & LangGraph State Machine

VeganFlow coordinates 5 modular LangGraph nodes operating over a unified state schema with checkpointing and glass-box execution tracing:

```
                      ┌──────────────────────┐
                      │  orchestrator_node   │
                      └──────────┬───────────┘
                                 │
                 ┌───────────────┴──────────────┐
                 ▼                              ▼
      [Stock / Expiry Query]         [Procurement / Restock]
      ┌──────────────────────┐       ┌──────────────────────┐
      │  shelf_monitor_node  │       │   negotiation_node   │◄───┐ (Max 3 rounds)
      └──────────┬───────────┘       └──────────┬───────────┘────┘
                 │                              │ (Deal Agreed)
                 │                   ┌──────────▼───────────┐
                 │                   │    execution_node    │
                 │                   └──────────┬───────────┘
                 │                              │
                 └───────────────┬──────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │  output_formatter_node  │
                    └────────────┬────────────┘
                                 ▼
                              [ END ]
```

### LangGraph Nodes
1. **`orchestrator_node`**: Ingests natural language queries, extracts entities (e.g. SKU names like *Vegan Jumbo Shrimp*), and classifies intent into `CHECK_STOCK` or `NEGOTIATE_RESTOCK`.
2. **`shelf_monitor_node`**: Queries SQLite inventory and calculates real-time **Days of Supply** ($\text{Stock} / \text{Daily Velocity}$), flagging stockouts, critical items ($<1.0\text{ day}$), and expiring batches ($\le 7\text{ days}$).
3. **`negotiation_node`**: Conducts multi-round Agent-to-Agent (A2A) negotiation handshakes across competing suppliers to secure wholesale discounts.
4. **`execution_node`**: Enforces strict financial and capacity guardrails before committing purchase orders and updating POS inventory.
5. **`output_formatter_node`**: Synthesizes structured data into clear, polite, and human-friendly operational summaries (never outputs raw JSON).

---

## 🛡️ Core Production Guardrails

| Guardrail | Purpose | Implementation |
| :--- | :--- | :--- |
| 🔁 **Loop Guard** | Prevents infinite agent loops in stalled supplier negotiations | Hard ceiling of `max_iterations = 3`. If no deal is accepted after 3 rounds, execution breaks to synthesis. |
| 💰 **Budget Guard** | Protects capital by routing high-value orders to Human-in-the-Loop (HITL) | If total purchase order value exceeds **$500.00**, autonomous execution halts and requires manager sign-off. |
| 📦 **Overstocking Guard** | Eliminates warehouse overflow and over-ordering | Orders are capped at $\text{Target Stock} - \text{Current Stock}$. If stock is already at or above target capacity, the order is rejected. |
| 🎯 **Anti-Hallucination Query Guard** | Prevents phantom product errors on empty query sets | Deterministic checks guarantee that empty out-of-stock query results return `"All items are in stock"` instead of `"Product not found"`. |

---

## 💻 Tech Stack

- **Agent Orchestration:** LangGraph (StateGraph, MemorySaver checkpointing)
- **Language Models:** Ollama (`qwen2.5:7b` / local models) & LangChain
- **Storage Layer:** SQLite (`veganflow_store.db`) with 10 products & 11 vendor catalogs
- **Web UI & Visual War Room:** Streamlit (clean enterprise dashboard with KPI scorecards, interactive negotiation visualizer, and manual POS controls)
- **Language & Runtime:** Python 3.10+

---

## 🚀 Getting Started (Run Locally)

### 1. Installation
Clone the repository and install dependencies:
```bash
pip install -r requirements.txt
```

### 2. Initialize Database
Initialize the SQLite database with 10 grocery items and 11 competing supplier catalogs:
```bash
python database.py
```
*Output: `✅ SQLite Database 'veganflow_store.db' initialized with 10 products and 11 vendors.`*

### 3. Run Guardrail & Sanity Tests
Execute the deterministic unit tests and sanity checks:
```bash
python test_inventory_guardrails.py
python sanity_check.py
```

### 4. Run Evaluation Benchmark Suite
Run the 6 automated end-to-end evaluation benchmarks:
```bash
python evals.py
```

### 5. Launch the Streamlit App
Start the interactive Streamlit dashboard:
```bash
streamlit run app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## 🧪 Evaluation Benchmark Suite (6 Test Cases)

The evaluation suite ([`evals.py`](file:///d:/AGENTIC%20AI%20PROJECT/Autonomous_Supply_Chain_Intelligence-main/evals.py)) validates end-to-end accuracy:

1. **EVAL-01: Out of Stock & Anti-Hallucination Guardrail**
   - *Query:* `"Check my store inventory and find which items are out of stock"`
   - *Verification:* Identifies full-stock items and critical Oat Barista Blend risk without emitting hallucinated "Product not found".
2. **EVAL-02: Critical Stockout Detection (< 1.0 Day of Supply)**
   - *Query:* `"Analyze critical stockout risks and urgent reorders"`
   - *Verification:* Detects Oat Barista Blend (12 units, 15/day velocity = 0.8 days supply).
3. **EVAL-03: Waste Risk & Expiring Soon Filter**
   - *Query:* `"Which items are expiring soon?"`
   - *Verification:* Lists perishable items expiring within 7 days (Yogurt, Brie, Tempeh).
4. **EVAL-04: Autonomous A2A Negotiation (< $500 Budget)**
   - *Query:* `"Negotiate and restock Oat Barista Blend for 100 units"`
   - *Verification:* Secures discount with Clark Distributing, clamps order to 88 units headroom, and executes PO under $500.
5. **EVAL-05: Budget & Overstocking Guardrails (> $500 HITL)**
   - *Query:* `"Buy and restock 1000 units of Cultured Truffle Brie"`
   - *Verification:* Flags $8,280 total value and requests Human Manager Approval.
6. **EVAL-06: Specific Product Entity Extraction**
   - *Query:* `"Check stock for Vegan Jumbo Shrimp"`
   - *Verification:* Extracts SKU accurately, returning 5 units left and OPTIMAL status.
