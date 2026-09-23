from __future__ import annotations

import json
from datetime import datetime, timezone

from openai import AsyncOpenAI, OpenAIError

from app.config import Settings
from app.schemas import ChatRequest
from app.tools import TOOL_DEFINITIONS, execute_tool


SYSTEM_PROMPT = """
You are Oracle, the Operational Resource for Analysis,
Communication, and Logical Execution — a JARVIS-style personal assistant.

Always refer to yourself as Oracle (never spell it with dots).

You help with analysis, planning, Gmail, and Google Calendar through a text interface.

Rules:
- Prefer using tools for email and calendar questions instead of guessing.
- For send_email and create_calendar_event, ALWAYS call first with confirmed=false.
- Only call those tools with confirmed=true after the user clearly agrees
  (for example: "yes", "confirm", "send it", "create it").
- Confirm destructive or outbound actions before executing them.
- If Google is not connected, tell the user to run: python oracle.py --connect-google
- Use ISO 8601 datetimes with timezone offsets for calendar events.
- Current UTC time is provided below; infer local intent carefully from the user wording.
""".strip()


class MissingApiKeyError(RuntimeError):
    """Raised when the backend has no LLM API key configured."""


class LLMServiceError(RuntimeError):
    """Raised when the LLM provider request fails."""


def _build_system_prompt() -> str:
    now = datetime.now(timezone.utc).isoformat()
    return f"{SYSTEM_PROMPT}\n\nCurrent UTC time: {now}\nBe concise but complete."


def _extract_confirmation_flag(tool_payloads: list[str]) -> bool:
    for payload in tool_payloads:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("needs_confirmation"):
            return True
    return False


async def generate_chat_reply(request: ChatRequest, settings: Settings) -> tuple[str, bool]:
    if not settings.openai_api_key:
        raise MissingApiKeyError(
            "OPENAI_API_KEY is not configured. Copy .env.example to .env and add your API key."
        )

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
    messages: list[dict] = [
        {"role": "system", "content": _build_system_prompt()},
    ]
    messages.extend(message.model_dump() for message in request.history)
    messages.append({"role": "user", "content": request.message})

    confirmation_needed = False

    try:
        for _ in range(6):
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                temperature=0.3,
            )
            choice = response.choices[0].message
            tool_calls = choice.tool_calls or []

            if not tool_calls:
                reply = (choice.content or "").strip()
                if not reply:
                    raise LLMServiceError("LLM provider returned an empty response.")
                return reply, confirmation_needed

            messages.append(
                {
                    "role": "assistant",
                    "content": choice.content,
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                        for tool_call in tool_calls
                    ],
                }
            )

            tool_payloads: list[str] = []
            for tool_call in tool_calls:
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                payload = execute_tool(tool_call.function.name, arguments)
                tool_payloads.append(payload)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": payload,
                    }
                )

            if _extract_confirmation_flag(tool_payloads):
                confirmation_needed = True

    except OpenAIError as exc:
        raise LLMServiceError(f"LLM provider request failed: {exc}") from exc

    raise LLMServiceError("Tool-calling loop exceeded the maximum number of steps.")
