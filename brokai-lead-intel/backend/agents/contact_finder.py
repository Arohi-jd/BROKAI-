import json
import os
import queue
import re
import threading
from typing import Any, Dict, List

try:
    from langchain_groq import ChatGroq
except Exception:
    ChatGroq = None

from langchain_google_genai import ChatGoogleGenerativeAI

from utils.scraper import scrape_url
from utils.search import web_search


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
        temperature=0,
        max_retries=0,
        timeout=8,
    )
else:
    llm = ChatGoogleGenerativeAI(
        model=MODEL_CANDIDATES[0],
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0,
        max_retries=0,
        timeout=8,
    )


def _safe_text(value: object) -> str:
    """Convert any input to a clean string representation."""
    return str(value or "").strip()


def _extract_url(result: Dict) -> str:
    """Extract a URL from common DuckDuckGo result keys."""
    return _safe_text(result.get("href") or result.get("url"))


def extract_contacts_with_regex(text: str) -> Dict[str, str]:
    """Extract the first likely phone number and email from plain text using regex."""
    try:
        email_matches = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")
        phone_candidates = re.findall(r"(?<!\d)(?:\+?\d[\d\s\-]{8,16}\d)(?!\d)", text or "")

        valid_phones: List[str] = []
        for candidate in phone_candidates:
            digits_only = re.sub(r"\D", "", candidate)
            if 10 <= len(digits_only) <= 13:
                valid_phones.append(candidate.strip())

        return {
            "phone": valid_phones[0] if valid_phones else "",
            "email": email_matches[0].strip() if email_matches else "",
        }
    except Exception as exc:
        print(f"[contact_finder.regex] error: {exc}")
        return {"phone": "", "email": ""}


def _has_phone_or_email(contact_card: Dict[str, str]) -> bool:
    """Return True if at least one of phone or email has been found."""
    return bool(_safe_text(contact_card.get("phone")) or _safe_text(contact_card.get("email")))


def _finalize_contact_card(contact_card: Dict[str, str]) -> Dict[str, str]:
    """Normalize contact card values so all required keys are always present."""
    final_card = {
        "phone": _safe_text(contact_card.get("phone")),
        "email": _safe_text(contact_card.get("email")),
        "whatsapp": _safe_text(contact_card.get("whatsapp")),
        "source_url": _safe_text(contact_card.get("source_url")),
    }
    final_card["phone"] = final_card["phone"] or "Not found"
    final_card["email"] = final_card["email"] or "Not found"
    final_card["whatsapp"] = final_card["whatsapp"] or "Not found"
    final_card["source_url"] = final_card["source_url"] or ""
    return final_card


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
                    temperature=0,
                    max_retries=0,
                    timeout=8,
                )
            else:
                model = ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=os.getenv("GEMINI_API_KEY"),
                    temperature=0,
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


def find_contact_card(profile: Dict) -> Dict[str, str]:
    """Find company contact details using website scraping, directories, and LLM extraction."""
    contact_card = {"phone": "", "email": "", "whatsapp": "", "source_url": ""}

    try:
        company = _safe_text(profile.get("company_name"))
        location = _safe_text(profile.get("location"))
        website_url = _safe_text(profile.get("website_url"))

        # Strategy 1: scrape common contact pages from company website.
        if website_url and website_url.lower() != "not available":
            base = website_url.rstrip("/")
            for path in ["/contact", "/contact-us", "/about", "/reach-us"]:
                page_url = f"{base}{path}"
                text = scrape_url(page_url)
                if not text:
                    continue
                extracted = extract_contacts_with_regex(text)
                if extracted.get("phone"):
                    contact_card["phone"] = extracted["phone"]
                if extracted.get("email"):
                    contact_card["email"] = extracted["email"]
                if _has_phone_or_email(contact_card):
                    contact_card["source_url"] = page_url
                    return _finalize_contact_card(contact_card)

        # Strategy 2: scrape marketplace/directory pages.
        for query in [
            f"{company} {location} indiamart",
            f"{company} {location} justdial",
        ]:
            results = web_search(query, max_results=5)
            for item in results:
                url = _extract_url(item)
                if not url:
                    continue
                lower_url = url.lower()
                if "indiamart" not in lower_url and "justdial" not in lower_url:
                    continue

                text = scrape_url(url)
                if not text:
                    continue

                extracted = extract_contacts_with_regex(text)
                if extracted.get("phone"):
                    contact_card["phone"] = extracted["phone"]
                if extracted.get("email"):
                    contact_card["email"] = extracted["email"]
                if _has_phone_or_email(contact_card):
                    contact_card["source_url"] = url
                    return _finalize_contact_card(contact_card)

        # Strategy 3: ask Gemini to extract contacts from snippets.
        fallback_results = web_search(
            f"{company} {location} phone number email contact",
            max_results=5,
        )
        snippets = []
        for item in fallback_results:
            title = _safe_text(item.get("title"))
            body = _safe_text(item.get("body"))
            url = _extract_url(item)
            snippets.append(f"Title: {title}\nSnippet: {body}\nURL: {url}")

        if not snippets:
            return _finalize_contact_card(contact_card)

        snippets_text = "\n\n".join(snippets)
        snippet_contacts = extract_contacts_with_regex(snippets_text)
        if snippet_contacts.get("phone"):
            contact_card["phone"] = snippet_contacts["phone"]
        if snippet_contacts.get("email"):
            contact_card["email"] = snippet_contacts["email"]
        if _has_phone_or_email(contact_card):
            for item in fallback_results:
                source_url = _extract_url(item)
                if source_url:
                    contact_card["source_url"] = source_url
                    break
            return _finalize_contact_card(contact_card)

        prompt = f"""
Extract contact details for this company from the snippets below.

Company: {company}
Location: {location}

Snippets:
{snippets_text if snippets else 'No snippets available.'}

Return a JSON object with exactly these keys:
- phone
- email
- whatsapp
- source_url

Use empty string for unknown fields.
Return ONLY valid JSON. No extra text, no markdown, no explanation.
"""

        try:
            response = _invoke_gemini(prompt)
            raw = response.content if hasattr(response, "content") else str(response)
            if isinstance(raw, list):
                raw = " ".join(str(part) for part in raw)
            cleaned = str(raw).replace("```json", "").replace("```", "").strip()
            parsed = json.loads(cleaned)

            contact_card["phone"] = _safe_text(parsed.get("phone"))
            contact_card["email"] = _safe_text(parsed.get("email"))
            contact_card["whatsapp"] = _safe_text(parsed.get("whatsapp"))
            contact_card["source_url"] = _safe_text(parsed.get("source_url"))
        except Exception as exc:
            print(f"[contact_finder.llm] error: {exc}")

        return _finalize_contact_card(contact_card)
    except Exception as exc:
        print(f"[contact_finder] error: {exc}")
        return {
            "phone": "Not found",
            "email": "Not found",
            "whatsapp": "Not found",
            "source_url": "",
        }
