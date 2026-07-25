from tavily import AsyncTavilyClient

from core.config import settings


async def web_search(query: str, max_results: int = 3) -> str:
    client = AsyncTavilyClient(api_key=settings.tavily_api_key)

    try:
        response = await client.search(query, max_results=max_results)
    except Exception as e:
        print(f"Web search failed for '{query}': {e}")
        return f"[search failed for '{query}', no results available]"

    results = response.get("results", [])
    if not results:
        return f"[no search results found for '{query}']"

    formatted = "\n".join(
        f"- {r['title']}: {r['content'][:200]}" for r in results
    )
    return formatted