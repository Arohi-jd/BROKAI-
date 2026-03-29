import os
import queue
import threading
from typing import Any, Dict

try:
    from langchain_groq import ChatGroq
except Exception:
    ChatGroq = None

from langchain_google_genai import ChatGoogleGenerativeAI


USE_GROQ = bool(os.getenv("GROQ_API_KEY"))

MODEL_CANDIDATES = (
    ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]
    if USE_GROQ
    else ["gemini-1.5-flash"]
)

LLM_DISABLED = False


if USE_GROQ and ChatGroq is not None:
    llm = ChatGroq(
        model=MODEL_CANDIDATES[0],
        groq_api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.5,
        max_retries=0,
        timeout=8,
    )
else:
    llm = ChatGoogleGenerativeAI(
        model=MODEL_CANDIDATES[0],
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0.5,
        max_retries=0,
        timeout=8,
    )


def _safe_text(value: object) -> str:
    """Convert an arbitrary value to a trimmed string."""
    return str(value or "").strip()


def _invoke_gemini(prompt: str):
    """Call configured LLM (Groq or Gemini) with model fallbacks and return a response object."""
    global LLM_DISABLED

    if LLM_DISABLED:
        raise RuntimeError("LLM disabled after previous hard failure")

    def _invoke_with_timeout(model: Any, request_prompt: str, timeout_seconds: int = 10):
        """Invoke a model with a hard timeout to avoid blocking request processing."""
        result_queue: queue.Queue = queue.Queue(maxsize=1)

        def _runner():
            try:
                result_queue.put((True, model.invoke(request_prompt)))
            except Exception as inner_exc:
                result_queue.put((False, inner_exc))

        worker = threading.Thread(target=_runner, daemon=True)
        worker.start()
        worker.join(timeout=timeout_seconds)

        if worker.is_alive():
            raise TimeoutError(f"LLM call timed out after {timeout_seconds}s")

        ok, payload = result_queue.get_nowait()
        if ok:
            return payload
        raise payload

    errors = []
    for model_name in MODEL_CANDIDATES:
        try:
            if model_name == MODEL_CANDIDATES[0]:
                model = llm
            elif USE_GROQ and ChatGroq is not None:
                model = ChatGroq(
                    model=model_name,
                    groq_api_key=os.getenv("GROQ_API_KEY"),
                    temperature=0.5,
                    max_retries=0,
                    timeout=8,
                )
            else:
                model = ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=os.getenv("GEMINI_API_KEY"),
                    temperature=0.5,
                    max_retries=0,
                    timeout=8,
                )
            return _invoke_with_timeout(model, prompt, timeout_seconds=10)
        except Exception as exc:
            errors.append(f"{model_name}: {exc}")

    combined_error = " | ".join(errors)
    if (
        "404" in combined_error
        or "not found" in combined_error.lower()
        or "api key" in combined_error.lower()
        or "authentication" in combined_error.lower()
        or "unauthorized" in combined_error.lower()
    ):
        LLM_DISABLED = True
    raise RuntimeError("All Gemini model attempts failed | " + combined_error)


def write_outreach_message(profile: Dict, contact_card: Dict) -> str:
    """Generate a personalized WhatsApp-style outreach message from profile and contact data."""
    company_name = _safe_text(profile.get("company_name")) or "your business"
    fallback = (
        f"Hi! We help businesses like {company_name} automate customer communication with AI. "
        "Worth a quick chat?"
    )

    try:
        prompt = f"""
Write a personalized cold outreach message for WhatsApp.

Company Name: {company_name}
What They Do: {_safe_text(profile.get("what_they_do"))}
Size Signals: {_safe_text(profile.get("size_signals"))}
Existing Tools: {_safe_text(profile.get("existing_tools"))}
Contact Phone: {_safe_text(contact_card.get("phone"))}
Contact Email: {_safe_text(contact_card.get("email"))}

Rules:
1) Maximum 5 sentences.
2) Start with outcome, not introduction.
3) Reference something specific about their business.
4) Sound human, not robotic.
5) End with a soft CTA like "Worth a quick chat?" or "Open to a 10-min call?"
6) Do not invent facts. Use only provided business details.
7) Avoid quoting uncertain numbers unless explicitly provided above.

Return only the final message text.
"""
        response = _invoke_gemini(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        if isinstance(raw, list):
            raw = " ".join(str(part) for part in raw)
        message = _safe_text(raw)
        return message or fallback
    except Exception as exc:
        print(f"[outreach_writer] error: {exc}")
        return fallback
