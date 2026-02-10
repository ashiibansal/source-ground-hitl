import streamlit as st
import os
import csv
import datetime
import pandas as pd
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from tavily import TavilyClient

# --- PAGE CONFIGURATION (Must be the first Streamlit command) ---
st.set_page_config(layout="wide", page_title="Agent Verification Lab")

# --- SECURITY SETUP ---
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

if not GROQ_API_KEY or not TAVILY_API_KEY:
    st.error("🚨 API Keys not found! Make sure you have created a .env file.")
    st.stop()

# --- INITIALIZE CLIENTS ---
llm = ChatGroq(temperature=0, model_name="llama-3.3-70b-versatile", groq_api_key=GROQ_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# --- HELPER FUNCTION: SAVE DATA ---
def save_result(topic, claim, url, verdict, mode):
    filename = "experiment_results.csv"
    file_exists = os.path.isfile(filename)
    
    with open(filename, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        # Write header if file is new
        if not file_exists:
            writer.writerow(["Timestamp", "Topic", "AI_Claim", "Source_URL", "Human_Verdict", "Interface_Mode"])
        
        # Write the experiment row
        writer.writerow([datetime.datetime.now(), topic, claim, url, verdict, mode])

# --- UI HEADER ---
st.title("🕵️ Source-Grounded Agent (HITL)")
st.markdown("### Human-in-the-Loop Verification Experiment")
st.markdown("---")

# --- SESSION STATE MANAGEMENT ---
if "step" not in st.session_state: st.session_state.step = "input" 
if "topic" not in st.session_state: st.session_state.topic = ""
if "research_data" not in st.session_state: st.session_state.research_data = None
if "ai_summary" not in st.session_state: st.session_state.ai_summary = ""
if "mode" not in st.session_state: st.session_state.mode = "Blind Mode" # Default

# --- STEP 1: INPUT PHASE ---
if st.session_state.step == "input":
    st.header("Step 1: Define Research Topic")
    
    # 1. Dataset Loader (New Feature)
    col_input, col_load = st.columns([3, 1])
    with col_input:
        topic_input = st.text_input("Enter a topic or load a trap:", value=st.session_state.topic)
    with col_load:
        st.write("") # Spacer
        st.write("")
        if st.button("🎲 Load Trap Question"):
            try:
                df = pd.read_csv("adversarial_dataset.csv")
                random_row = df.sample(1).iloc[0]
                # Handles potentially different column names
                q_col = "Question" if "Question" in df.columns else df.columns[0]
                st.session_state.topic = random_row[q_col]
                st.rerun()
            except FileNotFoundError:
                st.error("CSV not found. Run generate_dataset.py first!")

    # 2. Experiment Mode Toggle (New Feature)
    st.session_state.mode = st.radio(
        "Select Experiment Mode:", 
        ["Blind Mode (Control)", "Source-Grounded (Experimental)"], 
        horizontal=True
    )
    
    if st.button("🚀 Start Agent"):
        if not topic_input:
            st.warning("Please enter a topic.")
        else:
            with st.spinner("Agent is searching the web and generating a claim..."):
                try:
                    # Search
                    search_result = tavily.search(query=topic_input, search_depth="basic", max_results=1)
                    if not search_result.get('results'):
                        st.error("No results found.")
                        st.stop()

                    st.session_state.topic = topic_input
                    st.session_state.research_data = search_result['results'][0]
                    
                    # Summarize
                    source_text = st.session_state.research_data['content']
                    prompt = f"""
                    You are a research assistant. Based ONLY on the text below, extract the key factual claim.
                    Do not add outside knowledge. Limit to 2 sentences.
                    Text: {source_text}
                    """
                    response = llm.invoke(prompt)
                    st.session_state.ai_summary = response.content

                    st.session_state.step = "review"
                    st.rerun()

                except Exception as e:
                    st.error(f"Error: {e}")

# --- STEP 2: VERIFICATION PHASE ---
elif st.session_state.step == "review":
    st.header("Step 2: Verification Loop")
    
    # LOGIC: HIDE OR SHOW SOURCE BASED ON MODE
    if st.session_state.mode == "Blind Mode (Control)":
        # Mode A: Blind (ChatGPT style)
        st.subheader("🤖 AI Generated Claim")
        st.info(st.session_state.ai_summary)
        st.warning("🔒 Source Context is HIDDEN in Control Mode.")
        st.caption("Please verify this claim based on your own knowledge.")
        
    else:
        # Mode B: Source-Grounded (Your Reader Mode)
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("🤖 AI Generated Claim")
            st.info(st.session_state.ai_summary)
            st.caption("The agent extracted this claim automatically.")

        with col2:
            st.subheader("📄 Source Context (Reader Mode)")
            if st.session_state.research_data:
                url = st.session_state.research_data['url']
                st.markdown(f"**Source URL:** [{url}]({url})")
                
                content = st.session_state.research_data['content']
                st.markdown(
                    f"""
                    <div style="border: 1px solid #ddd; border-radius: 8px; padding: 20px; height: 400px; overflow-y: auto; background-color: #f9f9f9; color: #2c3e50; font-family: 'Arial', sans-serif; font-size: 15px; line-height: 1.6;">
                        {content}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
    
    st.markdown("---")
    st.write("### 🔍 Is this claim accurate?")

    c1, c2, c3 = st.columns(3)

    # Approve Button
    if c1.button("✅ Approve (Accurate)"):
        save_result(
            st.session_state.topic, 
            st.session_state.ai_summary, 
            st.session_state.research_data['url'], 
            "Verified Accurate", 
            st.session_state.mode
        )
        st.success("Result Saved!")
        st.session_state.step = "input"
        st.rerun()

    # Reject Button
    if c2.button("❌ Reject (Hallucination)"):
        save_result(
            st.session_state.topic, 
            st.session_state.ai_summary, 
            st.session_state.research_data['url'], 
            "Hallucination Detected", 
            st.session_state.mode
        )
        st.error("Rejection Saved!")
        st.session_state.step = "input"
        st.rerun()

    # Skip Button
    if c3.button("🔄 Skip / Restart"):
        st.session_state.step = "input"
        st.rerun()