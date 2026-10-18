from .db import write_query

# Synthetic demo data only. MERGE makes seeding safe to repeat.
SEED_QUERIES = [
    ("""
    MERGE (c:Company {id:'acme'})
    SET c.name='Acme Commerce', c.description='Synthetic demo company'
    """, {}),
    ("""
    MERGE (team:Team {id:'platform'})
    SET team.name='Platform Engineering'
    MERGE (team2:Team {id:'commerce'})
    SET team2.name='Commerce'
    """, {}),
    ("""
    MERGE (p:Person {id:'maya'})
    SET p.name='Maya Chen', p.role='Platform Lead'
    MERGE (p2:Person {id:'leo'})
    SET p2.name='Leo Martin', p2.role='Commerce Engineer'
    """, {}),
    ("""
    MERGE (s:Service {id:'payment-api'})
    SET s.name='Payment API', s.status='degraded'
    MERGE (s2:Service {id:'payment-db'})
    SET s2.name='Payment Database', s2.status='healthy'
    MERGE (s3:Service {id:'checkout'})
    SET s3.name='Checkout Service', s3.status='degraded'
    """, {}),
    ("""
    MERGE (pr:Project {id:'checkout-modernization'})
    SET pr.name='Checkout Modernization', pr.status='at risk'
    MERGE (d:Decision {id:'dec-001'})
    SET d.title='Keep payment writes synchronous', d.summary='The team chose synchronous writes for consistency.', d.date='2026-09-12'
    MERGE (doc:Document {id:'runbook-001'})
    SET doc.title='Payment API incident runbook', doc.content='Check Payment API latency, database connection pool saturation, and downstream Checkout errors. Escalate to Platform Engineering.'
    MERGE (inc:Incident {id:'INC-101'})
    SET inc.title='Payment API latency spike', inc.description='Payment requests timed out during a database connection pool saturation event.', inc.severity='critical', inc.status='investigating'
    MERGE (inc2:Incident {id:'INC-102'})
    SET inc2.title='Checkout slowdown', inc2.description='Checkout latency increased when Payment API calls slowed.', inc2.severity='high', inc2.status='open'
    """, {}),
    ("""
    MATCH (c:Company {id:'acme'}), (team:Team {id:'platform'}), (team2:Team {id:'commerce'})
    MERGE (c)-[:HAS_TEAM]->(team)
    MERGE (c)-[:HAS_TEAM]->(team2)
    """, {}),
    ("""
    MATCH (p:Person {id:'maya'}), (p2:Person {id:'leo'}), (team:Team {id:'platform'}), (team2:Team {id:'commerce'})
    MERGE (p)-[:MEMBER_OF]->(team)
    MERGE (p2)-[:MEMBER_OF]->(team2)
    """, {}),
    ("""
    MATCH (s:Service {id:'payment-api'}), (s2:Service {id:'payment-db'}), (s3:Service {id:'checkout'})
    MERGE (s)-[:DEPENDS_ON]->(s2)
    MERGE (s3)-[:DEPENDS_ON]->(s)
    """, {}),
    ("""
    MATCH (inc:Incident {id:'INC-101'}), (s:Service {id:'payment-api'}), (doc:Document {id:'runbook-001'}), (p:Person {id:'maya'})
    MERGE (inc)-[:AFFECTS]->(s)
    MERGE (inc)-[:DOCUMENTED_BY]->(doc)
    MERGE (s)-[:OWNED_BY]->(p)
    """, {}),
    ("""
    MATCH (inc:Incident {id:'INC-102'}), (s:Service {id:'checkout'}), (pr:Project {id:'checkout-modernization'})
    MERGE (inc)-[:AFFECTS]->(s)
    MERGE (pr)-[:USES]->(s)
    """, {}),
    ("""
    MATCH (d:Decision {id:'dec-001'}), (s:Service {id:'payment-api'}), (pr:Project {id:'checkout-modernization'}), (doc:Document {id:'runbook-001'})
    MERGE (d)-[:GOVERNS]->(s)
    MERGE (d)-[:RELEVANT_TO]->(pr)
    MERGE (doc)-[:DESCRIBES]->(s)
    """, {}),
]

def seed():
    for query, params in SEED_QUERIES:
        write_query(query, params)
    return {"status": "ok", "message": "Synthetic GraphMind graph seeded."}

if __name__ == "__main__":
    print(seed())
