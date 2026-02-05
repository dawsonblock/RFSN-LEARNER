# controller/context_builder.py
"""
Build context from chat history + optional memory recall.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class ContextConfig:
    """Configuration for context building."""
    max_turns: int = 12
    max_mem_items: int = 6
    recall: bool = True


def _fmt(role: str, text: str) -> str:
    """Format a single turn."""
    r = role.lower().strip()
    if r not in ("user", "assistant", "tool"):
        r = "user"
    return f"{r.upper()}: {text}"


def build_context(
    *,
    chat_history: Sequence[tuple[str, str]],
    user_text: str,
    memory: Any | None = None,
    cfg: ContextConfig | None = None,
) -> str:
    """
    Build context block for LLM prompt.
    
    Args:
        chat_history: List of (role, text) tuples
        user_text: Current user input (for memory recall)
        memory: Optional memory store with .search() method
        cfg: Context configuration
    
    Returns:
        Formatted context string
    """
    if cfg is None:
        cfg = ContextConfig()
    
    turns = chat_history[-cfg.max_turns:] if cfg.max_turns > 0 else list(chat_history)
    out: list[str] = []

    # Memory recall (best-effort; safe to skip if store absent)
    if cfg.recall and memory is not None:
        try:
            if hasattr(memory, "search"):
                hits = memory.search(user_text, limit=cfg.max_mem_items)
                if hits:
                    out.append("MEMORY (recalled):")
                    for h in hits:
                        if isinstance(h, dict):
                            k = str(h.get("key", ""))
                            v = str(h.get("value", ""))
                        else:
                            k, v = "", str(h)
                        line = f"- {k}: {v}".strip() if k else f"- {v}"
                        out.append(line)
                    out.append("")
        except Exception:
            # Don't break chat if memory search fails
            pass

    if turns:
        out.append("CHAT (recent):")
        for role, text in turns:
            out.append(_fmt(role, text))
        out.append("")

    out.append("INSTRUCTION:")
    out.append("Propose the next actions as JSON.")
    return "\n".join(out)
