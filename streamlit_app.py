__author__ = "PRILIVA sahoo"
__copyright__ = "Copyright 2026, PRILIVA sahoo"

import streamlit as st
import requests
import os

# Config
st.set_page_config(
    page_title="SHL Conversational Agent",
    layout="wide",
    page_icon="💬"
)

# Custom CSS
st.markdown("""
<style>
    .assessment-card {
        background: #1e2a2a;
        padding: 1rem;
        border-radius: 8px;
        margin-top: 0.5rem;
        border-left: 4px solid #4CAF50;
    }
</style>
""", unsafe_allow_html=True)

st.title("💬 SHL Assessment Recommender Agent")
st.caption("Chat with our AI to find the perfect SHL assessment for your hiring needs.")

with st.sidebar:
    st.header("⚙️ Configuration")
    api_url = st.text_input(
        "API Endpoint",
        value=os.getenv("API_URL", "http://localhost:8000/chat"),
    )
    if st.button("Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
        
    st.markdown("---")
    st.markdown("### How to use:")
    st.markdown("""
    1. Start by describing the role you are hiring for.
    2. Answer any clarifying questions the agent asks.
    3. Ask to compare assessments if you are unsure.
    """)

# Initialize chat history
if "messages" not in st.session_state or not st.session_state.messages:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hello! I am the SHL Assessment Recommender. What kind of role are you hiring for today?"}
    ]

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        
        # Display recommendations if they exist in this turn
        if "recommendations" in message and message["recommendations"]:
            for rec in message["recommendations"]:
                st.markdown(f"""
                <div class="assessment-card">
                    <strong>{rec['name']}</strong><br>
                    <small>Type: {rec.get('test_type', 'Not specified')}</small><br>
                    <a href="{rec['url']}" target="_blank">🔗 View in Catalog</a>
                </div>
                """, unsafe_allow_html=True)

# Accept user input
if prompt := st.chat_input("E.g., I'm looking for an assessment for a mid-level Java developer."):
    
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message in chat message container
    with st.chat_message("user"):
        st.markdown(prompt)

    # Format history for API (only role and content)
    api_messages = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = requests.post(
                    api_url,
                    json={"messages": api_messages},
                    timeout=120
                )
                
                if response.status_code == 200:
                    data = response.json()
                    reply = data.get("reply", "I'm not sure how to respond.")
                    recommendations = data.get("recommendations", [])
                    end_of_conversation = data.get("end_of_conversation", False)
                    
                    # Display the reply
                    st.markdown(reply)
                    
                    # Display recommendations
                    if recommendations:
                        for rec in recommendations:
                            st.markdown(f"""
                            <div class="assessment-card">
                                <strong>{rec['name']}</strong><br>
                                <small>Type: {rec.get('test_type', 'Not specified')}</small><br>
                                <a href="{rec['url']}" target="_blank">🔗 View in Catalog</a>
                            </div>
                            """, unsafe_allow_html=True)
                            
                    if end_of_conversation:
                        st.info("✅ The agent considers this task complete. You can clear the chat to start over or ask follow-up questions.")
                    
                    # Add to session state
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": reply,
                        "recommendations": recommendations,
                        "end_of_conversation": end_of_conversation
                    })
                    
                else:
                    st.error(f"API Error: {response.status_code} - {response.text}")
            except Exception as e:
                st.error(f"Failed to connect to API: {e}")