import os
import streamlit as st
from service.scraping import ScrapingService

def show():
    st.header("📥 Extrair da web")

    api_key = os.getenv("FIRECRAWL_API_KEY")
    api_url = os.getenv("FIRECRAWL_API_URL")

    #scraper = ScrapingService(api_key, api_url)
    scraper = ScrapingService(max_depth=1, concurrency=5)

    st.warning(
    """
    ⚠️ Observações importantes:
    - O conteúdo extraído fica **apenas na memória da sessão**.
    - Sites grandes podem demorar para extrair.
    - Após reiniciar o servidor ou atualizar a página, a coleção será perdida.
    """
)

    with st.form('scraping_form'):
        url = st.text_input("Endereço do site para extrair informações:", placeholder="https://example.com")
        collection_name = st.text_input("Nome da coleção de informações (apenas na memória):", placeholder="minha-colecao")
        submitted = st.form_submit_button("Iniciar extração")

        if submitted and url and collection_name:
            with st.spinner("Extraindo conteúdo..."):
                result = scraper.scrape_website(url)
                if result["success"]:
                    if "collections" not in st.session_state:
                        st.session_state.collections = {}
                    st.session_state.collections[collection_name] = result["data"]
                    st.success(f"✅ Concluído! {len(result['data'])} documentos armazenados na memória da sessão.")
                else:
                    st.error(f"❌ Error: {result['error']}")