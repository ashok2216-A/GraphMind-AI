import os
from dotenv import load_dotenv
from falkordb import FalkorDB

load_dotenv()

def get_graph():
    raw_url = os.getenv("FALKORDB_URL")
    url = raw_url.strip().strip('"').strip("'") if raw_url else None
    if url:
        db = FalkorDB.from_url(url)
    else:
        raw_host = os.getenv("FALKORDB_HOST", "localhost")
        host = raw_host.strip().strip('"').strip("'") if raw_host else "localhost"
        port = int(os.getenv("FALKORDB_PORT", "6379"))
        kwargs = {}
        raw_user = os.getenv("FALKORDB_USERNAME")
        raw_pass = os.getenv("FALKORDB_PASSWORD")
        username = raw_user.strip().strip('"').strip("'") if raw_user else None
        password = raw_pass.strip().strip('"').strip("'") if raw_pass else None
        ssl_val = os.getenv("FALKORDB_SSL", "false").lower() in ("true", "1", "yes")

        if username:
            kwargs["username"] = username
        if password:
            kwargs["password"] = password
        if ssl_val:
            kwargs["ssl"] = True

        db = FalkorDB(host=host, port=port, **kwargs)

    graph_name = os.getenv("FALKORDB_GRAPH", "graphmind").strip().strip('"').strip("'")
    return db.select_graph(graph_name)

def query_rows(query: str, params: dict | None = None) -> list[dict]:
    """Execute a parameterized, read-only Cypher query and normalize rows."""
    graph = get_graph()
    result = graph.ro_query(query, params or {})
    headers = [
        h.decode("utf-8") if isinstance(h, bytes) else str(h)
        for h in result.header
    ]
    rows = []
    for row in result.result_set:
        clean = []
        for value in row:
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            clean.append(value)
        rows.append(dict(zip(headers, clean)))
    return rows

def write_query(query: str, params: dict | None = None):
    """Internal helper for trusted, fixed seed/write statements only."""
    graph = get_graph()
    return graph.query(query, params or {})
