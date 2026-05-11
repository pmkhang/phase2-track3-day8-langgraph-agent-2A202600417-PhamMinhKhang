"""Streamlit UI for the LangGraph support-ticket agent lab."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.metrics import metric_from_state, summarize_metrics
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.scenarios import load_scenarios
from langgraph_agent_lab.state import Route, Scenario, initial_state

st.set_page_config(page_title="LangGraph Agent Lab", layout="wide")
st.title("🤖 LangGraph Support-Ticket Agent")

# Sidebar — input
st.sidebar.header("Run a scenario")
mode = st.sidebar.radio("Mode", ["Custom query", "Load from scenarios.jsonl"])

if mode == "Custom query":
    query = st.sidebar.text_area("Query", "How do I reset my password?")
    expected = st.sidebar.selectbox("Expected route", [r.value for r in Route if r not in (Route.DEAD_LETTER, Route.DONE)])
    scenario = Scenario(id="custom", query=query, expected_route=Route(expected))
    scenarios = [scenario]
    run_all = False
else:
    scenarios_path = st.sidebar.text_input("scenarios.jsonl path", "data/sample/scenarios.jsonl")
    try:
        scenarios = load_scenarios(scenarios_path)
        st.sidebar.success(f"Loaded {len(scenarios)} scenarios")
    except Exception as e:
        st.sidebar.error(str(e))
        scenarios = []
    run_all = st.sidebar.checkbox("Run all scenarios", value=True)
    if not run_all and scenarios:
        ids = [s.id for s in scenarios]
        chosen_id = st.sidebar.selectbox("Pick scenario", ids)
        scenarios = [s for s in scenarios if s.id == chosen_id]

checkpointer_kind = st.sidebar.selectbox("Checkpointer", ["memory", "sqlite"])
run_btn = st.sidebar.button("▶ Run", type="primary")

# Main area
if run_btn and scenarios:
    cp = build_checkpointer(checkpointer_kind, "outputs/checkpoints.db")
    graph = build_graph(checkpointer=cp)
    metrics_list = []

    for scenario in scenarios:
        state = initial_state(scenario)
        cfg = {"configurable": {"thread_id": state["thread_id"]}}
        with st.spinner(f"Running {scenario.id}…"):
            result = graph.invoke(state, config=cfg)

        metrics_list.append(metric_from_state(result, scenario.expected_route.value, scenario.requires_approval))

        with st.expander(f"{'✅' if result['route'] == scenario.expected_route.value else '❌'} {scenario.id} — route: `{result.get('route')}`", expanded=len(scenarios) == 1):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Query**: {scenario.query}")
                st.markdown(f"**Expected**: `{scenario.expected_route.value}` → **Actual**: `{result.get('route')}`")
                st.markdown(f"**Final answer**: {result.get('final_answer') or result.get('pending_question') or '—'}")
                if result.get("approval"):
                    st.markdown(f"**Approval**: {result['approval']}")
            with col2:
                st.markdown("**Event timeline**")
                for ev in result.get("events", []):
                    st.markdown(f"- `{ev['node']}` · {ev['event_type']} · {ev['message']}")

    # Summary metrics
    if len(metrics_list) > 1:
        report = summarize_metrics(metrics_list)
        st.divider()
        st.subheader("📊 Metrics summary")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", report.total_scenarios)
        c2.metric("Success rate", f"{report.success_rate:.0%}")
        c3.metric("Total retries", report.total_retries)
        c4.metric("Total interrupts", report.total_interrupts)

        rows = [m.model_dump() for m in report.scenario_metrics]
        st.dataframe(rows, use_container_width=True)

        if st.button("💾 Save metrics.json"):
            Path("outputs/metrics.json").write_text(json.dumps(report.model_dump(), indent=2))
            st.success("Saved to outputs/metrics.json")
