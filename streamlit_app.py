import os
import json
import requests
import streamlit as st
from dotenv import load_dotenv

from graphmind.tools import (
    search_company_knowledge,
    trace_service_dependencies,
    get_incident_evidence,
    remember_finding,
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
    print(f"[Render Live Log] {method} {path} - data: {data}", flush=True)
    if API:
        try:
            if method.upper() == "POST":
                r = requests.post(f"{API}{path}", json=data or {}, timeout=4)
            else:
                r = requests.get(f"{API}{path}", timeout=4)
            if r.status_code == 200:
                print(f"[Render Live Log] HTTP {r.status_code} from backend API for {path}", flush=True)
                return r.json()
        except Exception as exc:
            print(f"[Render Live Log] HTTP API notice ({exc}). Running graph tool in-process.", flush=True)

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

def generate_gemini_response(prompt: str, context: str):
    """Call Google Gemini 2.5 Flash if API key is provided."""
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    model = os.getenv("GRAPHMIND_MODEL", "gemini-2.5-flash").strip()
    if not api_key or api_key == "replace_me":
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                "You are GraphMind, a company intelligence and incident investigation agent backed by FalkorDB.\n"
                                "Your goal is to answer questions accurately using the following verified graph facts. Provide concise, clear answers citing affected services, owners, and decisions where applicable. Keep recommendations advisory.\n\n"
                                f"Graph Evidence:\n{context}\n\n"
                                f"User Question:\n{prompt}"
                            )
                        }
                    ]
                }
            ]
        }
        r = requests.post(url, json=payload, timeout=8)
        if r.status_code == 200:
            res = r.json()
            return res["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"[GraphMind Chat] Gemini API notice: {e}", flush=True)
    return None

def process_agent_chat(user_msg: str, session_key: str = "demo-user") -> str:
    """Intelligently route chat prompt to graph tools and synthesize response."""
    msg = user_msg.strip().lower()
    context = ""
    direct_summary = ""

    # 1. Memory write
    if "remember" in msg or "save finding" in msg:
        finding_text = user_msg
        for prefix in ["remember that", "remember:", "remember", "save finding:", "save finding"]:
            if msg.startswith(prefix):
                finding_text = user_msg[len(prefix):].strip()
                break
        res = call_api("POST", "/memory/recall", {}) # ensure tools initialized
        res = remember_finding(session_key, finding_text, ["INC-101", "payment-api"])
        return f"🧠 **Graph Memory Saved:**\n\nI have saved your finding into persistent graph memory as `AgentMemory` node (`{res.get('memory_id')}`) linked to related entities in FalkorDB.\n\n> *\"{finding_text}\"*\n\nThis finding will now be recallable across future agent sessions!"

    # 2. Memory recall
    if "recall" in msg or "past finding" in msg or "prior finding" in msg:
        kw = ""
        for word in ["about", "for", "on"]:
            if f"recall {word} " in msg:
                kw = msg.split(f"recall {word} ", 1)[1].strip()
                break
        res = call_api("POST", "/memory/recall", {"session_key": session_key, "keyword": kw})
        memories = res.get("memories", [])
        if memories:
            out = f"🧠 **Recalled Graph Memories ({len(memories)} findings found):**\n\n"
            for m in memories[:4]:
                out += f"- **[{m.get('session_key')}]** {m.get('finding')} *(Entities: {', '.join(m.get('entity_ids', []))})*\n"
            return out
        return "🧠 No past findings found matching your query in the graph."

    # 3. Incident investigation
    if "inc-" in msg or "incident" in msg or "outage" in msg or "spike" in msg:
        inc_id = "INC-102" if "102" in msg else "INC-101"
        ev = call_api("POST", "/incident", {"incident_id": inc_id})
        context += f"\nIncident Evidence ({inc_id}): {json.dumps(ev)}"
        direct_summary = f"### 🚨 Incident Investigation: {inc_id}\n\n"
        if ev.get("found"):
            data = ev["evidence"][0]
            direct_summary += f"**Title:** {data.get('title')}\n\n"
            direct_summary += f"**Severity:** `{data.get('severity').upper()}` | **Status:** `{data.get('status')}`\n\n"
            direct_summary += f"**Root Cause:** {data.get('description')}\n\n"
            direct_summary += f"**Affected Service:** {', '.join(data.get('affected_services', []))}\n\n"
            direct_summary += f"**Downstream Impact:** {', '.join(data.get('downstream_services', [])) or 'None'}\n\n"
            direct_summary += f"**Service Owner:** {', '.join(data.get('owners', []))}\n\n"
            direct_summary += f"**Emergency Runbook:** *{', '.join(data.get('documents', []))}*\n\n"
            direct_summary += "📋 **Advisory Recommendation:** Escalate to Platform Lead (Maya Chen) and inspect database pool saturation metrics before restarting downstream services."

    # 4. Dependency trace
    elif "depend" in msg or "blast radius" in msg or "trace" in msg or "impact" in msg:
        svc = "Checkout Service" if "checkout" in msg else "Payment API"
        deps = call_api("POST", "/dependencies", {"service_name": svc})
        context += f"\nDependency Trace ({svc}): {json.dumps(deps)}"
        if deps.get("results"):
            d = deps["results"][0]
            direct_summary = f"### 🔍 Dependency & Blast Radius Analysis: {svc}\n\n"
            direct_summary += f"- **Service:** {d.get('service')}\n"
            direct_summary += f"- **Upstream Dependencies:** {', '.join(d.get('dependencies', [])) or 'None (Root Datastore)'}\n"
            direct_summary += f"- **Accountable Owner:** {', '.join(d.get('owners', []))}\n"
            direct_summary += f"- **Active Outages:** {', '.join(d.get('incidents', [])) or 'None'}\n\n"
            direct_summary += "💡 **Topological Insight:** Service is in the critical transaction path. Any latency spike cascades into checkout operations."

    # 5. General company knowledge / decision search
    else:
        kw = user_msg.replace("search", "").replace("who", "").replace("what", "").replace("is", "").replace("why", "").strip() or "checkout"
        kn = call_api("POST", "/search", {"keyword": kw})
        context += f"\nCompany Knowledge ({kw}): {json.dumps(kn)}"
        results = kn.get("results", [])
        if results:
            direct_summary = f"### 🏛️ Company Brain Graph Matches for *'{kw}'*:\n\n"
            for r in results[:5]:
                labels = ", ".join(r.get("labels", []))
                direct_summary += f"- **[{labels}] {r.get('name')}**: {r.get('detail')}\n"
        else:
            direct_summary = f"No matching entities found in the company knowledge graph for '{kw}'."

    # If Gemini is configured, use it to synthesize an executive AI answer
    gemini_reply = generate_gemini_response(user_msg, context)
    if gemini_reply:
        return gemini_reply

    return direct_summary

st.set_page_config(page_title="GraphMind AI", page_icon="🧠", layout="wide")
st.title("🧠 GraphMind AI")
st.caption("One graph. Connected decisions, persistent memory, and a company brain.")
st.info("Demo data is synthetic. Recommendations are advisory; no external actions are executed.")

with st.sidebar:
    st.header("Setup & Controls")
    st.write("1. FalkorDB Graph Engine")
    st.write("2. FastAPI Intelligence Backend")
    st.write("3. Synthetic Company Dataset")
    if st.button("Seed / reset demo graph", use_container_width=True):
        try:
            response = call_api("POST", "/seed")
            st.success(response.get("message", "Seeded"))
        except Exception as e:
            st.error(f"Could not seed graph: {e}")
    session_key = st.text_input("Memory session key", value="demo-user")
    st.caption("Use the same session key later to recall saved findings.")
    st.divider()
    st.markdown("💡 **Sample Chat Prompts:**")
    st.markdown("- *Investigate incident INC-101*")
    st.markdown("- *Trace dependencies of Payment API*")
    st.markdown("- *Why are payment writes synchronous?*")
    st.markdown("- *Remember: pool saturation caused outage*")
    st.markdown("- *Recall prior findings*")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "💬 AI Agent Chat", "Investigate", "Company Brain", "Persistent Memory", "Graph Explorer"
])

with tab1:
    st.subheader("💬 Chat with GraphMind AI Agent")
    st.caption("Autonomous reasoning powered by FalkorDB Knowledge Graph & Google Gemini 2.5 Flash.")

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "👋 Hi, I'm **GraphMind**, your autonomous company intelligence agent! Ask me to investigate an outage (e.g. `INC-101`), trace service blast radiuses, check architectural decisions, or remember findings across sessions."
            }
        ]

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🧠" if msg["role"] == "assistant" else "👤"):
            st.markdown(msg["content"])

    if user_prompt := st.chat_input("Ask GraphMind (e.g., 'Investigate INC-101', 'Trace Payment API', 'Why synchronous writes?')..."):
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_prompt)

        with st.chat_message("assistant", avatar="🧠"):
            with st.spinner("GraphMind reasoning over FalkorDB..."):
                reply = process_agent_chat(user_prompt, session_key=session_key)
                st.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})

with tab2:
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

with tab3:
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

with tab4:
    st.subheader("Memory that survives sessions")
    st.write("Memories are stored as `AgentMemory` nodes and can link to company entities.")
    mem_keyword = st.text_input("Optional memory keyword", value="")
    if st.button("Recall memory"):
        try:
            data = call_api("POST", "/memory/recall", {"session_key": session_key, "keyword": mem_keyword})
            st.json(data)
        except Exception as e:
            st.error(f"Error: {e}")
    st.caption("You can also save findings in the 💬 AI Agent Chat tab by saying 'Remember that pool saturation caused INC-101'.")

with tab5:
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
st.caption("GraphMind AI • Google ADK + Gemini 2.5 Flash + FalkorDB • Graph Hacks 2026")
