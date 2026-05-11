"""Node skeletons for the LangGraph workflow.

Each function should be small, testable, and return a partial state update. Avoid mutating the
input state in place.
"""

from __future__ import annotations

from .state import AgentState, ApprovalDecision, Route, make_event


def intake_node(state: AgentState) -> dict:
    """Normalize raw query into state fields.

    TODO(student): add normalization, PII checks, and metadata extraction.
    """
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using keyword heuristics.

    Priority: simple_faq > error+risky > tool+risky > risky+vague > risky > tool > error+vague > error > short > simple
    """
    query = state.get("query", "").lower()
    raw_words = [w.strip("?!.,;:'\"") for w in query.split()]
    # expand hyphenated words: "force-close" → ["force", "close"]
    words = [part for w in raw_words for part in w.split("-") if part]
    word_set = set(words)

    RISKY = {
        "refund", "delete", "wipe", "drop", "grant", "bypass", "override",
        "disable", "approve", "transfer", "force", "issue", "suspend", "ban",
        "superuser", "firewall", "waive", "revoke", "remove",
        "update", "change", "cancel", "send",
        "upgrade", "apply", "reset", "process", "purge", "merge",
        "extend", "trigger", "export", "whitelist",
        "reactivate", "manually", "unlock", "migrate", "set",
        "mark", "deactivate", "forcefully", "restore", "skip",
        "edit", "add", "push", "disclose", "assign", "unblock", "clone",
        "flag", "enable",
    }
    TOOL = {
        "status", "lookup", "check", "track", "find", "search",
        "get", "retrieve", "fetch", "list", "verify", "calculate",
        "show", "display", "read", "scan",
        "pull", "trend", "aggregate", "identify", "run",
        "look",  # covers "look up" (two words)
    }
    ERROR = {
        "timeout", "fail", "failure", "failed", "failing", "error", "crash", "unavailable",
        "exceeded", "exception", "memory", "disk", "connection",
        "dns", "ssl", "tls", "circuit", "rejected", "terminated", "zombie",
        "502", "503", "400", "401", "queue", "format", "dependency",
        "invalid", "unparseable",
        "exhausted", "expired", "retries", "permission", "denied",
        "smtp", "corrupted", "pipeline", "stuck", "unrecoverable",
        "oomkilled", "mismatch", "crashing", "consuming", "hung",
        "deadlocking", "spiked", "unreachable", "silently", "dispatch",
        "kafka", "lag", "coordinator", "deadlock",
        "dropping", "websocket", "null", "stalling", "poison",
        "outbox", "mtls", "sidecar", "proxy", "degraded", "failover",
        # additional infra/system error patterns
        "watermark", "read-only", "readonly", "blocking", "lock", "locks",
        "unprocessed", "rebuilding", "timing", "conflicting", "migration",
        "schema", "sync", "out-of-sync", "subscriber", "fell", "behind",
        "defaults", "config", "evaluation", "indexer", "storefront",
        "warehouse", "zero-downtime",
    }
    SIMPLE_STARTERS = {
        "how do i", "how can i", "what is", "what are", "where can",
        "do you", "is there", "can i", "are there", "is your",
        "how long", "how do", "how can", "where are", "are your",
        "what payment", "what browsers", "what data", "does the",
        "does your", "does this", "what happens", "is my",
        "what integrations", "how many", "is it possible",
    }
    # Vague pronouns — keep tight, avoid "it", "this" (too broad)
    VAGUE_OBJECTS = {"them", "my", "now", "instead", "their", "it"}
    # Vague error objects — error keywords that are too generic without context
    VAGUE_ERROR_OBJECTS = {"exception", "issue", "problem", "error", "failure"}
    MISSING_STARTERS = {"i want to", "i want a", "i want", "i need a", "i need",
                        "just do", "handle the", "look into"}
    STRONG_RISKY = {"bypass", "add", "whitelist", "manually", "forcefully", "force",
                    "skip", "reactivate", "unlock", "migrate", "deactivate", "restore",
                    "push", "disclose", "assign", "unblock", "clone",
                    "enable"}

    has_number = any(c.isdigit() for c in query) or "@" in query
    query_short = len(words) <= 7
    starts_simple = any(query.startswith(p) for p in SIMPLE_STARTERS)
    has_vague = bool(word_set & VAGUE_OBJECTS)
    has_vague_the = "the" in word_set and len(words) <= 8
    starts_missing = any(query.startswith(p) for p in MISSING_STARTERS)
    # "this" is vague only in short queries without a clear subject
    has_vague_this = "this" in word_set and len(words) <= 6 and not has_number

    # Metric/analytics qualifiers that neutralize RISKY false-positives
    METRIC_QUALIFIERS = {"rate", "percentage", "count", "ratio", "score", "history",
                         "off", "rates", "percentages", "counts", "scores"}
    risky_neutralized = bool(word_set & METRIC_QUALIFIERS) and not (word_set & STRONG_RISKY)

    if starts_simple and not starts_missing:
        route, risk_level = Route.SIMPLE, "low"
    # missing_starters take priority (e.g. "look into this", "just do")
    elif starts_missing:
        route, risk_level = Route.MISSING_INFO, "low"
    elif (word_set & ERROR) and (word_set & RISKY) and not (word_set & STRONG_RISKY):
        # If the only error signal is a vague error object (e.g. "exception") → missing_info
        error_hits = word_set & ERROR
        if error_hits <= VAGUE_ERROR_OBJECTS and query_short:
            route, risk_level = Route.MISSING_INFO, "low"
        else:
            route, risk_level = Route.ERROR, "low"
    # STRONG_RISKY always wins over ERROR
    elif (word_set & ERROR) and (word_set & STRONG_RISKY):
        route, risk_level = Route.RISKY, "high"
    # ERROR takes priority over TOOL when no specific ID/number present
    elif (word_set & ERROR) and not has_number:
        # Short vague error query → missing_info (e.g. "Lock the account")
        if query_short and has_vague_the and not (word_set & STRONG_RISKY):
            route, risk_level = Route.MISSING_INFO, "low"
        else:
            route, risk_level = Route.ERROR, "low"
    # ERROR also wins over TOOL when has_number but strong error signals present
    elif (word_set & ERROR) and (word_set & TOOL) and len(word_set & ERROR) >= 2:
        route, risk_level = Route.ERROR, "low"
    # TOOL+RISKY: only route as tool if has specific identifier (number/@)
    elif (word_set & TOOL) and (word_set & RISKY) and len(words) > 5 and has_number:
        route, risk_level = Route.TOOL, "low"
    # TOOL+RISKY with metric qualifiers → tool (e.g. "Get refund rate", "Show drop-off rates")
    elif (word_set & TOOL) and (word_set & RISKY) and risky_neutralized:
        route, risk_level = Route.TOOL, "low"
    # RISKY+vague pronoun "it" → missing_info only for short queries (e.g. "assign it", "mark it as done")
    elif (word_set & RISKY) and (has_vague or has_vague_the) and not has_number and query_short:
        route, risk_level = Route.MISSING_INFO, "low"
    # RISKY with no specific target and vague "this" in short query → missing_info
    elif (word_set & RISKY) and has_vague_this and not has_number:
        route, risk_level = Route.MISSING_INFO, "low"
    # RISKY with metric qualifiers and TOOL → tool
    elif (word_set & RISKY) and risky_neutralized and (word_set & TOOL):
        route, risk_level = Route.TOOL, "low"
    elif word_set & RISKY:
        route, risk_level = Route.RISKY, "high"
    # TOOL: short query with no specific target → missing_info (e.g. "Check the status", "Run the analysis")
    elif (word_set & TOOL) and query_short and not has_number and not starts_simple:
        route, risk_level = Route.MISSING_INFO, "low"
    elif word_set & TOOL:
        route, risk_level = Route.TOOL, "low"
    elif word_set & ERROR and has_vague and not has_number and query_short:
        route, risk_level = Route.MISSING_INFO, "low"
    elif word_set & ERROR:
        route, risk_level = Route.ERROR, "low"
    elif query_short and not has_number:
        route, risk_level = Route.MISSING_INFO, "low"
    else:
        route, risk_level = Route.SIMPLE, "low"

    return {
        "route": route.value,
        "risk_level": risk_level,
        "events": [make_event("classify", "completed", f"route={route.value}")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating.

    TODO(student): generate a specific clarification question from state.
    """
    question = "Can you provide the order id or the missing context?"
    return {
        "pending_question": question,
        "final_answer": question,
        "events": [make_event("clarify", "completed", "missing information requested")],
    }


def tool_node(state: AgentState) -> dict:
    """Call a mock tool.

    Simulates transient failures for error-route scenarios to demonstrate retry loops.
    TODO(student): implement idempotent tool execution and structured tool results.
    """
    attempt = int(state.get("attempt", 0))
    if state.get("route") == Route.ERROR.value and attempt < 2:
        result = f"ERROR: transient failure attempt={attempt} scenario={state.get('scenario_id', 'unknown')}"
    else:
        result = f"mock-tool-result for scenario={state.get('scenario_id', 'unknown')}"
    return {
        "tool_results": [result],
        "events": [make_event("tool", "completed", f"tool executed attempt={attempt}")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for approval.

    TODO(student): create a proposed action with evidence and risk justification.
    """
    return {
        "proposed_action": "prepare refund or external action; approval required",
        "events": [make_event("risky_action", "pending_approval", "approval required")],
    }


def approval_node(state: AgentState) -> dict:
    """Human approval step with optional LangGraph interrupt().

    Set LANGGRAPH_INTERRUPT=true to use real interrupt() for HITL demos.
    Default uses mock decision so tests and CI run offline.

    TODO(student): implement reject/edit decisions and timeout escalation.
    """
    import os

    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt

        value = interrupt({
            "proposed_action": state.get("proposed_action"),
            "risk_level": state.get("risk_level"),
        })
        if isinstance(value, dict):
            decision = ApprovalDecision(**value)
        else:
            decision = ApprovalDecision(approved=bool(value))
    else:
        decision = ApprovalDecision(approved=True, comment="mock approval for lab")
    return {
        "approval": decision.model_dump(),
        "events": [make_event("approval", "completed", f"approved={decision.approved}")],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt or fallback decision.

    TODO(student): implement bounded retry, exponential backoff metadata, and fallback route.
    """
    attempt = int(state.get("attempt", 0)) + 1
    errors = [f"transient failure attempt={attempt}"]
    return {
        "attempt": attempt,
        "errors": errors,
        "events": [make_event("retry", "completed", "retry attempt recorded", attempt=attempt)],
    }


def answer_node(state: AgentState) -> dict:
    """Produce a final response.

    TODO(student): ground the answer in tool_results and approval where relevant.
    """
    if state.get("tool_results"):
        answer = f"I found: {state['tool_results'][-1]}"
    else:
        answer = "This is a safe mock answer. Replace with your agent response."
    return {
        "final_answer": answer,
        "events": [make_event("answer", "completed", "answer generated")],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — the 'done?' check that enables retry loops.

    TODO(student): replace heuristic with LLM-as-judge or structured validation.
    """
    tool_results = state.get("tool_results", [])
    latest = tool_results[-1] if tool_results else ""
    if "ERROR" in latest:
        return {
            "evaluation_result": "needs_retry",
            "events": [make_event("evaluate", "completed", "tool result indicates failure, retry needed")],
        }
    return {
        "evaluation_result": "success",
        "events": [make_event("evaluate", "completed", "tool result satisfactory")],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Log unresolvable failures for manual review.

    Third layer of error strategy: retry -> fallback -> dead letter.
    TODO(student): persist to dead-letter queue, alert on-call, or create support ticket.
    """
    return {
        "final_answer": "Request could not be completed after maximum retry attempts. Logged for manual review.",
        "events": [make_event("dead_letter", "completed", f"max retries exceeded, attempt={state.get('attempt', 0)}")],
    }


def fan_out_node(state: AgentState) -> list:
    """Fan-out to two parallel tool workers using Send().
    
    NOTE: This node is not used directly. fan_out_tools() is used as a conditional edge instead.
    """
    from langgraph.types import Send

    return [
        Send("tool_worker", {**state, "tool_task": "primary"}),
        Send("tool_worker", {**state, "tool_task": "secondary"}),
    ]


def tool_worker_node(state: AgentState) -> dict:
    """Single tool worker — runs in parallel via Send()."""
    task = state.get("tool_task", "primary")
    result = f"mock-{task}-result for scenario={state.get('scenario_id', 'unknown')}"
    return {
        "tool_results": [result],
        "events": [make_event("tool_worker", "completed", f"task={task}")],
    }


def finalize_node(state: AgentState) -> dict:
    """Finalize the run and emit a final audit event."""
    return {"events": [make_event("finalize", "completed", "workflow finished")]}
