import os
import streamlit as st
from dotenv import load_dotenv


load_dotenv()


st.set_page_config(page_title="Docksmith", page_icon="📃", layout="wide")
st.title("📃 Docksmith - Knowledge Extraction, the Smart Way")

with st.sidebar:
    st.header("Collections")
    mode = st.radio("Mode:", ["Chat", "Scraping"])
    st.divider()
    st.subheader("Collections available")
    
    collections_dir = "data/collections"
    if os.path.exists(collections_dir):
        collections = [
            d for d in os.listdir(collections_dir)
            if os.path.isdir(os.path.join(collections_dir, d))
        ]

        for collection in collections:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"📁 {collection}")
            with col2:
                if st.button("Use", key=f"use_{collection}"):
                    st.session_state.collection = collection
                    st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "collection" not in st.session_state:
    st.session_state.collection = None

if mode == "Scraping":
    st.write('Scraping Page')
else:
    st.write('Chat Page')    

