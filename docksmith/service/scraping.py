import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from markdownify import markdownify as md
import logging
import traceback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

class ScrapingService:
    def __init__(self, max_depth=2, concurrency=10):
        """
        max_depth: profundidade máxima da recursão
        concurrency: número máximo de conexões simultâneas
        """
        self.max_depth = max_depth
        self.semaphore = asyncio.Semaphore(concurrency)
        self.cache = {}  # cache em memória (HTML cru)

    async def _fetch(self, session, url):
        """Faz o fetch assíncrono e armazena no cache"""
        if url in self.cache:
            logging.info(f"♻️ Loaded from cache: {url}")
            return self.cache[url]

        try:
            async with self.semaphore:
                async with session.get(url, timeout=10) as resp:
                    resp.raise_for_status()
                    html = await resp.text()
                    self.cache[url] = html  # armazenamos o HTML cru
                    return html
        except Exception as e:
            logging.warning(f"❌ Failed to fetch {url}: {e}")
            return None

    async def _crawl(self, session, url, visited, depth=0):
        if url in visited or depth > self.max_depth:
            return []

        visited.add(url)
        html = await self._fetch(session, url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")

        base_netloc = urlparse(url).netloc
        links = []

        for a in soup.find_all("a", href=True):
            href = a.get("href")
            if not href:
                continue

            # 🔒 ignora tipos de links inválidos ou pseudo-links
            if href.startswith(("javascript:", "mailto:", "#", ":", "?")):
                continue

            # 🔒 ignora fragmentos ou parâmetros internos
            if "#" in href or "?" in href:
                continue

            full_url = urljoin(url, href)
            parsed = urlparse(full_url)

            # 🔒 só aceita links do mesmo domínio
            if parsed.netloc != base_netloc:
                continue

            links.append(full_url)

        if links:
            logging.info(f"🔗 Found {len(links)} valid links at depth {depth}: {url}")
        else:
            logging.debug(f"⚪ No valid links found on: {url}")

        # faz crawling paralelo para os links internos
        tasks = [self._crawl(session, link, visited, depth + 1) for link in links]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # converte o HTML atual para Markdown
        markdown_content = md(html)
        all_content = [markdown_content]

        for r in results:
            if isinstance(r, list):
                all_content.extend(r)

        return all_content

    async def scrape_website_async(self, url):
        """Crawling assíncrono completo e rápido"""
        try:
            async with aiohttp.ClientSession() as session:
                logging.info(f"🕵️ Starting async crawl on {url}")
                content = await self._crawl(session, url, set())
                if not content:
                    raise Exception("No content found.")
                unique = list(set(content))
                logging.info(f"✅ Done: {len(unique)} pages scraped")
                return {"success": True, "data": unique}
        except Exception as e:
            logging.error(f"❌ Scraping error: {e}")
            logging.debug(traceback.format_exc())
            return {"success": False, "error": str(e)}

    def scrape_website(self, url):
        """Interface síncrona compatível com Streamlit"""
        return asyncio.run(self.scrape_website_async(url))
