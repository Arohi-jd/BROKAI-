from typing import Dict, List
import queue
import threading
import time

from duckduckgo_search import DDGS


_SEARCH_LOCK = threading.Lock()
_LAST_SEARCH_TS = 0.0
_MIN_SECONDS_BETWEEN_SEARCHES = 1.1


def web_search(query: str, max_results: int = 5) -> List[Dict]:
    """Run a DuckDuckGo text search and return a list of result dictionaries."""
    try:
        global _LAST_SEARCH_TS

        # Throttle outgoing searches to reduce DuckDuckGo 202 rate-limit responses.
        with _SEARCH_LOCK:
            now = time.time()
            wait_for = _MIN_SECONDS_BETWEEN_SEARCHES - (now - _LAST_SEARCH_TS)
            if wait_for > 0:
                time.sleep(wait_for)
            _LAST_SEARCH_TS = time.time()

        result_queue: queue.Queue = queue.Queue(maxsize=1)

        def _runner() -> None:
            try:
                with DDGS(timeout=8) as ddgs:
                    for backend in ["lite", "html"]:
                        try:
                            results = list(
                                ddgs.text(
                                    query,
                                    max_results=max_results,
                                    region="in-en",
                                    safesearch="off",
                                    backend=backend,
                                )
                            )
                            if results:
                                result_queue.put((True, results))
                                return
                        except Exception as backend_exc:
                            print(f"[web_search] backend={backend} error: {backend_exc}")

                    result_queue.put((True, []))
            except Exception as inner_exc:
                result_queue.put((False, inner_exc))

        worker = threading.Thread(target=_runner, daemon=True)
        worker.start()
        worker.join(timeout=10)

        if worker.is_alive():
            print("[web_search] error: search timed out after 10s")
            return []

        ok, payload = result_queue.get_nowait()
        if ok:
            return payload

        print(f"[web_search] error: {payload}")
        return []
    except Exception as exc:
        print(f"[web_search] error: {exc}")
        return []
