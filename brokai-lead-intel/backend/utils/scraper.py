import httpx
from bs4 import BeautifulSoup


def scrape_url(url: str) -> str:
    """Fetch a URL and return cleaned plain text content limited to 4000 characters."""
    try:
        if not url:
            return ""

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        response = httpx.get(url, headers=headers, timeout=10, follow_redirects=True)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        for tag_name in ["script", "style", "nav", "footer", "head"]:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        return text[:4000]
    except Exception as exc:
        print(f"[scrape_url] error: {exc}")
        return ""
