import os
import requests
import streamlit as st
from dotenv import load_dotenv
from presentation import scraping
from presentation import chat

load_dotenv()

# Configuração da página
st.set_page_config(page_title="Docksmith", page_icon="📃", layout="wide")

# ==================== FUNÇÕES DE LOGIN/TOKEN ====================
API_BASE = os.getenv("API_BASE")

def get_token_from_query():
    """Pega token da query string, ex: ?token=xxxx"""
    params = st.query_params or {}
    token_val = params.get("token")
    if token_val is None:
        return None
    if isinstance(token_val, list):
        token_val = token_val[0] if token_val else None
    if token_val:
        token_val = str(token_val).strip()
        if token_val.lower().startswith("bearer "):
            token_val = token_val.split(" ", 1)[1]
    return token_val

def validate_token_with_api(token: str):
    """Chama API para validar token; retorna json com info do usuário se válido"""
    if not token:
        return None
    try:
        resp = requests.post(
            f"{API_BASE}/validate-agendador-token",
            json={"token": token},
            timeout=5
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            return None
    except requests.RequestException:
        return None

# ==================== VERIFICAÇÃO DE TOKEN ====================
token = get_token_from_query()
if API_BASE:  # só valida se tiver configurado API_BASE
    if not token:
        st.warning("Você precisa logar no www.syncron.pro.")
        st.stop()
    user_info = validate_token_with_api(token)
    if not user_info:
        st.error("⚠️ Token inválido ou expirado. Faça login novamente.")
        st.stop()
    user_email = user_info.get("user", {}).get("email", "Usuário")
    st.sidebar.success(f"Usuário: {user_email}")

# ==================== TÍTULO ====================
st.title("📃 Docksmith")
st.markdown(
    "<h4 style='color:gray; font-weight: normal; margin-top: -10px;'>Extração de Conhecimento, do Jeito Inteligente </h4>",
    unsafe_allow_html=True
)

# ==================== SIDEBAR ====================
with st.sidebar:
    st.header("📂 Coleções")
    mode = st.radio("Modo:", ["Chat", "Scraping"])
    st.divider()
    st.subheader("Coleções disponíveis (somente na sessão)")

    # CSS para o expander de ajuda
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

    # Inicializa o dicionário em memória
    if "collections" not in st.session_state:
        st.session_state.collections = {}

    # Lista as coleções disponíveis na sessão
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

# ==================== ESTADO INICIAL DO CHAT ====================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "collection" not in st.session_state:
    st.session_state.collection = None

# ==================== RENDERIZAÇÃO DO MODO ====================
if mode == "Scraping":
    scraping.show()
else:
    chat.show()
