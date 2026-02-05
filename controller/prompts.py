# controller/prompts.py
"""
System and user prompts for the agent loop.
"""
from __future__ import annotations

SYSTEM_PROMPT = """You are an assistant that MUST output a single JSON object and nothing else.

You propose actions. A safety gate will allow/deny each action.
If a tool is denied, continue with other actions or ask for permission.

You MUST follow this schema:

{
  "actions": [
    {
      "kind": "<string>",
      "payload": { ... }
    }
  ]
}

Allowed kinds:
- "message_send": payload {"message": "<string>"}
- "tool_call": payload {"tool": "<string>", "args": {...}}
- "memory_write": payload {"key": "<string>", "value": "<string>", "tags": ["..."]?}
- "permission_request": payload {"request": "<string>", "why": "<string>"}

Rules:
- Usually propose 1-3 actions.
- If you can answer directly, do only "message_send".
- Use "tool_call" only if needed.
- If a tool might be sensitive, do "permission_request" first.
- Never output markdown. JSON only.
"""


def user_prompt(*, user_text: str, context_block: str) -> str:
    """Build user prompt with context."""
    return f"""Context:
{context_block}

User:
{user_text}

Return JSON only."""
