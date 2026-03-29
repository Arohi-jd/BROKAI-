from typing import Dict, TypedDict

from langgraph.graph import END, StateGraph

from agents.contact_finder import find_contact_card
from agents.outreach_writer import write_outreach_message
from agents.researcher import build_company_profile


class CompanyState(TypedDict):
    """Shared LangGraph state passed across all three agents."""

    company_name: str
    location: str
    profile: dict
    contact_card: dict
    outreach_message: str
    error: str


def researcher_node(state: CompanyState) -> CompanyState:
    """Run Agent 01 (Researcher) and write the generated profile into state."""
    try:
        profile = build_company_profile(state.get("company_name", ""), state.get("location", "India"))
        return {**state, "profile": profile}
    except Exception as exc:
        fallback_profile = {
            "what_they_do": "Could not determine business details.",
            "size_signals": "No reliable size signals found.",
            "digital_presence": "No reliable online presence data found.",
            "existing_tools": "No tools identified.",
            "website_url": "Not available",
            "company_name": state.get("company_name", "Unknown Company"),
            "location": state.get("location", "India"),
        }
        return {**state, "profile": fallback_profile, "error": f"Researcher error: {exc}"}


def contact_finder_node(state: CompanyState) -> CompanyState:
    """Run Agent 02 (Contact Finder) and write the contact card into state."""
    try:
        contact_card = find_contact_card(state.get("profile", {}))
        return {**state, "contact_card": contact_card}
    except Exception as exc:
        fallback_contact = {
            "phone": "Not found",
            "email": "Not found",
            "whatsapp": "Not found",
            "source_url": "",
        }
        current_error = state.get("error", "")
        merged_error = f"{current_error} | Contact finder error: {exc}" if current_error else f"Contact finder error: {exc}"
        return {**state, "contact_card": fallback_contact, "error": merged_error}


def outreach_writer_node(state: CompanyState) -> CompanyState:
    """Run Agent 03 (Outreach Writer) and write the final message into state."""
    try:
        message = write_outreach_message(state.get("profile", {}), state.get("contact_card", {}))
        return {**state, "outreach_message": message}
    except Exception as exc:
        company_name = state.get("profile", {}).get("company_name", state.get("company_name", "your business"))
        fallback_message = (
            f"Hi! We help businesses like {company_name} automate customer communication with AI. "
            "Worth a quick chat?"
        )
        current_error = state.get("error", "")
        merged_error = f"{current_error} | Outreach writer error: {exc}" if current_error else f"Outreach writer error: {exc}"
        return {**state, "outreach_message": fallback_message, "error": merged_error}


graph = StateGraph(CompanyState)
graph.add_node("researcher", researcher_node)
graph.add_node("contact_finder", contact_finder_node)
graph.add_node("outreach_writer", outreach_writer_node)

graph.set_entry_point("researcher")
graph.add_edge("researcher", "contact_finder")
graph.add_edge("contact_finder", "outreach_writer")
graph.add_edge("outreach_writer", END)

pipeline = graph.compile()


def process_company(company_name: str, location: str) -> Dict:
    """Invoke the LangGraph pipeline for one company and return the final state."""
    initial_state: CompanyState = {
        "company_name": company_name,
        "location": location,
        "profile": {},
        "contact_card": {"phone": "", "email": "", "whatsapp": "", "source_url": ""},
        "outreach_message": "",
        "error": "",
    }
    try:
        result = pipeline.invoke(initial_state)
        return dict(result)
    except Exception as exc:
        fallback_profile = {
            "what_they_do": "Could not determine business details.",
            "size_signals": "No reliable size signals found.",
            "digital_presence": "No reliable online presence data found.",
            "existing_tools": "No tools identified.",
            "website_url": "Not available",
            "company_name": company_name,
            "location": location,
        }
        return {
            "company_name": company_name,
            "location": location,
            "profile": fallback_profile,
            "contact_card": {
                "phone": "Not found",
                "email": "Not found",
                "whatsapp": "Not found",
                "source_url": "",
            },
            "outreach_message": f"Hi! We help businesses like {company_name} automate customer communication with AI. Worth a quick chat?",
            "error": f"Pipeline invocation error: {exc}",
        }
