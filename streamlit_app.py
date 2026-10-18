import os
import requests
import streamlit as st
from dotenv import load_dotenv

from graphmind.tools import (
    search_company_knowledge,
    trace_service_dependencies,
    get_incident_evidence,
    recall_memory,
    get_graph_snapshot,
)
from graphmind.seed import seed

load_dotenv()
raw_api = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").strip().rstrip("/")
if raw_api and not raw_api.startswith("http://") and not raw_api.startswith("https://"):
    API = f"https://{raw_api}"
else:
    API = raw_api

def call_api(method: str, path: str, data: dict = None):
    """Query FastAPI endpoint if reachable; seamlessly fallback to direct tools."""
    if API:
        try:
            if method.upper() == "POST":
                r = requests.post(f"{API}{path}", json=data or {}, timeout=4)
            else:
                r = requests.get(f"{API}{path}", timeout=4)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass  # Fall back to in-process execution

    # In-process execution fallback
    if path == "/seed":
        return seed()
    elif path == "/search":
        return search_company_knowledge(data.get("keyword", "") if data else "")
    elif path == "/dependencies":
        return trace_service_dependencies(data.get("service_name", "") if data else "")
    elif path == "/incident":
        return get_incident_evidence(data.get("incident_id", "") if data else "")
    elif path == "/memory/recall":
        return recall_memory(data.get("session_key", ""), data.get("keyword", "") if data else "")
    elif path == "/graph":
        return get_graph_snapshot()
    raise RuntimeError(f"Unknown endpoint: {path}")

st.set_page_config(page_title="GraphMind AI", page_icon="🧠", layout="wide")
st.title("🧠 GraphMind AI")
st.caption("One graph. Connected decisions, persistent memory, and a company brain.")
st.info("Demo data is synthetic. Recommendations are advisory; no external actions are executed.")

with st.sidebar:
    st.header("Setup")
    st.write("1. Start FalkorDB")
    st.write("2. Start the API")
    st.write("3. Seed demo data")
    if st.button("Seed / reset demo graph", use_container_width=True):
        try:
            response = call_api("POST", "/seed")
            st.success(response.get("message", "Seeded"))
        except Exception as e:
            st.error(f"Could not seed graph: {e}")
    session_key = st.text_input("Memory session key", value="demo-user")
    st.caption("Use the same key later to recall saved findings.")

tab1, tab2, tab3, tab4 = st.tabs([
    "Investigate", "Company Brain", "Persistent Memory", "Graph Explorer"
])

with tab1:
    st.subheader("Investigate a service or incident")
    question = st.text_input("Search keyword", value="payment")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Search company graph", type="primary"):
            try:
                data = call_api("POST", "/search", {"keyword": question})
                st.json(data)
            except Exception as e:
                st.error(f"Error: {e}")
    with col2:
        service = st.text_input("Service to trace", value="Payment API")
        if st.button("Trace dependencies"):
            try:
                data = call_api("POST", "/dependencies", {"service_name": service})
                st.json(data)
            except Exception as e:
                st.error(f"Error: {e}")
    incident_id = st.text_input("Incident ID", value="INC-101")
    if st.button("Get incident evidence"):
        try:
            data = call_api("POST", "/incident", {"incident_id": incident_id})
            st.json(data)
        except Exception as e:
            st.error(f"Error: {e}")

with tab2:
    st.subheader("Company Brain")
    st.write("Search connected company facts: people, teams, services, projects, decisions, incidents, and runbooks.")
    term = st.text_input("Company knowledge query", value="checkout")
    if st.button("Search knowledge", key="company_search"):
        try:
            data = call_api("POST", "/search", {"keyword": term})
            st.metric("Matching graph records", data.get("count", 0))
            st.json(data.get("results", []))
        except Exception as e:
            st.error(f"Error: {e}")

with tab3:
    st.subheader("Memory that survives sessions")
    st.write("Memories are stored as `AgentMemory` nodes and can link to company entities.")
    mem_keyword = st.text_input("Optional memory keyword", value="")
    if st.button("Recall memory"):
        try:
            data = call_api("POST", "/memory/recall", {"session_key": session_key, "keyword": mem_keyword})
            st.json(data)
        except Exception as e:
            st.error(f"Error: {e}")
    st.caption("To save a finding through the AI agent, run `adk web` and ask GraphMind to remember it.")

with tab4:
    st.subheader("Knowledge graph snapshot")
    if st.button("Load graph"):
        try:
            data = call_api("GET", "/graph")
            nodes, edges = data.get("nodes", []), data.get("edges", [])
            left, right = st.columns(2)
            with left:
                st.metric("Nodes", len(nodes))
                st.dataframe(nodes, use_container_width=True)
            with right:
                st.metric("Relationships", len(edges))
                st.dataframe(edges, use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")

st.divider()
st.caption("GraphMind MVP • Google ADK + Gemini + FalkorDB • Synthetic demo dataset")
