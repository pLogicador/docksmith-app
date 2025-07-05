import os, logging, traceback
from firecrawl import FirecrawlApp


# Basic logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

class ScrapingService:
    def __init__(self):
        # Load the environment variables with the Firecrawl API credentials and endpoint
        self.api_key = os.getenv("FIRECRAWL_API_KEY")
        self.api_url = os.getenv("FIRECRAWL_API_URL")
        if not self.api_url:
            raise ValueError("FIRECRAWL_API_URL not defined.")
        logging.info(f"ScrapingService init | url={self.api_url}")

        self.app = FirecrawlApp(api_key=self.api_key, api_url=self.api_url)

    def scrape_website(self, url, collection_name):
        try:
            # 1. Maps the links in the given URL
            logging.info("map_url → %s", url)
            map_result = self.app.map_url(url)

            # 2. Extracts links securely, taking into account different return structures
            if hasattr(map_result, 'links'):
                links = map_result.links
            elif hasattr(map_result, 'data') and hasattr(map_result.data, 'links'):
                links = map_result.data.links
            else:
                links = getattr(map_result, 'links', [])
            if not links:
                raise Exception("No links were found!")

            print(f"Found {len(links)} links")

            # 3. Starts batch scraping of collected URLs
            logging.info("batch_scrape_urls → %d links", len(links))
            scrape_result = self.app.batch_scrape_urls(links)  

            # 4. Try extracting the returned data
            if hasattr(scrape_result, 'data'):
                scraped_data = scrape_result.data
            else:
                scraped_data = scrape_result.get("data", []) if hasattr(scrape_result, 'get') else []

            # 5. Creates the folder to store the files in the collection
            collection_path = f"data/collections/{collection_name}"
            os.makedirs(collection_path, exist_ok=True)

            # 6. Saves the Markdown content of each page
            saved_count = 0
            for i, page in enumerate(scraped_data, 1):
                if hasattr(page, "markdown") and page.markdown:
                    markdown_content = page.markdown
                elif hasattr(page, 'data') and hasattr(page.data, 'markdown'):
                    markdown_content = page.data.markdown
                elif isinstance(page, dict) and page.get("markdown"):
                    markdown_content = page["markdown"]
                else:
                    continue

                with open(f"{collection_path}/{i}.md", "w", encoding="utf-8") as f:
                    f.write(markdown_content)
                saved_count += 1

            logging.info("✅ Scraping completed: %d saved files", saved_count)
            return {"success": True, "files": saved_count}
        except Exception as e:
            logging.error("❌ Error in scraping: %s", e)
            logging.debug(traceback.format_exc())
            return {"success": False, "error": str(e)}

