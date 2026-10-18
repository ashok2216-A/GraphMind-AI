import os
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
raw_api = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").strip().rstrip("/")
if raw_api and not raw_api.startswith("http://") and not raw_api.startswith("https://"):
    API = f"https://{raw_api}"
else:
    API = raw_api

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
            response = requests.post(f"{API}/seed", timeout=15)
            response.raise_for_status()
            st.success(response.json().get("message", "Seeded"))
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
                r = requests.post(f"{API}/search", json={"keyword": question}, timeout=15)
                r.raise_for_status()
                st.json(r.json())
            except Exception as e:
                st.error(f"API error: {e}")
    with col2:
        service = st.text_input("Service to trace", value="Payment API")
        if st.button("Trace dependencies"):
            try:
                r = requests.post(f"{API}/dependencies", json={"service_name": service}, timeout=15)
                r.raise_for_status()
                st.json(r.json())
            except Exception as e:
                st.error(f"API error: {e}")
    incident_id = st.text_input("Incident ID", value="INC-101")
    if st.button("Get incident evidence"):
        try:
            r = requests.post(f"{API}/incident", json={"incident_id": incident_id}, timeout=15)
            r.raise_for_status()
            st.json(r.json())
        except Exception as e:
            st.error(f"API error: {e}")

with tab2:
    st.subheader("Company Brain")
    st.write("Search connected company facts: people, teams, services, projects, decisions, incidents, and runbooks.")
    term = st.text_input("Company knowledge query", value="checkout")
    if st.button("Search knowledge", key="company_search"):
        try:
            r = requests.post(f"{API}/search", json={"keyword": term}, timeout=15)
            r.raise_for_status()
            data = r.json()
            st.metric("Matching graph records", data.get("count", 0))
            st.json(data.get("results", []))
        except Exception as e:
            st.error(f"API error: {e}")

with tab3:
    st.subheader("Memory that survives sessions")
    st.write("Memories are stored as `AgentMemory` nodes and can link to company entities.")
    mem_keyword = st.text_input("Optional memory keyword", value="")
    if st.button("Recall memory"):
        try:
            r = requests.post(
                f"{API}/memory/recall",
                json={"session_key": session_key, "keyword": mem_keyword},
                timeout=15,
            )
            r.raise_for_status()
            st.json(r.json())
        except Exception as e:
            st.error(f"API error: {e}")
    st.caption("To save a finding through the AI agent, run `adk web` and ask GraphMind to remember it.")

with tab4:
    st.subheader("Knowledge graph snapshot")
    if st.button("Load graph"):
        try:
            r = requests.get(f"{API}/graph", timeout=15)
            r.raise_for_status()
            data = r.json()
            nodes, edges = data.get("nodes", []), data.get("edges", [])
            left, right = st.columns(2)
            with left:
                st.metric("Nodes", len(nodes))
                st.dataframe(nodes, use_container_width=True)
            with right:
                st.metric("Relationships", len(edges))
                st.dataframe(edges, use_container_width=True)
        except Exception as e:
            st.error(f"API error: {e}")

st.divider()
st.caption("GraphMind MVP • Google ADK + Gemini + FalkorDB • Synthetic demo dataset")
