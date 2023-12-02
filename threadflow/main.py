import os
import re
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from .agent import OpenAIAgent
from .container import (
    AgentMessageRequest,
    Message,
    MessageList,
    Character,
    CharacterList,
    User,
    UserMessageRequest,
)
from .storage import LocalStorage
from .strategy import PlayStrategy


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_FOLDER = os.path.join(HERE, "..")
STORAGE_FOLDER = os.path.join(ROOT_FOLDER, "data", "session")
STATIC_FOLDER = os.path.join(ROOT_FOLDER, "dist")

storage = LocalStorage(STORAGE_FOLDER)
agent = OpenAIAgent("gpt-3.5-turbo")
strategy = PlayStrategy(storage, agent)

app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/token")


async def get_user(token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    user = await storage.get_user_by_token(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# TODO make sure that this is only caused by user, and not internal code...
@app.exception_handler(KeyError)
async def unicorn_exception_handler(request: Request, exception: KeyError):
    return JSONResponse(
        status_code=400,
        content={"detail": f'Invalid identifier "{exception.args[0]}"'},
    )


@app.get("/")
async def get_root():
    # return RedirectResponse("/static/index.html")
    return FileResponse(os.path.join(STATIC_FOLDER, "index.html"))


@app.post("/api/v1/token")
async def post_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    # TODO should we use the OAuth2 scopes?
    token = await storage.authorize(form_data.username, form_data.password)
    if token is None:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    return {"access_token": token, "token_type": "bearer"}


@app.get("/api/v1/users/me")
async def get_character_list(user: Annotated[User, Depends(get_user)]) -> User:
    return user


@app.get("/api/v1/sessions/{session_id}/characters")
async def get_character_list(session_id: str) -> CharacterList:
    entries = await storage.get_characters(session_id)
    return CharacterList(entries)


@app.get("/api/v1/sessions/{session_id}/characters/{character_id}")
async def get_character(session_id: str, character_id: str) -> Character:
    character = await storage.get_character(session_id, character_id)
    return character


@app.get("/api/v1/sessions/{session_id}/messages")
async def get_message_list(session_id: str) -> MessageList:
    entries = await storage.get_messages(session_id)
    return MessageList(entries)


@app.get("/api/v1/sessions/{session_id}/messages/{message_id}")
async def get_message(session_id: str, message_id: str) -> Message:
    message = await storage.get_message(session_id, message_id)
    return message


@app.get("/api/v1/sessions/{session_id}/messages/{message_id}/characters")
async def get_characters_at_message(session_id: str, message_id: str) -> CharacterList:
    entries = await storage.get_characters_at(session_id, message_id)
    return CharacterList(entries)


async def handle_command(session_id: str, request: UserMessageRequest) -> Message:
    command = request.content
    assert command.startswith("/")

    match = re.match(r"/(\w*)\s*", command)
    assert match
    name = match.group(1).lower()
    payload = command[match.end() :]

    # TODO better command dispatcher
    # TODO better argument parser, support multiple names for /add and /remove

    if name == "add":
        character = await storage.get_character_by_name(session_id, payload)
        message = await storage.make_attendance_message(
            session_id,
            request.parent_message_id,
            added=[character.character_id],
        )
        return message

    if name == "remove":
        character = await storage.get_character_by_name(session_id, payload)
        message = await storage.make_attendance_message(
            session_id,
            request.parent_message_id,
            removed=[character.character_id],
        )
        return message

    raise KeyError(name)


@app.post("/api/v1/sessions/{session_id}/messages/user")
async def post_user_message(session_id: str, request: UserMessageRequest) -> Message:
    is_command = request.content.startswith("/")
    if is_command:
        return await handle_command(session_id, request)

    message = await storage.make_message(
        session_id,
        request.parent_message_id,
        request.character_id,
        request.content,
    )
    return message


@app.post("/api/v1/sessions/{session_id}/messages/agent")
async def post_agent_message(session_id: str, request: AgentMessageRequest) -> Message:
    message = await strategy.handle(
        session_id,
        request.parent_message_id,
        request.character_id,
    )
    return message


app.mount("/", StaticFiles(directory=STATIC_FOLDER), name="static")
