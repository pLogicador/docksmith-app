import os
import streamlit as st
from service.rag import RAGService
from datetime import datetime

def get_chat_history_as_text():
    lines = []
    for msg in st.session_state.messages:
        role = "Usuário" if msg["role"] == "user" else "Assistente"
        timestamp = msg.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        lines.append(f"[{timestamp}] {role}: {msg['content']}")
        lines.append("")  # linha em branco entre mensagens
    return "\n".join(lines)

def show():
    st.header("💬 Chat com Documentos")

    if "collections" not in st.session_state or not st.session_state.collections:
        st.info("Primeiro faça a extração de um site no modo Scraping para criar uma coleção (armazenada apenas na sessão).")
        return

    if "collection" not in st.session_state or not st.session_state.collection:
        st.info("Select a collection below:")
        for c in st.session_state.collections.keys():
            if st.button(f"Use {c}"):
                st.session_state.collection = c
                st.rerun()
        return

    collection_name = st.session_state.collection
    st.success(f"📁 Coleção ativa: {collection_name}")

    if "rag_service" not in st.session_state:
        st.session_state.rag_service = RAGService()

    if "current_collection" not in st.session_state or st.session_state.current_collection != collection_name:
        st.info("⚠️ Carregando documentos na memória. Isso pode levar alguns segundos/minutos, dependendo do tamanho da coleção.")
        with st.spinner("Carregando documentos..."):
            groq_key = os.getenv("GROQ_API_KEY")
            docs = st.session_state.collections[collection_name]
            success = st.session_state.rag_service.load_collection(docs, groq_key)
            if success:
                st.session_state.current_collection = collection_name
                st.success("Documentos carregados com sucesso!")
            else:
                st.error("Erro ao carregar documentos")
                return

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    if prompt := st.chat_input("Faça uma pergunta sobre os documentos..."):
        st.chat_message("user").write(prompt)
        st.session_state.messages.append({
            "role": "user",
            "content": prompt,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        with st.chat_message("assistant"):
            with st.spinner("Pensando..."):
                response = st.session_state.rag_service.ask_question(prompt)
                st.write(response)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

    # Botão de download do histórico
    if st.session_state.messages:
        chat_text = get_chat_history_as_text()
        st.download_button(
            label="💾 Baixar histórico",
            data=chat_text,
            file_name=f"chat_history_{collection_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain"
        )

    if st.button("🗑️ Limpar chat"):
        st.session_state.messages = []
        st.rerun()