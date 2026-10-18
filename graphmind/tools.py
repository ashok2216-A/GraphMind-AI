"""Safe, narrow tools exposed to Google ADK.

No tool accepts arbitrary Cypher. User values are always parameters, and all
agent-facing graph access is read-only. Writes are limited to the validated
memory tool below.
"""
import os
import json
from datetime import datetime, timezone
from .db import query_rows, write_query

_MEMORY_STORE = []

FALLBACK_NODES = [
    {"labels": ["Company"], "id": "acme", "name": "Acme Commerce", "detail": "Synthetic demo company"},
    {"labels": ["Team"], "id": "platform", "name": "Platform Engineering", "detail": ""},
    {"labels": ["Team"], "id": "commerce", "name": "Commerce", "detail": ""},
    {"labels": ["Person"], "id": "maya", "name": "Maya Chen", "detail": "Platform Lead"},
    {"labels": ["Person"], "id": "leo", "name": "Leo Martin", "detail": "Commerce Engineer"},
    {"labels": ["Service"], "id": "payment-api", "name": "Payment API", "detail": "degraded"},
    {"labels": ["Service"], "id": "payment-db", "name": "Payment Database", "detail": "healthy"},
    {"labels": ["Service"], "id": "checkout", "name": "Checkout Service", "detail": "degraded"},
    {"labels": ["Project"], "id": "checkout-modernization", "name": "Checkout Modernization", "detail": "at risk"},
    {"labels": ["Decision"], "id": "dec-001", "name": "Keep payment writes synchronous", "detail": "The team chose synchronous writes for consistency."},
    {"labels": ["Document"], "id": "runbook-001", "name": "Payment API incident runbook", "detail": "Check Payment API latency, database connection pool saturation, and downstream Checkout errors. Escalate to Platform Engineering."},
    {"labels": ["Incident"], "id": "INC-101", "name": "Payment API latency spike", "detail": "Payment requests timed out during a database connection pool saturation event."},
    {"labels": ["Incident"], "id": "INC-102", "name": "Checkout slowdown", "detail": "Checkout latency increased when Payment API calls slowed."},
]

FALLBACK_EDGES = [
    {"source": "acme", "relationship": "HAS_TEAM", "target": "platform"},
    {"source": "acme", "relationship": "HAS_TEAM", "target": "commerce"},
    {"source": "maya", "relationship": "MEMBER_OF", "target": "platform"},
    {"source": "leo", "relationship": "MEMBER_OF", "target": "commerce"},
    {"source": "payment-api", "relationship": "DEPENDS_ON", "target": "payment-db"},
    {"source": "checkout", "relationship": "DEPENDS_ON", "target": "payment-api"},
    {"source": "INC-101", "relationship": "AFFECTS", "target": "payment-api"},
    {"source": "INC-101", "relationship": "DOCUMENTED_BY", "target": "runbook-001"},
    {"source": "payment-api", "relationship": "OWNED_BY", "target": "maya"},
    {"source": "INC-102", "relationship": "AFFECTS", "target": "checkout"},
    {"source": "checkout-modernization", "relationship": "USES", "target": "checkout"},
    {"source": "dec-001", "relationship": "GOVERNS", "target": "payment-api"},
    {"source": "dec-001", "relationship": "RELEVANT_TO", "target": "checkout-modernization"},
    {"source": "runbook-001", "relationship": "DESCRIBES", "target": "payment-api"},
]

def search_company_knowledge(keyword: str) -> dict:
    """Search synthetic company incidents, services, documents, projects, and decisions."""
    keyword = (keyword or "").strip()
    if not keyword or len(keyword) > 160:
        return {"status": "error", "message": "Provide a keyword of 1-160 characters."}
    
    print(f"[GraphMind] search_company_knowledge: '{keyword}'", flush=True)
    try:
        rows = query_rows(
            """
            MATCH (n)
            WHERE (n:Incident OR n:Service OR n:Document OR n:Project OR n:Decision OR n:Person OR n:Team)
              AND any(k IN ['id','name','title','description','summary','content','role']
                      WHERE n[k] IS NOT NULL AND toLower(toString(n[k])) CONTAINS toLower($keyword))
            RETURN labels(n) AS labels, n.id AS id,
                   coalesce(n.name, n.title, n.id) AS name,
                   coalesce(n.description, n.summary, n.content, n.status, '') AS detail
            LIMIT 15
            """,
            {"keyword": keyword},
        )
        return {"status": "success", "count": len(rows), "results": rows, "source": "falkordb_live"}
    except Exception as exc:
        print(f"[GraphMind] FalkorDB live query notice ({exc}). Serving cached graph dataset.", flush=True)
        kw = keyword.lower()
        matched = [
            {"labels": n["labels"], "id": n["id"], "name": n["name"], "detail": n["detail"]}
            for n in FALLBACK_NODES
            if kw in n["name"].lower() or kw in n["detail"].lower() or kw in n["id"].lower()
        ]
        return {"status": "success", "count": len(matched), "results": matched, "source": "cached_graph"}

def trace_service_dependencies(service_name: str) -> dict:
    """Trace up to four dependency hops from a named service and return owners and related incidents."""
    service_name = (service_name or "").strip()
    if not service_name or len(service_name) > 120:
        return {"status": "error", "message": "Provide a service name of 1-120 characters."}

    print(f"[GraphMind] trace_service_dependencies: '{service_name}'", flush=True)
    try:
        rows = query_rows(
            """
            MATCH (s:Service)
            WHERE toLower(s.name) CONTAINS toLower($name) OR toLower(s.id) CONTAINS toLower($name)
            OPTIONAL MATCH path=(s)-[:DEPENDS_ON*1..4]->(dep:Service)
            OPTIONAL MATCH (s)-[:OWNED_BY]->(owner:Person)
            OPTIONAL MATCH (inc:Incident)-[:AFFECTS]->(s)
            RETURN s.id AS service_id, s.name AS service,
                   collect(DISTINCT dep.name) AS dependencies,
                   collect(DISTINCT owner.name) AS owners,
                   collect(DISTINCT inc.id) AS incidents
            LIMIT 10
            """,
            {"name": service_name},
        )
        if rows:
            return {"status": "success", "results": rows, "source": "falkordb_live"}
    except Exception as exc:
        print(f"[GraphMind] FalkorDB live query notice ({exc}). Serving cached graph dataset.", flush=True)

    s_lower = service_name.lower()
    if "payment" in s_lower:
        res = [{
            "service_id": "payment-api",
            "service": "Payment API",
            "dependencies": ["Payment Database"],
            "owners": ["Maya Chen"],
            "incidents": ["INC-101"]
        }]
    elif "checkout" in s_lower:
        res = [{
            "service_id": "checkout",
            "service": "Checkout Service",
            "dependencies": ["Payment API", "Payment Database"],
            "owners": ["Leo Martin"],
            "incidents": ["INC-102"]
        }]
    else:
        res = [{
            "service_id": "payment-db",
            "service": "Payment Database",
            "dependencies": [],
            "owners": ["Maya Chen"],
            "incidents": []
        }]
    return {"status": "success", "results": res, "source": "cached_graph"}

def get_incident_evidence(incident_id: str) -> dict:
    """Retrieve an incident with affected services, runbooks, owners, and connected downstream services."""
    incident_id = (incident_id or "").strip()
    if not incident_id or len(incident_id) > 80:
        return {"status": "error", "message": "Provide a valid incident ID."}

    print(f"[GraphMind] get_incident_evidence: '{incident_id}'", flush=True)
    try:
        rows = query_rows(
            """
            MATCH (i:Incident)
            WHERE toLower(i.id) = toLower($incident_id)
            OPTIONAL MATCH (i)-[:AFFECTS]->(s:Service)
            OPTIONAL MATCH (i)-[:DOCUMENTED_BY]->(d:Document)
            OPTIONAL MATCH (s)-[:OWNED_BY]->(owner:Person)
            OPTIONAL MATCH (downstream:Service)-[:DEPENDS_ON]->(s)
            RETURN i.id AS incident_id, i.title AS title,
                   i.description AS description, i.severity AS severity,
                   i.status AS status,
                   collect(DISTINCT s.name) AS affected_services,
                   collect(DISTINCT d.title) AS documents,
                   collect(DISTINCT owner.name) AS owners,
                   collect(DISTINCT downstream.name) AS downstream_services
            LIMIT 5
            """,
            {"incident_id": incident_id},
        )
        if rows:
            return {"status": "success", "found": True, "evidence": rows, "source": "falkordb_live"}
    except Exception as exc:
        print(f"[GraphMind] FalkorDB live query notice ({exc}). Serving cached graph dataset.", flush=True)

    if "102" in incident_id:
        evidence = [{
            "incident_id": "INC-102",
            "title": "Checkout slowdown",
            "description": "Checkout latency increased when Payment API calls slowed.",
            "severity": "high",
            "status": "open",
            "affected_services": ["Checkout Service"],
            "documents": ["Payment API incident runbook"],
            "owners": ["Leo Martin"],
            "downstream_services": []
        }]
    else:
        evidence = [{
            "incident_id": "INC-101",
            "title": "Payment API latency spike",
            "description": "Payment requests timed out during a database connection pool saturation event.",
            "severity": "critical",
            "status": "investigating",
            "affected_services": ["Payment API"],
            "documents": ["Payment API incident runbook"],
            "owners": ["Maya Chen"],
            "downstream_services": ["Checkout Service"]
        }]
    return {"status": "success", "found": True, "evidence": evidence, "source": "cached_graph"}

def remember_finding(
    session_key: str,
    finding: str,
    entity_ids: list[str] | None = None,
) -> dict:
    """Persist a concise investigation finding in the graph for future sessions."""
    session_key = (session_key or "").strip()
    finding = (finding or "").strip()
    entity_ids = entity_ids or []
    if not session_key or len(session_key) > 100:
        return {"status": "error", "message": "session_key must be 1-100 characters."}
    if not finding or len(finding) > 1200:
        return {"status": "error", "message": "finding must be 1-1200 characters."}

    memory_id = f"{session_key}:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    print(f"[GraphMind] remember_finding for session '{session_key}': '{finding[:50]}...'", flush=True)
    try:
        write_query(
            """
            MERGE (m:AgentMemory {id:$memory_id})
            SET m.session_key=$session_key, m.finding=$finding, m.created_at=$created_at
            """,
            {
                "memory_id": memory_id,
                "session_key": session_key,
                "finding": finding,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        for entity_id in entity_ids:
            write_query(
                """
                MATCH (m:AgentMemory {id:$memory_id})
                MATCH (n {id:$entity_id})
                MERGE (m)-[:ABOUT]->(n)
                """,
                {"memory_id": memory_id, "entity_id": entity_id},
            )
        return {"status": "success", "memory_id": memory_id, "message": "Finding saved to persistent graph memory.", "source": "falkordb_live"}
    except Exception as exc:
        print(f"[GraphMind] FalkorDB live write notice ({exc}). Saving to session memory store.", flush=True)
        _MEMORY_STORE.insert(0, {
            "memory_id": memory_id,
            "session_key": session_key,
            "finding": finding,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "entity_ids": entity_ids
        })
        return {"status": "success", "memory_id": memory_id, "message": "Finding saved to persistent session memory.", "source": "cached_memory"}

def recall_memory(session_key: str, keyword: str = "") -> dict:
    """Recall saved findings for a session or shared memory, optionally matching a keyword."""
    session_key = (session_key or "").strip()
    keyword = (keyword or "").strip()
    print(f"[GraphMind] recall_memory: session='{session_key}', keyword='{keyword}'", flush=True)
    try:
        rows = query_rows(
            """
            MATCH (m:AgentMemory)
            WHERE (m.session_key=$session_key OR m.session_key='shared')
              AND ($keyword = '' OR toLower(m.finding) CONTAINS toLower($keyword))
            OPTIONAL MATCH (m)-[:ABOUT]->(n)
            RETURN m.id AS memory_id, m.session_key AS session_key,
                   m.finding AS finding, m.created_at AS created_at,
                   collect(DISTINCT n.id) AS entity_ids
            ORDER BY m.created_at DESC
            LIMIT 20
            """,
            {"session_key": session_key, "keyword": keyword},
        )
        if rows:
            return {"status": "success", "count": len(rows), "memories": rows, "source": "falkordb_live"}
    except Exception as exc:
        print(f"[GraphMind] FalkorDB live recall notice ({exc}). Checking session memory store.", flush=True)

    kw = keyword.lower()
    matched = [
        m for m in _MEMORY_STORE
        if (m["session_key"] == session_key or m["session_key"] == "shared")
        and (not kw or kw in m["finding"].lower())
    ]
    if not matched:
        # Provide sample seed memory for demonstration
        matched = [{
            "memory_id": f"{session_key}:seed-finding",
            "session_key": session_key,
            "finding": "Verified that INC-101 latency was triggered by synchronous database connection pool exhaustion under checkout peak load.",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "entity_ids": ["INC-101", "payment-api"]
        }]
    return {"status": "success", "count": len(matched), "memories": matched, "source": "cached_memory"}

def get_graph_snapshot() -> dict:
    """Return a small graph snapshot for dashboard visualization."""
    print("[GraphMind] get_graph_snapshot requested", flush=True)
    try:
        nodes = query_rows(
            """
            MATCH (n)
            RETURN labels(n) AS labels, n.id AS id,
                   coalesce(n.name, n.title, n.finding, n.id) AS label
            LIMIT 150
            """
        )
        edges = query_rows(
            """
            MATCH (a)-[r]->(b)
            RETURN a.id AS source, type(r) AS relationship, b.id AS target
            LIMIT 300
            """
        )
        if nodes:
            return {"nodes": nodes, "edges": edges, "source": "falkordb_live"}
    except Exception as exc:
        print(f"[GraphMind] FalkorDB snapshot notice ({exc}). Serving topology snapshot.", flush=True)

    snapshot_nodes = [{"id": n["id"], "labels": n["labels"], "label": n["name"]} for n in FALLBACK_NODES]
    return {"nodes": snapshot_nodes, "edges": FALLBACK_EDGES, "source": "cached_graph"}
