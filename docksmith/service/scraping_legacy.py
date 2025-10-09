import logging
import traceback
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from markdownify import markdownify as md

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

class ScrapingService:
    def __init__(self, max_depth=2):
        """
        max_depth: profundidade máxima da recursão para evitar crawling infinito
        """
        self.max_depth = max_depth
        self.cache = {}  # cache só na memória

    def _crawl(self, url, visited=None, depth=0):
        if visited is None:
            visited = set()

        if url in visited or depth > self.max_depth:
            return []

        visited.add(url)

        if url in self.cache:
            logging.info(f"♻️  Loaded from cache: {url}")
            return [self.cache[url]]

        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            content = md(soup.prettify())  # converte HTML para Markdown
        except Exception as e:
            logging.warning(f"❌ Failed to fetch {url}: {e}")
            return []

        # salva no cache em memória
        self.cache[url] = content

        # extrai links internos do mesmo domínio, ignorando javascript:, mailto: e #
        links = [
            urljoin(url, a.get("href"))
            for a in soup.find_all("a", href=True)
            if urlparse(a.get("href")).netloc in ("", urlparse(url).netloc)
            and not a.get("href").startswith(("javascript:", "mailto:", "#"))
        ]

        all_content = [content]
        for link in links:
            all_content.extend(self._crawl(link, visited, depth + 1))

        return all_content

    def scrape_website(self, url):
        """Retorna conteúdo em Markdown em memória (não salva no disco)."""
        try:
            logging.info(f"🕵️  Starting recursive crawl on URL: {url}")
            all_content = self._crawl(url)

            if not all_content:
                raise Exception("No pages found during crawling.")

            unique_content = list(set(all_content))
            logging.info(f"✅ Scraping completed: {len(unique_content)} pages found")

            return {"success": True, "data": unique_content}

        except Exception as e:
            logging.error(f"❌ Error in scraping: {e}")
            logging.debug(traceback.format_exc())
            return {"success": False, "error": str(e)}
