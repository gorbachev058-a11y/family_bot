import logging
import asyncio
from typing import Dict, Any, Optional
from tavily import TavilyClient
from config import (
    TAVILY_API_KEY, TAVILY_MAX_RESULTS,
    USE_PROXY, HTTP_PROXY, HTTPS_PROXY
)

logger = logging.getLogger(__name__)


class TavilySearcher:
    def __init__(self):
        if not TAVILY_API_KEY:
            logger.warning("Tavily API key not configured")
            self.client = None
            return

        proxies = None
        if USE_PROXY and HTTP_PROXY and HTTPS_PROXY and HTTP_PROXY.strip() and HTTPS_PROXY.strip():
            proxies = {
                "http": HTTP_PROXY,
                "https": HTTPS_PROXY
            }
            logger.info(f"Using proxy for Tavily: {HTTP_PROXY}")
        else:
            logger.info("Proxy not used for Tavily")

        try:
            self.client = TavilyClient(
                api_key=TAVILY_API_KEY,
                proxies=proxies
            )
            logger.info("Tavily client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Tavily client: {e}")
            self.client = None

    async def search(self, query: str, max_results: int = None) -> Optional[Dict[str, Any]]:
        if not self.client:
            logger.warning("Tavily client not available")
            return None

        if max_results is None:
            max_results = TAVILY_MAX_RESULTS

        try:
            logger.info(f"Searching Tavily for: {query}")

            # Запускаем синхронный поиск в отдельном потоке с таймаутом
            loop = asyncio.get_event_loop()
            search_task = loop.run_in_executor(
                None,
                lambda: self.client.search(
                    query=query,
                    search_depth="advanced",
                    max_results=max_results,
                    include_answer=True,
                    include_raw_content=False,
                    include_images=False
                )
            )

            # Ждём максимум 30 секунд
            response = await asyncio.wait_for(search_task, timeout=10.0)
            logger.info(f"Tavily found {len(response.get('results', []))} results")

            formatted_results = {
                "query": response.get("query", query),
                "answer": response.get("answer", ""),
                "results": []
            }

            for result in response.get("results", []):
                formatted_results["results"].append({
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "content": result.get("content", ""),
                    "score": result.get("score", 0)
                })

            return formatted_results

        except asyncio.TimeoutError:
            logger.error("Tavily search timeout after 30 seconds")
            return None
        except Exception as e:
            logger.error(f"Tavily search error: {e}")
            return None

    def format_results_for_prompt(self, search_results: Dict[str, Any]) -> str:
        if not search_results or not search_results.get("results"):
            return "По вашему запросу ничего не найдено."

        formatted = []
        if search_results.get("answer"):
            formatted.append(f"Краткий ответ: {search_results['answer']}\n")

        formatted.append("Результаты поиска:")
        for i, result in enumerate(search_results["results"], 1):
            formatted.append(
                f"\n{i}. {result['title']}\n"
                f"   URL: {result['url']}\n"
                f"   Содержание: {result['content'][:300]}..."
            )

        return "\n".join(formatted)