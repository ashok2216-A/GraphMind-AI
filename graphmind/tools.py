"""Safe, narrow tools exposed to Google ADK.

No tool accepts arbitrary Cypher. User values are always parameters, and all
agent-facing graph access is read-only. Writes are limited to the validated
memory tool below.
"""
import json
from datetime import datetime, timezone
from .db import query_rows, write_query

def search_company_knowledge(keyword: str) -> dict:
    """Search synthetic company incidents, services, documents, projects, and decisions."""
    keyword = (keyword or "").strip()
    if not keyword or len(keyword) > 160:
        return {"status": "error", "message": "Provide a keyword of 1-160 characters."}
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
    return {"status": "success", "count": len(rows), "results": rows}

def trace_service_dependencies(service_name: str) -> dict:
    """Trace up to four dependency hops from a named service and return owners and related incidents."""
    service_name = (service_name or "").strip()
    if not service_name or len(service_name) > 120:
        return {"status": "error", "message": "Provide a service name of 1-120 characters."}
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
    return {"status": "success", "results": rows}

def get_incident_evidence(incident_id: str) -> dict:
    """Retrieve an incident with affected services, runbooks, owners, and connected downstream services."""
    incident_id = (incident_id or "").strip()
    if not incident_id or len(incident_id) > 80:
        return {"status": "error", "message": "Provide a valid incident ID."}
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
    return {"status": "success", "found": bool(rows), "evidence": rows}

def remember_finding(
    session_key: str,
    finding: str,
    entity_ids: list[str] | None = None,
) -> dict:
    """Persist a concise investigation finding in the graph for future sessions.

    Store only synthetic/demo or non-sensitive information. Keep finding under
    1200 characters and entity_ids to a short list of existing entity IDs.
    """
    session_key = (session_key or "").strip()
    finding = (finding or "").strip()
    entity_ids = entity_ids or []
    if not session_key or len(session_key) > 100:
        return {"status": "error", "message": "session_key must be 1-100 characters."}
    if not finding or len(finding) > 1200:
        return {"status": "error", "message": "finding must be 1-1200 characters."}
    if len(entity_ids) > 10 or any(not isinstance(x, str) or len(x) > 100 for x in entity_ids):
        return {"status": "error", "message": "Provide at most 10 short entity IDs."}

    memory_id = f"{session_key}:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
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
    # Link to entities only through a parameterized ID match.
    for entity_id in entity_ids:
        write_query(
            """
            MATCH (m:AgentMemory {id:$memory_id})
            MATCH (n {id:$entity_id})
            MERGE (m)-[:ABOUT]->(n)
            """,
            {"memory_id": memory_id, "entity_id": entity_id},
        )
    return {"status": "success", "memory_id": memory_id, "message": "Finding saved to persistent graph memory."}

def recall_memory(session_key: str, keyword: str = "") -> dict:
    """Recall saved findings for a session or shared memory, optionally matching a keyword."""
    session_key = (session_key or "").strip()
    keyword = (keyword or "").strip()
    if not session_key or len(session_key) > 100 or len(keyword) > 160:
        return {"status": "error", "message": "Invalid session key or keyword."}
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
    return {"status": "success", "count": len(rows), "memories": rows}

def get_graph_snapshot() -> dict:
    """Return a small graph snapshot for dashboard visualization."""
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
    return {"nodes": nodes, "edges": edges}
