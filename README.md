# VeganFlow — Autonomous Multi-Agent Supply Chain System

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Framework-LangGraph-orange.svg)](https://github.com/langchain-ai/langgraph)
[![Ollama](https://img.shields.io/badge/LLM-Ollama%20(qwen2.5:7b)-purple.svg)](https://ollama.ai/)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-red.svg)](https://streamlit.io/)
[![Database](https://img.shields.io/badge/Database-SQLite-lightgrey.svg)](https://www.sqlite.org/)

---

## 📌 Problem Statement

Retail inventory management frequently suffers from critical stockout risks and inefficient manual vendor procurement processes. Delays in identifying low-stock items cause lost revenue, while unmonitored reordering can lead to expensive overstocking and budget overruns. **VeganFlow** automates the entire retail supply chain lifecycle—from real-time POS shelf scanning to autonomous agent-to-agent (A2A) vendor price negotiations—ensuring optimal inventory levels while enforcing strict financial and operational safety guardrails.

---

## 🏗️ System Architecture

VeganFlow is built on a directed, stateful multi-agent state graph compiled with **LangGraph**. The workflow comprises 5 specialized functional nodes:

1. **`orchestrator_node`**: Ingests natural language user queries, extracts entities (product names, quantities), and classifies intent (`CHECK_STOCK`, `NEGOTIATE_RESTOCK`).
2. **`shelf_monitor_node`**: Queries SQLite POS database to analyze stock quantities, daily sales velocity, Days of Supply (DoS), and expiration risk windows.
3. **`negotiation_node`**: Conducts multi-turn Agent-to-Agent (A2A) Request for Quotation (RFQ) handshakes across competing wholesale vendors to negotiate volume discounts below list price.
4. **`execution_node`**: Evaluates financial guardrails and updates inventory stock levels in SQLite upon successful purchase order (PO) finalization.
5. **`output_formatter_node`**: Formats transparent natural language responses, cost savings summaries, and guardrail warnings.

---

## 🛡️ Multi-Layered Safety Guardrails

To prevent autonomous agent hallucination and financial exposure, VeganFlow implements a 3-tier defense matrix:

- **🔄 Loop Guard:** Enforces a hard limit of maximum 3 negotiation iterations across vendor candidate pools to prevent infinite looping and redundant API calls.
- **💰 Autonomous Budget Guard ($500 Threshold):** Orders exceeding **$500.00** total value trigger a mandatory **Human-in-the-Loop (HITL)** approval gate before PO execution.
- **📦 Overstocking Guardrail:** Restock orders are capped at `max_allowed = target_stock_level - current_stock`. If `current_stock >= target_stock`, reorders are automatically blocked. If an order exceeds capacity, it is automatically reduced to `max_allowed`.

---

## 👤 Human-in-the-Loop (HITL) Approval System

When an order exceeds the **$500.00** threshold, VeganFlow pauses execution and requests manager confirmation:

- **Interactive UI Approval:** Streamlit renders an interactive Action Card with **[✅ Authorize & Commit Purchase Order]** and **[❌ Reject / Cancel Order]** buttons.
- **Conversational Chat Intent:** Managers can authorize orders directly by typing `"approve"`, `"confirm"`, `"authorize"`, or `"yes"` in the chat terminal.
- **Audit Logging:** Every approval or rejection is logged to `approval_log.txt` with exact timestamp, product SKU, negotiated unit price, total cost, and manager action.

---

## 🧪 Benchmark Test Cases

The evaluation suite (`evals.py`) automatically executes 6 core benchmark test cases:

1. **Out of Stock & Empty List Guardrail:** Validates system behavior when all products are in stock vs. reporting critical low-stock items.
2. **Critical Stockout Detection:** Identifies items with `< 1.0 Day of Supply` (DoS) and triggers urgent reorder flags.
3. **Waste Risk & Expiring Soon Filter:** Scans batches expiring within 7 days to suggest promotional discounts or priority clearance.
4. **Autonomous A2A Restock Negotiation (< $500 Budget):** Evaluates end-to-end negotiation and PO execution for orders within autonomous budget limits.
5. **Budget & Overstocking Guardrails Protection (> $500 HITL):** Verifies that orders exceeding $500 trigger the `Human Approval Required` gate.
6. **Specific Product Entity Extraction & Scan:** Tests precise SKU entity resolution (e.g., `"Vegan Jumbo Shrimp"`) from unstructured user queries.
7. **Quantity Extraction & Overstock Reduction:** Validates regex parsing of custom target quantities (e.g., 500 units) and automatic order reduction by the Overstocking Guard.

---

## 🛠️ Tech Stack

- **Workflow Orchestration:** [LangGraph](https://github.com/langchain-ai/langgraph) (StateGraph, MemorySaver)
- **Language Model:** Ollama (`qwen2.5:7b`) via [LangChain Ollama](https://github.com/langchain-ai/langchain)
- **Database & Storage:** SQLite (`veganflow_store.db`) with custom health status triggers
- **User Interface:** Streamlit (Multi-Tab UI with Action Cards and Real-Time Agent Trace Streaming)
- **Environment Management:** `python-dotenv`, `pydantic`

---

## 🚀 How to Run

### 1. Initialize Virtual Environment & Install Dependencies
```bash
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Reset / Initialize SQLite Database
```bash
python database.py
```

### 3. Run Benchmark Evaluation Suite
```bash
python evals.py
```

### 4. Launch Multi-Agent Streamlit Web UI
```bash
streamlit run app.py
```
Open your browser at **`http://localhost:8501`**.
