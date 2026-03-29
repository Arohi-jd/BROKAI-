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
        temperature=0.2,
        max_retries=0,
        timeout=8,
    )
else:
    llm = ChatGoogleGenerativeAI(
        model=MODEL_CANDIDATES[0],
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0.2,
        max_retries=0,
        timeout=8,
    )


def _safe_text(value: object) -> str:
    """Convert any value to a trimmed string for prompt-safe usage."""
    return str(value or "").strip()


def _normalize_name(value: str) -> str:
    """Normalize company names for generic cleanup and matching."""
    return re.sub(r"[^a-z0-9]", "", _safe_text(value).lower())


def _json_value_to_text(value: Any) -> str:
    """Convert JSON values (dict/list/scalar) to concise readable text."""
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            key = _safe_text(k)
            val = _safe_text(v)
            if key and val:
                parts.append(f"{key}: {val}")
            elif key:
                parts.append(key)
            elif val:
                parts.append(val)
        return "; ".join(parts)

    if isinstance(value, list):
        return ", ".join(_safe_text(item) for item in value if _safe_text(item))

    return _safe_text(value)


def _extract_url(result: Dict) -> str:
    """Extract a URL from DuckDuckGo result dictionaries."""
    return _safe_text(result.get("href") or result.get("url"))


def _build_snippets_block(results: List[Dict]) -> str:
    """Convert search results into a compact snippet text block."""
    lines = []
    for item in results:
        title = _safe_text(item.get("title"))
        body = _safe_text(item.get("body"))
        url = _extract_url(item)
        if title or body or url:
            lines.append(f"Title: {title}\nSnippet: {body}\nURL: {url}")
    return "\n\n".join(lines)


def _guess_website_url(company_name: str) -> str:
    """Guess a likely website URL from company name when search results are missing."""
    try:
        base = "".join(ch.lower() for ch in company_name if ch.isalnum())
        if not base:
            return ""

        candidates = [
            f"https://www.{base}.com",
            f"https://{base}.com",
            f"https://www.{base}.in",
            f"https://{base}.in",
        ]

        # Helpful fallback for names ending with apostrophe-s.
        base_no_trailing_s = base[:-1] if base.endswith("s") else base
        if base_no_trailing_s and base_no_trailing_s != base:
            candidates.extend(
                [
                    f"https://www.{base_no_trailing_s}.com",
                    f"https://{base_no_trailing_s}.com",
                    f"https://www.{base_no_trailing_s}.in",
                    f"https://{base_no_trailing_s}.in",
                ]
            )

        for candidate in candidates:
            text = scrape_url(candidate)
            if len(text) > 250:
                return candidate
    except Exception as exc:
        print(f"[researcher.guess_website] error: {exc}")

    return ""


def _collect_candidate_urls(*result_groups: List[Dict], max_urls: int = 6) -> List[str]:
    """Collect distinct candidate URLs from search results, preserving order."""
    urls: List[str] = []
    seen = set()

    for group in result_groups:
        for item in group or []:
            url = _extract_url(item)
            if not url or url in seen:
                continue

            # Skip obvious noisy targets.
            lower_url = url.lower()
            if any(blocked in lower_url for blocked in ["linkedin.com", "youtube.com", "facebook.com", "instagram.com"]):
                continue

            urls.append(url)
            seen.add(url)
            if len(urls) >= max_urls:
                return urls

    return urls


def _build_heuristic_profile(
    company_name: str,
    location: str,
    website_url: str,
    scraped_text: str,
    snippets_block: str,
) -> Dict:
    """Build a best-effort profile from non-LLM signals when Gemini is unavailable."""
    combined = " ".join([_safe_text(scraped_text), _safe_text(snippets_block)]).strip()
    combined_lower = combined.lower()

    what_they_do = "Could not determine what this company does."
    if combined:
        what_they_do = combined[:280].strip()

    size_parts = []
    for keyword in ["employees", "employee", "team", "branches", "locations", "founded", "years"]:
        if keyword in combined_lower:
            size_parts.append(keyword)
    size_signals = (
        f"Signals found in public text: {', '.join(sorted(set(size_parts)))}"
        if size_parts
        else "No reliable size signals found."
    )

    digital_parts = []
    if website_url and website_url.lower() != "not available":
        digital_parts.append("Website found")
    for keyword in ["instagram", "facebook", "linkedin", "youtube", "google reviews"]:
        if keyword in combined_lower:
            digital_parts.append(keyword)
    digital_presence = ", ".join(sorted(set(digital_parts))) if digital_parts else "No reliable digital presence data found."

    tool_hits = []
    for keyword in ["crm", "whatsapp", "shopify", "zoho", "salesforce", "hubspot", "quickbooks"]:
        if keyword in combined_lower:
            tool_hits.append(keyword)
    existing_tools = ", ".join(sorted(set(tool_hits))) if tool_hits else "Could not identify existing tools."

    return {
        "what_they_do": what_they_do,
        "size_signals": size_signals,
        "digital_presence": digital_presence,
        "existing_tools": existing_tools,
        "website_url": website_url or "Not available",
        "company_name": company_name,
        "location": location,
    }


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
                    temperature=0.2,
                    max_retries=0,
                    timeout=8,
                )
            else:
                model = ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=os.getenv("GEMINI_API_KEY"),
                    temperature=0.2,
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
    raise RuntimeError("All LLM model attempts failed | " + combined_error)


def build_company_profile(company_name: str, location: str) -> Dict:
    """Research a company and return a structured profile dictionary with fixed keys."""
    website_url = ""
    scraped_text = ""
    snippets_block = ""

    fallback_profile = {
        "what_they_do": "Could not determine what this company does.",
        "size_signals": "No reliable size signals found.",
        "digital_presence": "No reliable digital presence data found.",
        "existing_tools": "Could not identify existing tools.",
        "website_url": "Not available",
        "company_name": company_name,
        "location": location,
    }

    try:
        website_results = web_search(f"{company_name} {location} official website", max_results=5)
        generic_site_results = web_search(f"{company_name} official website", max_results=5)
        context_results = web_search(f"{company_name} {location} reviews services about", max_results=5)
        about_results = web_search(f"{company_name} about services", max_results=5)

        candidate_urls = _collect_candidate_urls(website_results, generic_site_results, context_results, about_results)
        if candidate_urls:
            website_url = candidate_urls[0]
        else:
            website_url = _guess_website_url(company_name)
            if website_url:
                candidate_urls = [website_url]

        # Scrape multiple real-time sources to improve data quality.
        scraped_chunks = []
        for url in candidate_urls[:3]:
            text = scrape_url(url)
            if text:
                scraped_chunks.append(text)

            base = url.rstrip("/")
            for path in ["/about", "/about-us", "/services"]:
                more_text = scrape_url(f"{base}{path}")
                if more_text:
                    scraped_chunks.append(more_text)

        scraped_text = "\n\n".join(scraped_chunks)[:4000]
        snippets_block = _build_snippets_block((website_results or []) + (generic_site_results or []) + (context_results or []) + (about_results or []))

        # If no search or scrape context is available, skip LLM and return fallback immediately.
        if not scraped_text and not snippets_block and not website_url:
            return fallback_profile

        prompt = f"""
You are a business intelligence analyst.

Company Name: {company_name}
Location: {location}
Likely Website URL: {website_url or "Not available"}

Website Text (may be partial):
{scraped_text or "No website text available."}

Search Snippets:
{snippets_block or "No snippets found."}

Return a JSON object with exactly these keys:
- what_they_do
- size_signals
- digital_presence
- existing_tools
- website_url

Return ONLY valid JSON. No extra text, no markdown, no explanation.
"""

        response = _invoke_gemini(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        if isinstance(raw, list):
            raw = " ".join(str(part) for part in raw)

        cleaned = str(raw).replace("```json", "").replace("```", "").strip()
        parsed = json.loads(cleaned)

        profile = {
            "what_they_do": _json_value_to_text(parsed.get("what_they_do")) or fallback_profile["what_they_do"],
            "size_signals": _json_value_to_text(parsed.get("size_signals")) or fallback_profile["size_signals"],
            "digital_presence": _json_value_to_text(parsed.get("digital_presence")) or fallback_profile["digital_presence"],
            "existing_tools": _json_value_to_text(parsed.get("existing_tools")) or fallback_profile["existing_tools"],
            "website_url": _safe_text(parsed.get("website_url")) or website_url or fallback_profile["website_url"],
            "company_name": company_name,
            "location": location,
        }
        return profile
    except Exception as exc:
        print(f"[researcher] error: {exc}")
        heuristic = _build_heuristic_profile(company_name, location, website_url, scraped_text, snippets_block)
        if heuristic.get("what_they_do") == "Could not determine what this company does." and not website_url:
            return fallback_profile
        return heuristic
