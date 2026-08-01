"""Day 6 — Dynamic node registry tests."""
import pytest
from engine.registry import NodeRegistry, NodeEntry, get_registry


def test_registry_resolves_canonical_name():
    r = get_registry()
    assert r.resolve("summarize") is not None


def test_registry_resolves_alias():
    r = get_registry()
    assert r.resolve("summarize_document") is r.resolve("summarize")


def test_registry_resolves_prefix():
    r = get_registry()
    assert r.resolve("summarize_chapter") is r.resolve("summarize")


def test_registry_returns_none_for_unknown():
    r = get_registry()
    assert r.resolve("nonexistent_step_xyz") is None


def test_registry_describe_returns_all_nodes():
    r = get_registry()
    desc = r.describe()
    names = [d["name"] for d in desc]
    assert "summarize" in names
    assert "extract_concepts" in names
    assert "generate_quiz" in names
    assert "retrieve_chunks" in names
    assert "verify_quiz" in names


def test_registry_describe_has_descriptions():
    r = get_registry()
    for entry in r.describe():
        assert entry["description"], f"{entry['name']} has no description"


def test_build_node_for_step_uses_registry():
    from engine.llm_nodes import build_node_for_step, SummarizeNode
    node = build_node_for_step("summarize_document", "summarise", "document", "summary")
    assert isinstance(node, SummarizeNode)


def test_build_node_for_step_falls_back_to_llm_node():
    from engine.llm_nodes import build_node_for_step, LLMNode
    node = build_node_for_step("totally_custom_step", "do something", "input", "output")
    assert isinstance(node, LLMNode)
