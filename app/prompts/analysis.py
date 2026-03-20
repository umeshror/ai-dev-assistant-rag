"""
app/prompts/analysis.py
──────────────────────────────────────────────────────────────────────────────
Prompt engineering layer for the AI Developer Assistant.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import List, Sequence

from openai.types.chat import ChatCompletionMessageParam

# ── Constants ────────────────────────────────────────────────────────────────

_SYSTEM_ROLE = "system"
_USER_ROLE = "user"

_REQUIRED_JSON_SCHEMA = """\
{
  "violations": ["<string>", "..."],
  "security_risks": ["<string>", "..."],
  "suggestions": ["<string>", "..."]
}"""

_SYSTEM_PROMPT = f"""\
You are a Senior Security Engineer at a large enterprise.
Your task is to audit code, Terraform configurations, and YAML files against \
internal security and compliance policies.

STRICT OUTPUT REQUIREMENTS:
- Respond ONLY with a single valid JSON object. No markdown, no prose, no code fences.
- The JSON object MUST contain exactly these three keys with array values:

{_REQUIRED_JSON_SCHEMA}

- Base your analysis SOLELY on the policies listed in the POLICY CONTEXT section.
"""


def build_analysis_prompt(
    retrieved_policies: Sequence[str],
    code_snippet: str,
    code_type: str,
) -> List[ChatCompletionMessageParam]:
    """Construct the chat message list for an analysis request."""
    policy_context = _format_policies(retrieved_policies)
    user_message = _build_user_message(code_snippet, code_type, policy_context)

    messages: List[ChatCompletionMessageParam] = [
        {"role": _SYSTEM_ROLE, "content": _SYSTEM_PROMPT},
        {"role": _USER_ROLE, "content": user_message},
    ]
    return messages


def _format_policies(policies: Sequence[str]) -> str:
    """Format retrieved policies into a numbered list."""
    if not policies:
        return "Apply general security best practices only."

    lines: List[str] = []
    for i, policy in enumerate(policies, start=1):
        cleaned = policy.strip()
        if cleaned:
            lines.append(f"  {i}. {cleaned}")

    return "\n".join(lines)


def _build_user_message(
    code_snippet: str,
    code_type: str,
    policy_context: str,
) -> str:
    """Construct the user-turn message."""
    return f"""\
=== POLICY CONTEXT ===
{policy_context}

=== CODE TO ANALYZE ===
Type: {code_type.upper()}

```
{code_snippet}
```

=== TASK ===
Analyze the code above against the policies listed above.
Return ONLY a JSON object with exactly these keys:

{_REQUIRED_JSON_SCHEMA}
"""
