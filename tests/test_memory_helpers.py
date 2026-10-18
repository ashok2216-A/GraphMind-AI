from graphmind.memory import _id, ALLOWED_TYPES

def test_memory_id_is_stable():
    assert _id("demo", "Payment API is slow", "semantic") == _id("demo", "Payment API is slow", "semantic")

def test_memory_id_is_org_scoped():
    assert _id("org-a", "same fact", "semantic") != _id("org-b", "same fact", "semantic")

def test_memory_types():
    assert {"episodic", "semantic", "procedural", "decision"} == ALLOWED_TYPES
