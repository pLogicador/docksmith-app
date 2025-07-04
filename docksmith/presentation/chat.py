import streamlit as st
from service.rag import RAGService


def show():
    st.header("💬 Chat with Documents")

    if not st.session_state.collection:
        st.info("Select a collection first in the scraping section")
        return
    st.success(f"📁 Active collection: {st.session_state.collection}")

    if "rag_service" not in st.session_state:
        st.session_state.rag_service = RAGService()

    if "current_collection" not in st.session_state or st.session_state.current_collection != st.session_state.collection:
        with st.spinner("Loading documents..."):
            success = st.session_state.rag_service.load_collection(st.session_state.collection)
            if success:
                st.session_state.current_collection = st.session_state.collection
                st.success("Documents uploaded successfully!")
            else:
                st.error("Error uploading documents")
                return

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
    
    if prompt := st.chat_input("Ask a question about the documents..."):
        st.chat_message("user").write(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = st.session_state.rag_service.ask_question(prompt)
                st.write(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

    if st.button("🗑️ Clear chat"):
        st.session_state.messages = []
        st.rerun()
