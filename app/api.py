__author__ = "PRILIVA sahoo"
__copyright__ = "Copyright 2026, PRILIVA sahoo"

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import chromadb
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
from dotenv import load_dotenv
import os
import json
from pathlib import Path

# Load environment variables
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
llm = genai.GenerativeModel('gemini-2.0-flash')

app = FastAPI(title="SHL Conversational Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

chroma_client = chromadb.PersistentClient(path="app/chroma_db")

# --- SCHEMAS ---

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]

class Recommendation(BaseModel):
    name: str
    url: str
    test_type: Optional[str] = "Not specified"

class ChatResponse(BaseModel):
    reply: str
    recommendations: List[Recommendation]
    end_of_conversation: bool

class HealthResponse(BaseModel):
    status: str
    message: Optional[str] = None

# --- ENDPOINTS ---

from fastapi.responses import RedirectResponse

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        collection = chroma_client.get_collection("shl_assessments")
    except ValueError:
        raise HTTPException(status_code=500, detail="Vector DB not initialized")

    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages array cannot be empty")

    history = "\n".join([f"{m.role}: {m.content}" for m in request.messages])

    # STEP 1: Decide Agent Action
    decision_prompt = f"""
You are an expert HR assistant helping a recruiter find the right SHL assessments from the SHL catalog.
You must be conversational, clarifying, and stay strictly in scope.

Based on the conversation history below, decide what to do next.
1. CLARIFY: The user's query is too vague (e.g. "I need an assessment"). Ask them for details like seniority, role, skills, etc.
2. REFUSE: The user asks for general hiring advice, legal advice, or something outside of finding an SHL assessment. Politely refuse.
3. SEARCH: The user has provided enough context, or asked a specific question about assessments, or wants to compare assessments.

Your response MUST be valid JSON with this exact structure:
{{
    "action": "CLARIFY" | "REFUSE" | "SEARCH",
    "reply": "If CLARIFY or REFUSE, write your polite response to the user here. If SEARCH, leave this empty.",
    "search_query": "If action is SEARCH, write a detailed semantic search query here combining the user's requirements. Otherwise empty."
}}

Conversation History:
{history}
"""
    
    try:
        decision_response = llm.generate_content(
            decision_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                response_mime_type="application/json"
            )
        )
        decision = json.loads(decision_response.text)
    except Exception as e:
        print(f"Decision LLM Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to process conversation context")

    action = decision.get("action", "CLARIFY")
    
    if action in ["CLARIFY", "REFUSE"]:
        return ChatResponse(
            reply=decision.get("reply", "Could you provide more details about the role?"),
            recommendations=[],
            end_of_conversation=False
        )

    # STEP 2: Retrieval & Final Response Generation
    search_query = decision.get("search_query", request.messages[-1].content)
    
    results = collection.query(
        query_texts=[search_query],
        n_results=10,
        include=["metadatas", "documents"]
    )

    catalog_context = ""
    for i in range(len(results["ids"][0])):
        meta = results["metadatas"][0][i]
        catalog_context += f"ID: {i}\nName: {meta['name']}\nURL: {meta['url']}\nType: {meta.get('test_type', 'Not specified')}\nDesc: {meta.get('description', '')[:300]}\n---\n"

    final_prompt = f"""
You are an SHL Assessment Recommender Agent.
The user is looking for assessments. 

Conversation History:
{history}

Here is the catalog data retrieved from the database based on the user's needs:
{catalog_context}

Task:
1. Write a helpful 'reply'. 
   - If they asked for a comparison, compare the items using the catalog data. 
   - If they asked for a shortlist, present it briefly.
2. Select the most relevant items from the catalog data to recommend. You can pick between 1 and 10 items.
3. Decide if the conversation is over (end_of_conversation = true). It is true if you are providing the final recommendations and the user's need is fully met.

Your response MUST be valid JSON with this exact structure:
{{
   "reply": "Your response to the user.",
   "recommendation_ids": [0, 2], // The integer IDs of the items to recommend from the catalog data provided above. Empty list if none match.
   "end_of_conversation": true // true if the user's need is fully met and you are providing final recommendations
}}
"""
    
    try:
        final_response = llm.generate_content(
            final_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                response_mime_type="application/json"
            )
        )
        final_data = json.loads(final_response.text)
    except Exception as e:
        print(f"Final LLM Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate recommendations")

    reply = final_data.get("reply", "Here are the assessments I found.")
    rec_ids = final_data.get("recommendation_ids", [])
    end_of_conv = final_data.get("end_of_conversation", True)

    recommendations = []
    for idx in rec_ids:
        # Validate ID exists in results
        if isinstance(idx, int) and 0 <= idx < len(results["ids"][0]):
            meta = results["metadatas"][0][idx]
            recommendations.append(Recommendation(
                name=meta['name'],
                url=meta['url'],
                test_type=meta.get('test_type', 'Not specified')
            ))

    return ChatResponse(
        reply=reply,
        recommendations=recommendations,
        end_of_conversation=end_of_conv
    )