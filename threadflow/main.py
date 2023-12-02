import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from .agent import Agent
from .container import (
    AgentMessageRequest,
    Message,
    MessageList,
    Persona,
    PersonaList,
    UserMessageRequest,
)
from .engine import Engine
from .strategy import PlayStrategy


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_FOLDER = os.path.join(HERE, "..")
STATIC_FOLDER = os.path.join(ROOT_FOLDER, "dist")

agent = Agent("gpt-3.5-turbo")
strategy = PlayStrategy(agent)
engine = Engine(ROOT_FOLDER, strategy)

app = FastAPI()

# TODO better fix for CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def get_root():
    # return RedirectResponse("/static/index.html")
    return FileResponse(os.path.join(STATIC_FOLDER, "index.html"))


# TODO proper status codes for bad requests


@app.get("/api/v1/sessions/{session_id}/personas")
async def get_persona_list(session_id: str) -> PersonaList:
    session = engine.sessions[session_id]
    entries = list(session.personas.values())
    return PersonaList(entries)


@app.get("/api/v1/sessions/{session_id}/personas/{persona_id}")
async def get_persona(session_id: str, persona_id: str) -> Persona:
    session = engine.sessions[session_id]
    return session.personas[persona_id]


@app.get("/api/v1/sessions/{session_id}/messages")
async def get_message_list(session_id: str) -> MessageList:
    session = engine.sessions[session_id]
    entries = list(session.messages.values())
    return MessageList(entries)


@app.get("/api/v1/sessions/{session_id}/messages/{message_id}")
async def get_message(session_id: str, message_id: str) -> Message:
    session = engine.sessions[session_id]
    return session.messages[message_id]


@app.get("/api/v1/sessions/{session_id}/messages/{message_id}/personas")
async def get_personas_at_message(session_id: str, message_id: str) -> PersonaList:
    session = engine.sessions[session_id]
    persona_ids = await session.get_active_personas(message_id)
    entries = [session.personas[persona_id] for persona_id in persona_ids]
    return PersonaList(entries)


@app.post("/api/v1/sessions/{session_id}/messages/user")
async def post_user_message(session_id: str, request: UserMessageRequest) -> Message:
    session = engine.sessions[session_id]
    return await session.do_user_message(request)


@app.post("/api/v1/sessions/{session_id}/messages/agent")
async def post_agent_message(session_id: str, request: AgentMessageRequest) -> Message:
    session = engine.sessions[session_id]
    return await session.do_agent_message(request)


app.mount("/", StaticFiles(directory=STATIC_FOLDER), name="static")
