import os
import streamlit as st
from service.scraping import ScrapingService

def show():
    st.header("📥 Web Scraping")

    scraper = ScrapingService()

    with st.form('scraping_form'):
        url = st.text_input("Site URL:", placeholder="https://example.com")
        collection_name = st.text_input("Collection name:", placeholder="my-collection")
        submitted = st.form_submit_button("Start Scraping")

        if submitted and url and collection_name:
            # For the user to understand that there is an operations in background and that it must wait
            with st.spinner("Extracting content..."):
                result = scraper.scrape_website(url, collection_name)
                if result["success"]:
                    st.success(f"✅ Done! {result['files']} saved files.")
                else:
                    st.error(f"❌ Error: {result['error']}")

