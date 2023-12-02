from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import json
import os
import re
import secrets
import yaml

from fastapi import HTTPException

import rapidfuzz

from .container import (
    AgentMessageRequest,
    Message,
    Character,
    UserMessageRequest,
)

from .strategy import Strategy


CHARACTER_PATTERN = r"[a-z][a-z0-9\-]*[a-z0-9]?"


class Engine:
    def __init__(self, root_folder: str, strategy: Strategy):
        self.root_folder = root_folder
        self.strategy = strategy
        self.sessions = {}

        # TODO allow discovery of sessions during runtime?
        sessions_folder = session_folder = os.path.join(root_folder, "data", "session")
        session_names = os.listdir(sessions_folder)
        for name in session_names:
            session_folder = os.path.join(sessions_folder, name)
            config_path = os.path.join(session_folder, "config.yaml")
            if os.path.exists(config_path):
                session = Session(self, session_folder)
                self.sessions[name] = session


class Session:
    def __init__(self, engine: Engine, session_folder: str):
        self.engine = engine
        self.session_folder = session_folder
        self.config = {}
        self.characters = {}
        self.pre_prompt = ""
        self.post_prompt = ""
        self.public_prompts = {}
        self.private_prompts = {}
        self.messages = {}
        self.reload()

    def reload(self):
        config_path = os.path.join(self.session_folder, "config.yaml")
        with open(config_path, encoding="utf-8") as file:
            self.config = yaml.safe_load(file)

        self.pre_prompt = self.config["pre-prompt"]
        self.post_prompt = self.config["post-prompt"]

        self.characters = {}
        for character_id, properties in self.config["characters"].items():
            if (
                not re.fullmatch(CHARACTER_PATTERN, character_id)
                or character_id == "system"
            ):
                raise RuntimeError(
                    f'"{character_id}" is not a valid character identifier'
                )
            self.characters[character_id] = Character(
                character_id,
                properties["name"],
                properties.get("color", "black"),
            )
            self.public_prompts[character_id] = properties["public-prompt"]
            self.private_prompts[character_id] = properties["private-prompt"]

        # TODO better serialization strategy, with an actual message storage class
        history_path = os.path.join(self.session_folder, "history.jl")
        self.messages = {}
        if os.path.exists(history_path):
            with open(history_path, encoding="utf-8") as file:
                for line in file:
                    payload = json.loads(line)
                    message = Message(
                        payload["message_id"],
                        payload["parent_message_id"],
                        payload["character_id"],
                        datetime.fromisoformat(payload["timestamp"]),
                        payload["content"],
                    )
                    self.messages[message.message_id] = message

    def match_character(self, text) -> Optional[str]:
        # Exact match of identifier takes precedence
        character_id = text.lower()
        if character_id in self.characters:
            return character_id

        # Otherwise, use fuzzy matching on display name
        choices, character_ids = zip(*[(p.name, i) for i, p in self.characters.items()])
        _, score, index = rapidfuzz.process.extractOne(text, choices)
        if score >= 50:
            return character_ids[index]

        return None

    async def generate_unique_identifier(self) -> str:
        # TODO should probably use uuid.uuid4?
        while True:
            identifier = secrets.token_hex(8)
            if identifier not in self.messages:
                return identifier

    async def get_active_characters(self, message_id: str) -> list[str]:
        # TODO refactor where we have these helpers
        messages = await self.engine.strategy.build_messages(
            self,
            message_id,
            include_system=True,
        )

        character_ids = set(self.characters.keys())
        for message in messages:
            if message.character_id == "system":
                match = re.search(r"\((\w+)\) added", message.content)
                if match:
                    character_id = match.group(1)
                    character_ids.add(character_id)

                match = re.search(r"\((\w+)\) removed", message.content)
                if match:
                    character_id = match.group(1)
                    character_ids.remove(character_id)

        return sorted(character_ids)

    async def handle_command(self, request: UserMessageRequest) -> str:
        command = request.content
        assert command.startswith("/")

        match = re.match(r"/(\w*)\s*", command)
        assert match
        name = match.group(1).lower()
        payload = command[match.end() :]

        if name == "add":
            character_id = self.match_character(payload)
            if character_id is None:
                return f'**"{payload}" not found, cannot add.**'
            # TODO check whether it already exists
            return f"**{self.characters[character_id].name} ({character_id}) added.**"

        if name == "remove":
            character_id = self.match_character(payload)
            if character_id is None:
                return f'**"{payload}" not found, cannot add.**'
            # TODO check whether it does not exists
            return f"**{self.characters[character_id].name} ({character_id}) removed.**"

        # TODO handle other commands
        return f"**Command /{name} not found.**"

    async def make_message(
        self,
        parent_message_id: str,
        character_id: str,
        content: str,
    ) -> Message:
        message_id = await self.generate_unique_identifier()
        timestamp = datetime.now(timezone.utc)
        message = Message(
            message_id,
            parent_message_id,
            character_id,
            timestamp,
            content,
        )

        # TODO write async
        history_path = os.path.join(self.session_folder, "history.jl")
        with open(history_path, "a", encoding="utf-8") as file:
            payload = {
                "message_id": message.message_id,
                "parent_message_id": message.parent_message_id,
                "character_id": message.character_id,
                "timestamp": message.timestamp.isoformat(),
                "content": message.content,
            }
            line = json.dumps(payload)
            file.write(f"{line}\n")

        self.messages[message_id] = message
        return message

    async def do_user_message(self, request: UserMessageRequest) -> Message:
        if (
            request.parent_message_id is not None
            and request.parent_message_id not in self.messages
        ):
            raise HTTPException(
                400, f'Parent message "{request.parent_message_id}" not found'
            )
        if (
            request.character_id not in self.characters
            and request.character_id != "system"
        ):
            raise HTTPException(400, f'Character "{request.character_id}" not found')
        is_command = request.content.startswith("/")
        if is_command:
            character_id = "system"
            content = await self.handle_command(request)
        else:
            character_id = request.character_id
            if character_id == "system":
                raise HTTPException(400, 'Cannot add user message as "system"')
            content = request.content
        message = await self.make_message(
            request.parent_message_id,
            character_id,
            content,
        )
        return message

    async def do_agent_message(self, request: AgentMessageRequest) -> Message:
        parent_message_id = request.parent_message_id
        if parent_message_id is not None and parent_message_id not in self.messages:
            raise HTTPException(400, f'Parent message "{parent_message_id}" not found')

        character_id = request.character_id
        if character_id == "system":
            raise HTTPException(400, 'Cannot add agent message as "system"')
        if character_id is not None and character_id not in self.characters:
            raise HTTPException(400, f'Character "{character_id}" not found')

        if character_id is None:
            character_id = await self.engine.strategy.choose_character(
                self,
                parent_message_id,
            )

        content = await self.engine.strategy.handle(
            self, parent_message_id, character_id
        )

        message = await self.make_message(
            parent_message_id,
            character_id,
            content,
        )
        return message
