import os
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

# Import our specialized sub-agents (use package-relative imports)
from .inventory import create_shelf_monitor
from .procurement import create_procurement_agent

# --- Automation: The Memory Hook ---
async def auto_save_memory(callback_context):
    """
    AUTOMATION HOOK: Runs automatically after every agent turn.
    It pushes the session history to the Memory Service for consolidation.
    """
    # Check if memory service is available in the runner context
    if not hasattr(callback_context._invocation_context, 'memory_service'):
        return

    memory_service = callback_context._invocation_context.memory_service
    session = callback_context._invocation_context.session
    
    if memory_service:
        print(f"   🧠 [Auto-Memory] Ingesting session insights...")
        await memory_service.add_session_to_memory(session)

def create_store_manager():
    """
    Creates the 'VeganFlow' Store Manager (Root Agent).
    """
    # Use Ollama Qwen 2.5 7B for reasoning and delegation
    model_config = LiteLlm(
        model="ollama_chat/qwen2.5:7b"
    )

    # Initialize the Workers
    inventory_agent = create_shelf_monitor()
    procurement_agent = create_procurement_agent()

    system_instruction = """
    You are the Store Manager for 'VeganFlow', a high-tech sustainable retail store.
    Your goal is to optimize inventory costs, prevent waste, and ensure affordability.
    
    You manage a team of specialized agents. DO NOT attempt to solve tasks yourself.
    DELEGATE immediately based on the user's request:
    
    --- YOUR TEAM ---
    1. shelf_monitor (Inventory Agent):
       - The "Eyes" of the store.
       - Use this for ANY questions about stock levels, sales velocity, out-of-stock items, or expiry dates.
       - Example: "Do we have enough Oat Milk?" or "What is out of stock?"
       
    2. procurement_negotiator (Procurement Agent):
       - The "Hands" of the store.
       - Use this ONLY when you need to buy stock, contact vendors, or check market prices.
       - Example: "Restock the Oat Milk" or "Negotiate a better price with Earthly Gourmet."
    
    --- YOUR PROCESS ---
    1. Analyze the user's request.
    2. If the user asks about inventory, out of stock, or low stock, delegate to 'shelf_monitor'.
    3. If the 'shelf_monitor' finds low stock / out of stock items, AUTOMATICALLY delegate 
       to 'procurement_negotiator' to reorder.
    4. Summarize the final result for the store owner in polite, clean natural language.
    
    --- STRICT GUARDRAIL RULES ---
    - If the user asks for 'out of stock' items, use the OUT_OF_STOCK filter. NEVER use EXPIRING_SOON for this query.
    - If the tool returns an empty list, respond with 'All items are in stock.' Do not hallucinate.
    - Do NOT output raw JSON format (e.g. {"result": ...}). Always respond in human-readable natural language.
    """

    store_manager = LlmAgent(
        name="store_manager",
        model=model_config,
        instruction=system_instruction,
        # This creates the hierarchy: Manager -> [Monitor, Negotiator]
        sub_agents=[inventory_agent, procurement_agent],
        # This enables the "Learning" capability
        after_agent_callback=auto_save_memory
    )

    return store_manager

if __name__ == "__main__":
    # Smoke test
    agent = create_store_manager()
    print(f"✅ Root Agent '{agent.name}' initialized.")
    # FIX: Use public 'sub_agents' attribute. 
    # Note: ADK wraps sub-agents in tools, so we iterate carefully.
    if agent.sub_agents:
        print(f"   Sub-agents linked: {len(agent.sub_agents)}")
    else:
        print("   No sub-agents found.")
