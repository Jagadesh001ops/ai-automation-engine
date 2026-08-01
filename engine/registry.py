"""Central node registry — single source of truth for available step types.

The registry replaces the hardcoded SPECIALIST_NODES dict and SPECIALIST_PREFIXES
list in llm_nodes.py.  Every node type is registered once here; both the intent
parser (to know what steps to plan) and the execution engine (to build nodes at
runtime) consult this registry.

Adding a new step type means adding one NodeEntry — the routing, planner prompt
injection, and introspection all update automatically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Type


@dataclass
class NodeEntry:
    """Metadata for one registered node type."""
    name: str                        # canonical name used in plans
    description: str                 # one-sentence description shown to the planner
    node_class: type                 # the class to instantiate
    aliases: List[str] = field(default_factory=list)   # alternative step names
    prefixes: List[str] = field(default_factory=list)  # match any step starting with these


class NodeRegistry:
    """Registry of available node types.

    Usage:
        registry = NodeRegistry()
        registry.register(NodeEntry(...))
        NodeClass = registry.resolve("summarize_document")
        metadata  = registry.describe()   # list for planner prompt injection
    """

    def __init__(self):
        self._entries: List[NodeEntry] = []
        # flat lookup: canonical name + aliases -> NodeEntry
        self._by_name: dict[str, NodeEntry] = {}

    def register(self, entry: NodeEntry) -> None:
        self._entries.append(entry)
        self._by_name[entry.name] = entry
        for alias in entry.aliases:
            self._by_name[alias] = entry

    def resolve(self, step_name: str) -> Optional[type]:
        """Return the node class for *step_name*, or None if unknown."""
        key = step_name.strip().lower().replace("-", "_")
        entry = self._by_name.get(key)
        if entry:
            return entry.node_class
        # Prefix matching (e.g. "summarize_chapter" -> SummarizeNode)
        for e in self._entries:
            for prefix in e.prefixes:
                if key.startswith(prefix):
                    return e.node_class
        return None

    def describe(self) -> List[dict]:
        """Return a list of {name, description} dicts for planner prompt injection."""
        return [
            {"name": e.name, "description": e.description}
            for e in self._entries
        ]

    def names(self) -> List[str]:
        return [e.name for e in self._entries]


# ─── Default registry (populated by llm_nodes on import) ─────────────────────

_default: Optional[NodeRegistry] = None


def get_registry() -> NodeRegistry:
    """Return the process-wide registry (initialised on first call)."""
    global _default
    if _default is None:
        from engine import llm_nodes  # noqa: F401 — triggers registration
        assert _default is not None, "llm_nodes failed to register nodes"
    return _default


def _set_registry(r: NodeRegistry) -> None:
    """Called by llm_nodes during module init to install the default registry."""
    global _default
    _default = r
