"""
The backend server (FastAPI).

The UI talks to the agent only through these endpoints:
    GET  /health                 - is the server up?
    POST /sessions               - start a new conversation
    GET  /sessions               - list past conversations
    GET  /sessions/{session_id}  - the messages of one conversation
    DELETE /sessions/{session_id} - delete one conversation
    POST /chat                   - send a message, get the agent's answer
    POST /transcribe             - turn a voice recording into text

Conversations are saved in PostgreSQL by ADK (tables: sessions, events).

Run from the project root:
    uvicorn backend.main:app --port 8000
Then open http://localhost:8000/docs to try the endpoints in the browser.
"""

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, UploadFile
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import errors, types
from pydantic import BaseModel

from backend.agent.agent import root_agent
from backend.config import DATABASE_URL
from backend.db.load_data import load_aviation_data
from backend.voice import transcribe

# Errors from Gemini: API errors (quota, overload) and network errors (disconnects).
MODEL_ERRORS = (errors.APIError, httpx.HTTPError)

APP_NAME = "airport_agent"
USER_ID = "analyst"  # one user for now (no login)

# ADK saves every conversation in PostgreSQL.
session_service = DatabaseSessionService(db_url=DATABASE_URL)
runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=session_service)


@asynccontextmanager
async def lifespan(app):
    """Runs once when the server starts."""
    load_aviation_data()  # make sure the aviation tables match data/processed
    yield


app = FastAPI(title="Airport Investment Agent", lifespan=lifespan)


class ChatRequest(BaseModel):
    """What the UI sends to /chat."""
    session_id: str
    message: str


async def find_session(session_id):
    session = await session_service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return session


def text_of(event):
    """The visible text of one event (skips tool calls and the model's hidden thoughts)."""
    if not event.content:
        return ""
    return "".join(part.text for part in event.content.parts if part.text and not part.thought)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/sessions")
async def create_session():
    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID)
    return {"session_id": session.id}


@app.get("/sessions")
async def list_sessions():
    result = await session_service.list_sessions(app_name=APP_NAME, user_id=USER_ID)
    newest_first = sorted(result.sessions, key=lambda s: s.last_update_time, reverse=True)
    # Only conversations that have a question in them (empty ones have no title yet).
    return [
        {"session_id": s.id, "title": s.state["title"]}
        for s in newest_first
        if "title" in s.state
    ]


@app.get("/sessions/{session_id}")
async def get_conversation(session_id: str):
    session = await find_session(session_id)
    messages = [
        {"role": "user" if event.author == "user" else "assistant", "text": text_of(event)}
        for event in session.events
        if text_of(event)
    ]
    return {"session_id": session_id, "messages": messages}


@app.delete("/sessions/{session_id}")
async def delete_conversation(session_id: str):
    await find_session(session_id)  # 404 if it does not exist
    # ADK deletes the conversation and all its messages.
    await session_service.delete_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
    return {"deleted": session_id}


@app.post("/chat")
async def chat(request: ChatRequest):
    session = await find_session(request.session_id)

    message = types.Content(role="user", parts=[types.Part(text=request.message)])
    # The first question becomes the conversation's title (shown in the list).
    new_state = {"title": request.message[:60]} if "title" not in session.state else None

    answer = ""
    tools_used = []
    try:
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=request.session_id,
            new_message=message,
            state_delta=new_state,
        ):
            for part in event.content.parts if event.content else []:
                if part.function_call:
                    tools_used.append({"tool": part.function_call.name, "args": dict(part.function_call.args)})
            if event.is_final_response():
                answer += text_of(event)
    except MODEL_ERRORS as error:
        raise HTTPException(status_code=503, detail=f"The AI model is not available right now: {error}")

    return {"answer": answer, "tools_used": tools_used}


@app.post("/transcribe")
async def transcribe_audio(audio: UploadFile):
    """The UI sends a voice recording; we return the text."""
    audio_bytes = await audio.read()
    try:
        text = await transcribe(audio_bytes, audio.content_type or "audio/wav")
    except MODEL_ERRORS as error:
        raise HTTPException(status_code=503, detail=f"Could not transcribe right now: {error}")
    return {"text": text}
