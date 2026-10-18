"""Persistent, organization-scoped memory stored in FalkorDB.

Memory types: episodic (investigations), semantic (facts/lessons), procedural
(runbook/solutions), and decision. This module deliberately accepts only
structured values; it never executes model-generated Cypher.
"""
from __future__ import annotations
import hashlib, json, os, re
from datetime import datetime, timezone, timedelta
from .db import query_rows, write_query

ALLOWED_TYPES = {"episodic", "semantic", "procedural", "decision"}

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def _safe(s: str, limit: int = 160) -> str:
    return (s or "").strip()[:limit]

def _id(org_id: str, content: str, memory_type: str) -> str:
    raw = f"{org_id}|{memory_type}|{content.casefold()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]

def save_memory(*, org_id: str, content: str, memory_type: str = "semantic",
                source: str = "investigation", session_id: str = "", user_id: str = "",
                entity_ids: list[str] | None = None, confidence: float = 0.75,
                evidence: str = "", ttl_days: int | None = None) -> dict:
    org_id = _safe(org_id, 100)
    content = (content or "").strip()[:1800]
    memory_type = _safe(memory_type, 24).lower()
    if not org_id or not content:
        return {"status": "error", "message": "org_id and content are required"}
    if memory_type not in ALLOWED_TYPES:
        memory_type = "semantic"
    confidence = max(0.0, min(1.0, float(confidence)))
    entity_ids = [str(x)[:100] for x in (entity_ids or [])[:12] if str(x).strip()]
    memory_id = _id(org_id, content, memory_type)
    created = now_iso()
    if ttl_days is None:
        ttl_days = int(os.getenv("MEMORY_TTL_DAYS", "0"))
    expires = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat() if ttl_days > 0 else ""
    # MERGE by stable hash makes repeated extraction idempotent; last_seen is refreshed.
    write_query("""
        MERGE (m:AgentMemory {id:$memory_id})
        ON CREATE SET m.created_at=$created_at, m.org_id=$org_id, m.content=$content, m.memory_type=$memory_type, m.source=$source, m.session_id=$session_id, m.user_id=$user_id, m.confidence=$confidence, m.evidence=$evidence, m.expires_at=$expires_at, m.status='active', m.recall_count=0
        SET m.last_seen=$created_at, m.confidence=CASE WHEN m.confidence < $confidence THEN $confidence ELSE m.confidence END
        """, {"memory_id":memory_id,"created_at":created,"org_id":org_id,"content":content,"memory_type":memory_type,"source":_safe(source,80),"session_id":_safe(session_id,120),"user_id":_safe(user_id,120),"confidence":confidence,"evidence":(evidence or "")[:1000],"expires_at":expires})
    # Only link to entities belonging to the same organization, when that property exists.
    for entity_id in entity_ids:
        write_query("""
            MATCH (m:AgentMemory {id:$memory_id, org_id:$org_id})
            MATCH (n {id:$entity_id})
            WHERE n.org_id IS NULL OR n.org_id=$org_id
            MERGE (m)-[:ABOUT]->(n)
            """, {"memory_id":memory_id,"org_id":org_id,"entity_id":entity_id})
    return {"status":"success","memory_id":memory_id,"memory_type":memory_type,"message":"Memory saved to FalkorDB."}

def recall_memories(*, org_id: str, query: str = "", session_id: str = "", user_id: str = "", limit: int = 8) -> dict:
    org_id = _safe(org_id,100); query = _safe(query,200).lower()
    if not org_id:
        return {"status":"error","message":"org_id is required","memories":[]}
    limit = max(1, min(int(limit), 20))
    # Graph keyword recall: safely parameterized. Semantic/vector recall can be added later.
    rows = query_rows("""
        MATCH (m:AgentMemory {org_id:$org_id, status:'active'})
        WHERE (m.expires_at IS NULL OR m.expires_at='' OR m.expires_at > $now)
          AND ($query='' OR toLower(m.content) CONTAINS $query OR toLower(coalesce(m.evidence,'')) CONTAINS $query OR toLower(coalesce(m.memory_type,'')) CONTAINS $query)
        OPTIONAL MATCH (m)-[:ABOUT]->(n)
        RETURN m.id AS memory_id, m.content AS content, m.memory_type AS memory_type,
               m.source AS source, m.session_id AS session_id, m.user_id AS user_id,
               m.created_at AS created_at, m.last_seen AS last_seen, m.confidence AS confidence,
               m.evidence AS evidence, collect(DISTINCT n.id) AS entity_ids
        ORDER BY m.created_at DESC LIMIT $limit
        """, {"org_id":org_id,"query":query,"now":now_iso(),"limit":limit})
    # Shared org memory is returned across sessions; personal-only memories are filtered.
    filtered=[]
    for row in rows:
        if row.get("user_id") and row.get("user_id") != user_id:
            continue
        filtered.append(row)
    # Update recall counters without making retrieval depend on a write succeeding.
    for row in filtered:
        try:
            write_query("MATCH (m:AgentMemory {id:$id, org_id:$org_id}) SET m.recall_count=coalesce(m.recall_count,0)+1, m.last_recalled=$now", {"id":row["memory_id"],"org_id":org_id,"now":now_iso()})
        except Exception:
            pass
    return {"status":"success","count":len(filtered),"memories":filtered}

def list_memories(org_id: str, limit: int = 50) -> dict:
    rows=query_rows("MATCH (m:AgentMemory {org_id:$org_id, status:'active'}) RETURN m.id AS memory_id,m.content AS content,m.memory_type AS memory_type,m.source AS source,m.created_at AS created_at,m.confidence AS confidence,m.user_id AS user_id ORDER BY m.created_at DESC LIMIT $limit", {"org_id":_safe(org_id,100),"limit":max(1,min(int(limit),100))})
    return {"status":"success","count":len(rows),"memories":rows}

def forget_memory(org_id: str, memory_id: str) -> dict:
    # Soft delete preserves auditability while excluding it from recall.
    write_query("MATCH (m:AgentMemory {id:$id, org_id:$org_id}) SET m.status='deleted', m.deleted_at=$now RETURN m.id AS id", {"id":_safe(memory_id,100),"org_id":_safe(org_id,100),"now":now_iso()})
    return {"status":"success","message":"Memory marked deleted if it existed in this organization."}

def save_conversation_turn(*, org_id: str, session_id: str, user_id: str, role: str, content: str) -> dict:
    content=(content or "").strip()[:5000]
    if role not in {"user","assistant"} or not org_id or not session_id or not content:
        return {"status":"error","message":"Invalid conversation turn"}
    # Sequential timestamp+hash ID. Store full turn in graph for restart-safe history.
    created=now_iso(); raw=f"{org_id}|{session_id}|{role}|{created}|{content}".encode(); turn_id=hashlib.sha256(raw).hexdigest()[:32]
    write_query("MERGE (t:ConversationTurn {id:$id}) SET t.org_id=$org_id,t.session_id=$session_id,t.user_id=$user_id,t.role=$role,t.content=$content,t.created_at=$created", {"id":turn_id,"org_id":org_id,"session_id":session_id,"user_id":user_id,"role":role,"content":content,"created":created})
    return {"status":"success","turn_id":turn_id}

def get_conversation_history(*, org_id: str, session_id: str, user_id: str = "", limit: int = 12) -> list[dict]:
    rows=query_rows("MATCH (t:ConversationTurn {org_id:$org_id, session_id:$session_id}) WHERE t.user_id=$user_id OR $user_id='' RETURN t.role AS role,t.content AS content,t.created_at AS created_at ORDER BY t.created_at DESC LIMIT $limit", {"org_id":_safe(org_id,100),"session_id":_safe(session_id,120),"user_id":_safe(user_id,120),"limit":max(1,min(int(limit),30))})
    return list(reversed(rows))

def auto_extract_memories(*, org_id: str, session_id: str, user_id: str, user_message: str, assistant_message: str, entity_ids: list[str] | None = None) -> dict:
    """Extract reusable memories using Gemini when configured; deterministic fallback otherwise."""
    transcript=f"USER: {user_message[:2500]}\nASSISTANT: {assistant_message[:3500]}"
    candidates=[]
    api_key=os.getenv("GOOGLE_API_KEY")
    if api_key and assistant_message.strip():
        try:
            import json
            from google import genai
            client=genai.Client(api_key=api_key)
            prompt=("Extract 0-3 durable, reusable company memories from this investigation. "
                    "Only include factual conclusions, decisions, incident causes, resolutions, or lessons. "
                    "Do not store questions, greetings, speculation, secrets, or personal data. "
                    "Return JSON only: {\"memories\":[{\"content\":\"...\",\"type\":\"semantic|episodic|procedural|decision\",\"confidence\":0.0,\"evidence\":\"...\"}]}\n\n"+transcript)
            response=client.models.generate_content(model=os.getenv("GRAPHMIND_MODEL","gemini-2.5-flash"), contents=prompt)
            raw=(response.text or "").strip()
            raw=re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I)
            data=json.loads(raw)
            candidates=data.get("memories",[])[:3]
        except Exception:
            candidates=[]
    # Safe fallback: save a short episodic summary only if both sides have substance.
    if not candidates and len(user_message.strip()) > 20 and len(assistant_message.strip()) > 60:
        # Avoid recording empty/low-value answers. Clearly label as a session summary.
        candidates=[{"content":f"Investigation summary: User asked: {user_message[:350]}. GraphMind response: {assistant_message[:650]}","type":"episodic","confidence":0.55,"evidence":"Auto-generated fallback summary; verify before treating as fact."}]
    saved=[]
    for item in candidates:
        content=str(item.get("content","")).strip()[:1800]
        if len(content)<20: continue
        result=save_memory(org_id=org_id,content=content,memory_type=str(item.get("type","semantic")),source="auto-extraction",session_id=session_id,user_id="",entity_ids=entity_ids,confidence=float(item.get("confidence",0.65)),evidence=str(item.get("evidence","")))
        if result.get("status")=="success": saved.append(result)
    return {"status":"success","saved_count":len(saved),"saved":saved}
