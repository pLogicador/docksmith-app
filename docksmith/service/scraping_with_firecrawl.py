import logging
import traceback
from firecrawl import FirecrawlApp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class ScrapingService:
    def __init__(self, api_key, api_url):
        if not api_url:
            raise ValueError("FIRECRAWL_API_URL not defined.")
        logging.info(f"ScrapingService initialized with URL: {api_url}")

        self.app = FirecrawlApp(api_key=api_key, api_url=api_url)

    def _crawl(self, url, visited=None):
        if visited is None:
            visited = set()

        if url in visited:
            return []

        visited.add(url)

        try:
            result = self.app.map_url(url)
            links = getattr(result, 'links', [])
        except Exception as e:
            logging.warning(f"Failed to map URL {url}: {e}")
            links = []

        all_links = list(links)
        for link in links:
            all_links.extend(self._crawl(link, visited))

        return all_links

    def scrape_website(self, url):
        """Retorna conteúdo markdown em memória (não salva no disco)."""
        try:
            logging.info(f"Starting recursive crawl on URL: {url}")
            all_links = self._crawl(url)

            if not all_links:
                raise Exception("No links found during crawling.")

            unique_links = list(set(all_links))
            logging.info(f"Total unique links found: {len(unique_links)}")

            scrape_result = self.app.batch_scrape_urls(unique_links)

            if hasattr(scrape_result, 'data'):
                scraped_data = scrape_result.data
            else:
                scraped_data = scrape_result.get("data", []) if hasattr(scrape_result, 'get') else []

            markdown_list = []
            for page in scraped_data:
                md = None
                if hasattr(page, "markdown") and page.markdown:
                    md = page.markdown
                elif hasattr(page, "data") and hasattr(page.data, "markdown"):
                    md = page.data.markdown
                elif isinstance(page, dict):
                    md = page.get("markdown")

                if md:
                    markdown_list.append(md)

            logging.info(f"✅ Scraping completed successfully: {len(markdown_list)} items in memory")
            return {"success": True, "data": markdown_list}

        except Exception as e:
            logging.error(f"❌ Error in scraping: {e}")
            logging.debug(traceback.format_exc())
            return {"success": False, "error": str(e)}