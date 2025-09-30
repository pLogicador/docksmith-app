import os
import logging
import traceback
from firecrawl import FirecrawlApp


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class ScrapingService:
    def __init__(self):
        self.api_key = os.getenv("FIRECRAWL_API_KEY")
        self.api_url = os.getenv("FIRECRAWL_API_URL")
        if not self.api_url:
            raise ValueError("FIRECRAWL_API_URL not defined.")
        logging.info(f"ScrapingService initialized with URL: {self.api_url}")

        self.app = FirecrawlApp(api_key=self.api_key, api_url=self.api_url)

    def _crawl(self, url, visited=None):
        """
        Recursively maps all links starting from the given URL.
        Avoids revisiting URLs by tracking visited set.
        """
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

    def scrape_website(self, url, collection_name):
        """
        Performs recursive crawling to find all links, then batch scrapes them.
        Saves the scraped markdown content into the specified collection folder.
        """
        try:
            logging.info(f"Starting recursive crawl on URL: {url}")
            all_links = self._crawl(url)

            if not all_links:
                raise Exception("No links found during crawling.")

            # Deduplicate links
            unique_links = list(set(all_links))
            logging.info(f"Total unique links found: {len(unique_links)}")

            # Batch scrape all links
            logging.info(f"Batch scraping {len(unique_links)} links")
            scrape_result = self.app.batch_scrape_urls(unique_links)

            # Extract scraped data
            if hasattr(scrape_result, 'data'):
                scraped_data = scrape_result.data
            else:
                scraped_data = scrape_result.get("data", []) if hasattr(scrape_result, 'get') else []

            # Prepare collection directory
            collection_path = os.path.join("data", "collections", collection_name)
            os.makedirs(collection_path, exist_ok=True)

            saved_count = 0
            for i, page in enumerate(scraped_data, start=1):
                markdown_content = None
                if hasattr(page, "markdown") and page.markdown:
                    markdown_content = page.markdown
                elif hasattr(page, 'data') and hasattr(page.data, 'markdown'):
                    markdown_content = page.data.markdown
                elif isinstance(page, dict):
                    markdown_content = page.get("markdown")

                if not markdown_content:
                    continue

                filepath = os.path.join(collection_path, f"{i}.md")
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(markdown_content)
                saved_count += 1

            logging.info(f"✅ Scraping completed successfully: {saved_count} files saved")
            return {"success": True, "files": saved_count}

        except Exception as e:
            logging.error(f"❌ Error in scraping: {e}")
            logging.debug(traceback.format_exc())
            return {"success": False, "error": str(e)}
