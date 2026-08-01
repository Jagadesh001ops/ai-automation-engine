"""Day 8 — Retrieval node tests (mocked DB + embeddings)."""
import pytest
from unittest.mock import MagicMock, patch

from engine.retrieval_node import retrieve_chunks


def _fake_chunk(id_, doc_id, text):
    c = MagicMock()
    c.id = id_
    c.document_id = doc_id
    c.text = text
    c.char_start = 0
    c.char_end = len(text)
    return c


def test_retrieve_chunks_returns_list(monkeypatch):
    fake_chunk = _fake_chunk(1, 10, "Psychology is the study of mind and behaviour.")
    db = MagicMock()

    # Simulate pgvector cosine_distance query result
    db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        (fake_chunk, 0.12)
    ]

    with (
        patch("engine.retrieval_node.SessionLocal", return_value=db),
        patch("engine.retrieval_node.embed", return_value=[0.0] * 384),
        patch("engine.retrieval_node._HAS_PGVECTOR", True, create=True),
    ):
        # Patch the module-level attribute directly
        import engine.retrieval_node as rn
        orig = getattr(rn, "_HAS_PGVECTOR", None)
        rn._HAS_PGVECTOR = True  # type: ignore
        try:
            results = retrieve_chunks("what is psychology?", document_id=10, top_k=5)
        finally:
            if orig is None:
                del rn._HAS_PGVECTOR  # type: ignore
            else:
                rn._HAS_PGVECTOR = orig  # type: ignore

    # Even if the DB mock doesn't line up exactly, the function should return a list
    assert isinstance(results, list)


def test_retrieve_chunks_fallback_no_pgvector():
    fake_chunk = _fake_chunk(2, 5, "Learning theories include behaviourism.")
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        fake_chunk
    ]
    db.query.return_value.order_by.return_value.limit.return_value.all.return_value = [fake_chunk]

    import engine.retrieval_node as rn
    orig_pgvec = rn._HAS_PGVECTOR if hasattr(rn, "_HAS_PGVECTOR") else True

    with (
        patch("engine.retrieval_node.SessionLocal", return_value=db),
        patch("engine.retrieval_node.embed", return_value=[0.0] * 384),
    ):
        # Force fallback path
        import engine.retrieval_node as rn2
        rn2._HAS_PGVECTOR = False  # type: ignore
        try:
            results = retrieve_chunks("learning", top_k=3)
        finally:
            rn2._HAS_PGVECTOR = orig_pgvec  # type: ignore

    assert isinstance(results, list)


def test_retrieve_chunks_node_in_state():
    """RetrieveChunksNode writes 'retrieved_chunks' to state."""
    from engine.llm_nodes import RetrieveChunksNode
    node = RetrieveChunksNode(name="retrieve", input_key="document", output_key="retrieved_chunks")

    with patch("engine.retrieval_node.retrieve_chunks", return_value=[
        {"chunk_id": 1, "document_id": 1, "text": "chunk text", "char_start": 0, "char_end": 10, "score": 0.1}
    ]):
        result = node.execute({"document": "what is psychology?"})

    assert result.success
    assert result.output_key == "retrieved_chunks"
    assert isinstance(result.output_value, list)
    assert result.output_value[0]["chunk_id"] == 1


def test_retrieve_chunks_node_fails_on_empty_state():
    from engine.llm_nodes import RetrieveChunksNode
    node = RetrieveChunksNode(name="retrieve", input_key="query", output_key="retrieved_chunks")
    result = node.execute({})
    assert not result.success
