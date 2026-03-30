"""
Customer Intent Router — agent.py
===================================
Intelligent triage microservice for customer support.

Pipeline (SequentialAgent):
  greeter → intent_extractor → db_lookup → intent_router

Run in Cloud Shell:
  adk web --port 8080 --allow_origins="*"
  Then: Web Preview → Preview on port 8080
"""

import json
import logging
import sqlite3
from enum import Enum

from pydantic import BaseModel, Field

# --- Correct ADK imports for Cloud Shell / google-adk ---
from google.adk.agents import Agent, SequentialAgent
from google.adk.tools.tool_context import ToolContext

# ---------------------------------------------------------------------------
# Pydantic schema — enforces the exact JSON shape the router must return
# ---------------------------------------------------------------------------

class RouteLabel(str, Enum):
    TECHNICAL_SUPPORT     = "Technical Support"
    OUT_OF_WARRANTY_SALES = "Out-of-Warranty Sales"
    BILLING_AND_REFUNDS   = "Billing & Refunds"
    ESCALATION            = "Escalation"
    GENERAL_ENQUIRY       = "General Enquiry"


class Priority(str, Enum):
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


class RoutingDecision(BaseModel):
    """The strict output contract for every routing decision."""
    route: RouteLabel = Field(
        ..., description="The support team this ticket should be sent to."
    )
    priority: Priority = Field(
        ..., description="Urgency level of the customer's issue."
    )
    reason: str = Field(
        ..., max_length=200,
        description="One-sentence explanation grounded in the DB result and customer query."
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Model confidence in the routing decision (0.0 – 1.0)."
    )


# ---------------------------------------------------------------------------
# Simulated SQL database (replaces a real CRM / order management backend)
# ---------------------------------------------------------------------------

def _build_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE orders (
            order_id        TEXT PRIMARY KEY,
            user_id         TEXT NOT NULL,
            product_name    TEXT NOT NULL,
            purchase_date   TEXT NOT NULL,
            warranty_months INTEGER NOT NULL,
            warranty_active INTEGER NOT NULL,
            order_status    TEXT NOT NULL
        )
    """)
    cur.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", [
        ("ORD-1001", "USR-001", "ProBook Laptop 15",   "2024-06-01", 24, 1, "delivered"),
        ("ORD-1002", "USR-002", "UltraTab X10",        "2022-01-15", 12, 0, "delivered"),
        ("ORD-1003", "USR-003", "ClearView Monitor",   "2023-11-20", 18, 1, "delivered"),
        ("ORD-1004", "USR-004", "MaxSound Headphones", "2021-03-10", 12, 0, "delivered"),
        ("ORD-1005", "USR-001", "MechKey Pro",         "2025-01-05", 24, 1, "in_transit"),
        ("ORD-1006", "USR-005", "SlimCharge Pad",      "2024-12-01", 12, 1, "delivered"),
    ])
    conn.commit()
    return conn


_DB = _build_db()


# ---------------------------------------------------------------------------
# Tool 1 — Save customer query to agent state
# (mirrors add_prompt_to_state from the original zoo-guide code)
# ---------------------------------------------------------------------------

def save_customer_query(tool_context: ToolContext, query: str) -> dict:
    """
    Saves the raw customer support query into agent state so every
    downstream agent in the pipeline can read it consistently.

    Args:
        tool_context: Injected automatically by ADK.
        query: The verbatim message the customer submitted.

    Returns:
        A success status dict.
    """
    tool_context.state["CUSTOMER_QUERY"] = query
    logging.info(f"[State] CUSTOMER_QUERY saved: {query}")
    return {"status": "success", "saved_query": query}


# ---------------------------------------------------------------------------
# Tool 2 — Simulate a SQL database lookup (the Function Tool)
# ---------------------------------------------------------------------------

def query_order_database(
    tool_context: ToolContext,
    order_id: str = "",
    user_id: str  = "",
) -> dict:
    """
    Queries the order/warranty database for a given order_id or user_id.
    Saves the result to state["DB_RESULT"] for the router agent to read.

    Args:
        tool_context: Injected automatically by ADK.
        order_id: Order reference number (e.g. 'ORD-1001'). Optional.
        user_id:  Customer user ID (e.g. 'USR-001'). Optional.

    Returns:
        A dict with the matching order record, or an error message.
    """
    cur = _DB.cursor()

    if order_id:
        cur.execute("SELECT * FROM orders WHERE order_id = ?", (order_id.upper(),))
    elif user_id:
        cur.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY purchase_date DESC LIMIT 1",
            (user_id.upper(),),
        )
    else:
        result = {"error": "No order_id or user_id provided — cannot look up order."}
        tool_context.state["DB_RESULT"] = json.dumps(result)
        return result

    row = cur.fetchone()
    if not row:
        result = {"error": f"No order found for order_id='{order_id}' user_id='{user_id}'"}
        tool_context.state["DB_RESULT"] = json.dumps(result)
        logging.warning(f"[DB] {result}")
        return result

    cols   = [d[0] for d in cur.description]
    record = dict(zip(cols, row))
    result = {
        "order_id":        record["order_id"],
        "user_id":         record["user_id"],
        "product_name":    record["product_name"],
        "purchase_date":   record["purchase_date"],
        "warranty_months": record["warranty_months"],
        "warranty_active": bool(record["warranty_active"]),
        "order_status":    record["order_status"],
    }

    tool_context.state["DB_RESULT"] = json.dumps(result)
    logging.info(f"[DB] Record found: {result}")
    return result


# ---------------------------------------------------------------------------
# Routing rules injected into the intent_router prompt
# ---------------------------------------------------------------------------

_ROUTE_VALUES    = [e.value for e in RouteLabel]
_PRIORITY_VALUES = [e.value for e in Priority]

_ROUTING_RULES = f"""
ROUTING LOGIC — apply in order:
1. warranty_active = true  AND issue is hardware / damage / replacement
   → route = "Technical Support",     priority = HIGH
2. warranty_active = false AND issue is hardware / damage / replacement
   → route = "Out-of-Warranty Sales", priority = MEDIUM
3. issue involves billing / payment / refund / invoice
   → route = "Billing & Refunds",     priority = HIGH
4. order_status = "in_transit" AND issue is about delivery / tracking
   → route = "General Enquiry",       priority = LOW
5. DB_RESULT contains an error OR model confidence < 0.6
   → route = "Escalation",            priority = CRITICAL
6. Anything else
   → route = "General Enquiry",       priority = LOW

OUTPUT FORMAT — return ONLY a JSON object, no markdown, no preamble:
{{
  "route":      <one of {_ROUTE_VALUES}>,
  "priority":   <one of {_PRIORITY_VALUES}>,
  "reason":     "<≤200 char explanation grounded in DB result + customer issue>",
  "confidence": <float 0.0–1.0>
}}
"""


# ---------------------------------------------------------------------------
# Agent 1 — Greeter / Query Intake
# ---------------------------------------------------------------------------

# Agent 2 — Intent Extractor
# Reads CUSTOMER_QUERY from state, outputs structured JSON via output_key
# ---------------------------------------------------------------------------

intent_extractor = Agent(
    name="intent_extractor",
    model="gemini-2.0-flash",
    description="Extracts structured intent fields from the raw customer query.",
    instruction="""
You are an information-extraction engine.

Read the customer's raw query and extract the following fields.
Output ONLY a valid JSON object — no commentary, no markdown fences.

Fields:
- "user_id"    : Customer user ID (format USR-XXXX) if mentioned, else null
- "order_id"   : Order reference (format ORD-XXXX) if mentioned, else null
- "product"    : Product name or model if mentioned, else null
- "issue_type" : Short label, e.g. "screen_damage", "billing_dispute",
                 "delivery_query", "refund_request", "general_enquiry"
- "summary"    : One neutral sentence restating what the customer wants

CUSTOMER_QUERY:
{ CUSTOMER_QUERY }
""",
    output_key="EXTRACTED_INTENT",
)


# ---------------------------------------------------------------------------
# Agent 3 — DB Lookup Agent
# Calls query_order_database using identifiers from EXTRACTED_INTENT
# ---------------------------------------------------------------------------

db_lookup = Agent(
    name="db_lookup",
    model="gemini-2.0-flash",
    description="Calls the SQL function tool to fetch warranty and order status.",
    instruction="""
You are a database retrieval agent.

1. Read EXTRACTED_INTENT below to find the best identifier.
2. Call 'query_order_database':
   - Use order_id if present.
   - Fall back to user_id if order_id is absent.
   - If neither is present, call with empty strings — an error will be
     returned and the router will handle it gracefully.
3. The tool saves its result to state automatically.
   Confirm the lookup is complete — no other output needed.

EXTRACTED_INTENT:
{ EXTRACTED_INTENT }
""",
    tools=[query_order_database],
    output_key="DB_LOOKUP_STATUS",
)


# ---------------------------------------------------------------------------
# Agent 4 — Intent Router
# Synthesises all state → emits Pydantic-validated JSON routing decision
# ---------------------------------------------------------------------------

intent_router = Agent(
    name="intent_router",
    model="gemini-2.0-flash",
    description="Produces a deterministic JSON routing decision from query + DB data.",
    instruction=f"""
You are the routing engine for a customer support microservice.
Your output is machine-consumed — return ONLY valid JSON, nothing else.

Available context:
  CUSTOMER_QUERY:   {{ CUSTOMER_QUERY }}
  EXTRACTED_INTENT: {{ EXTRACTED_INTENT }}
  DB_RESULT:        {{ DB_RESULT }}

{_ROUTING_RULES}

Think step by step (internally):
1. What did the customer ask? (CUSTOMER_QUERY)
2. What was extracted? (EXTRACTED_INTENT)
3. What does the DB say? (DB_RESULT)
4. Apply routing logic above.
5. Output the JSON object — and ONLY the JSON object.
""",
    output_key="ROUTING_DECISION",
)


# ---------------------------------------------------------------------------
# Sequential Pipeline
# ---------------------------------------------------------------------------

intent_router_workflow = SequentialAgent(
    name="intent_router_workflow",
    description="Full triage pipeline: extract intent → DB lookup → route.",
    sub_agents=[
        intent_extractor,  # Step 1: parse free-text query
        db_lookup,         # Step 2: hit the simulated SQL backend
        intent_router,     # Step 3: produce deterministic routing JSON
    ],
)


# ---------------------------------------------------------------------------
# Root Agent — ADK requires this exact name exported from the module
# ---------------------------------------------------------------------------

root_agent = Agent(
    name="greeter",
    model="gemini-2.0-flash",
    description="Main entry point for the Customer Intent Router.",
    instruction="""
You are a friendly customer support intake assistant.

1. Greet the customer warmly and ask them to describe their issue.
2. Once they reply, call the 'save_customer_query' tool with their exact message.
3. After the tool confirms success, transfer control to 'intent_router_workflow'.
   Do NOT respond further yourself after calling the tool.
""",
    tools=[save_customer_query],
    sub_agents=[intent_router_workflow],
)


# ---------------------------------------------------------------------------
# Pydantic validation helper — call this after the pipeline run to validate
# the ROUTING_DECISION state value before sending it to your CRM / ticketing
# ---------------------------------------------------------------------------

def validate_routing_decision(raw_json: str) -> RoutingDecision:
    """
    Parses and validates the router's raw JSON output.
    Raises pydantic.ValidationError if the schema is violated.

    Usage (in a custom runner or test):
        raw = session.state.get("ROUTING_DECISION", "{}")
        decision = validate_routing_decision(raw)
        print(decision.model_dump_json(indent=2))
    """
    data = json.loads(raw_json)
    return RoutingDecision(**data)