from datetime import datetime, timedelta, timezone
import os
import re
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from jose import JWTError, jwt
from passlib.context import CryptContext

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

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
EXPIRES_DELTA = 15
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/token")


def hash(password) -> str:
    return password_context.hash(password)


async def get_user(token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    try:
        secret_key = storage.get_secret_key()
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        user = await storage.get_user(user_id)
        return user

    except (JWTError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


# TODO make sure that this is only caused by user, and not internal code...
@app.exception_handler(KeyError)
async def key_error_handler(request: Request, exception: KeyError):
    return JSONResponse(
        status_code=400,
        content={"detail": f'Invalid identifier "{exception.args[0]}"'},
    )


@app.get("/")
async def get_root():
    # return RedirectResponse("/static/index.html")
    return FileResponse(os.path.join(STATIC_FOLDER, "index.html"))


@app.post("/api/v1/token")
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user_id = form_data.username
    user_hash = await storage.get_user_hash(user_id)
    if user_hash:
        password = form_data.password
        if password_context.verify(password, user_hash):
            now = datetime.now(timezone.utc)
            expire = now + timedelta(minutes=EXPIRES_DELTA)
            claims = {
                "sub": user_id,
                "exp": expire,
            }
            secret_key = storage.get_secret_key()
            token = jwt.encode(claims, secret_key, ALGORITHM)
            return {
                "access_token": token,
                "token_type": "bearer",
            }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.get("/api/v1/users/me")
async def get_character_list(user: Annotated[User, Depends(get_user)]) -> User:
    return user


# TODO add session authorization


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
