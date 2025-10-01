import os
import streamlit as st
from dotenv import load_dotenv
from presentation import scraping
from presentation import chat

load_dotenv()

st.set_page_config(page_title="Docksmith", page_icon="📃", layout="wide")
st.title("📃 Docksmith")

# Subtítulo discreto
st.markdown(
    "<h4 style='color:gray; font-weight: normal; margin-top: -10px;'>Transforme documentos em conhecimento prático</h4>",
    unsafe_allow_html=True
)

with st.sidebar:
    st.header("📂 Coleções")
    mode = st.radio("Modo:", ["Chat", "Scraping"])
    st.divider()
    st.subheader("Coleções disponíveis (somente na sessão)")

    


    # CSS para deixar o expander no canto superior direito
    st.markdown(
        """
        <style>
        .help-expander {
            position: fixed;
            top: 20px;
            right: 20px;
            width: 350px;
            z-index: 100;
        }
        </style>
        """, unsafe_allow_html=True
    )

    with st.container():
        with st.expander("ℹ️ Ajuda Docksmith", expanded=False):
            st.markdown("""
            **Como usar o Docksmith:**
            - Modo Scraping(Extração): informe o site e o nome da coleção, clique em "Iniciar extração".
            - As coleções ficam disponíveis **somente na sessão**.
            - Modo Chat: selecione a coleção e faça perguntas sobre os documentos extraídos.

            **Limitações:**
            - Sites grandes podem demorar.
            - Há limites de requisições dependendo da API usada.
            - Estamos trabalhando para melhorar velocidade e salvar coleções em nuvem.
            """)


    # inicializa o dicionário em memória
    if "collections" not in st.session_state:
        st.session_state.collections = {}

    # lista as coleções que estão apenas na sessão
    if st.session_state.collections:
        for collection in st.session_state.collections.keys():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"📁 {collection}")
            with col2:
                if st.button("Usar", key=f"use_{collection}"):
                    st.session_state.collection = collection
                    st.rerun()
    else:
        st.info("Nenhuma coleção disponível ainda. Faça uma extração primeiro.")

# estado inicial do chat
if "messages" not in st.session_state:
    st.session_state.messages = []
if "collection" not in st.session_state:
    st.session_state.collection = None

# renderiza o modo
if mode == "Scraping":
    scraping.show()
else:
    chat.show()
