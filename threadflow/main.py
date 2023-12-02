import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from .agent import OpenAIAgent
from .container import (
    AgentMessageRequest,
    Message,
    MessageList,
    Character,
    CharacterList,
    UserMessageRequest,
)
from .engine import Engine
from .strategy import PlayStrategy


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_FOLDER = os.path.join(HERE, "..")
STATIC_FOLDER = os.path.join(ROOT_FOLDER, "dist")

agent = OpenAIAgent("gpt-3.5-turbo")
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


@app.get("/api/v1/sessions/{session_id}/characters")
async def get_character_list(session_id: str) -> CharacterList:
    session = engine.sessions[session_id]
    entries = list(session.characters.values())
    return CharacterList(entries)


@app.get("/api/v1/sessions/{session_id}/characters/{character_id}")
async def get_character(session_id: str, character_id: str) -> Character:
    session = engine.sessions[session_id]
    return session.characters[character_id]


@app.get("/api/v1/sessions/{session_id}/messages")
async def get_message_list(session_id: str) -> MessageList:
    session = engine.sessions[session_id]
    entries = list(session.messages.values())
    return MessageList(entries)


@app.get("/api/v1/sessions/{session_id}/messages/{message_id}")
async def get_message(session_id: str, message_id: str) -> Message:
    session = engine.sessions[session_id]
    return session.messages[message_id]


@app.get("/api/v1/sessions/{session_id}/messages/{message_id}/characters")
async def get_characters_at_message(session_id: str, message_id: str) -> CharacterList:
    session = engine.sessions[session_id]
    character_ids = await session.get_active_characters(message_id)
    entries = [session.characters[character_id] for character_id in character_ids]
    return CharacterList(entries)


@app.post("/api/v1/sessions/{session_id}/messages/user")
async def post_user_message(session_id: str, request: UserMessageRequest) -> Message:
    session = engine.sessions[session_id]
    return await session.do_user_message(request)


@app.post("/api/v1/sessions/{session_id}/messages/agent")
async def post_agent_message(session_id: str, request: AgentMessageRequest) -> Message:
    session = engine.sessions[session_id]
    return await session.do_agent_message(request)


app.mount("/", StaticFiles(directory=STATIC_FOLDER), name="static")
