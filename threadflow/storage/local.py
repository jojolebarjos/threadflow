from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
import secrets
from typing import Optional

import yaml

import rapidfuzz

from ..container import (
    Message,
    Character,
)

from .base import Storage


CHARACTER_PATTERN = r"[a-z][a-z0-9\-]*[a-z0-9]?"


class _Session:
    def __init__(self, folder: str):
        self.folder = folder
        self.config = {}
        self.messages: dict[str, Message] = {}
        self.characters: dict[str, Character] = {}
        self.reload()

    def reload(self):
        config_path = os.path.join(self.folder, "config.yaml")
        with open(config_path, encoding="utf-8") as file:
            self.config = yaml.safe_load(file)

        # TODO need "world" knowledge

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
                properties["public-prompt"],
                properties["private-prompt"],
            )

        message_path = os.path.join(self.folder, "message.jl")
        self.messages = {}
        if os.path.exists(message_path):
            with open(message_path, encoding="utf-8") as file:
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


class LocalStorage(Storage):
    def __init__(self, folder: str):
        self.folder = folder
        self.sessions: dict[str, _Session] = {}
        self.reload()

    def reload(self):
        self.sessions = {}
        for session_id in os.listdir(self.folder):
            session_folder = os.path.join(self.folder, session_id)
            config_path = os.path.join(session_folder, "config.yaml")
            if os.path.exists(config_path):
                session = _Session(session_folder)
                self.sessions[session_id] = session

    async def get_message(self, session_id: str, message_id: str) -> Message:
        session = self.sessions[session_id]
        return session.messages[message_id]

    async def get_messages(self, session_id: str) -> list[Message]:
        session = self.sessions[session_id]
        return list(session.messages.values())

    async def get_message_chain(
        self,
        session_id: str,
        message_id: str,
        max_depth: Optional[int] = None,
    ) -> list[Message]:
        session = self.sessions[session_id]
        messages = []
        while message_id is not None and len(messages) < max_depth:
            message = session.messages[message_id]
            messages.append(message)
            message_id = message.parent_message_id
        messages.reverse()
        return messages

    async def get_character(self, session_id: str, character_id: str) -> Character:
        session = self.sessions[session_id]
        return session.characters[character_id]

    async def get_character_by_name(self, session_id: str, name: str) -> Character:
        # TODO this should probably be the same, regardless of the storage

        session = self.sessions[session_id]

        # Exact match of identifier takes precedence
        character_id = name.lower()
        character = session.characters.get(character_id)
        if character is not None:
            return character

        # Otherwise, use fuzzy matching on display name
        choices, characters = zip(
            *[(character.name, character) for character in session.characters.values()]
        )
        _, score, index = rapidfuzz.process.extractOne(name, choices)
        if score >= 50:
            return characters[index]

        raise KeyError(name)

    async def get_characters(self, session_id: str) -> list[Character]:
        session = self.sessions[session_id]
        return list(session.characters.values())

    async def get_characters_at(
        self,
        session_id: str,
        message_id: str,
    ) -> list[Character]:
        session = self.sessions[session_id]

        messages = []
        while message_id is not None:
            message = session.messages[message_id]
            if message.character_id == "system":
                messages.append(message)
            message_id = message.parent_message_id
        messages.reverse()

        # TODO threads should probably start with no attendees
        character_ids = set(session.characters.keys())

        for message in messages:
            match = re.search(r"\((\w+)\) added", message.content)
            if match:
                character_id = match.group(1)
                character_ids.add(character_id)

            match = re.search(r"\((\w+)\) removed", message.content)
            if match:
                character_id = match.group(1)
                character_ids.remove(character_id)

        return [session.characters[character_id] for character_id in character_ids]

    async def make_message(
        self,
        session_id: str,
        parent_message_id: Optional[str],
        character_id: str,
        content: str,
    ) -> Message:
        session = self.sessions[session_id]

        if parent_message_id is not None and parent_message_id not in session.messages:
            raise KeyError(parent_message_id)

        if character_id != "system" and character_id not in session.characters:
            raise KeyError(character_id)

        # TODO should probably use uuid.uuid4?
        while True:
            message_id = secrets.token_hex(8)
            if message_id not in session.messages:
                break

        timestamp = datetime.now(timezone.utc)

        # TODO write async (don't forget to use lock, for id generation)
        path = os.path.join(session.folder, "message.jl")
        with open(path, "a", encoding="utf-8") as file:
            payload = {
                "message_id": message_id,
                "parent_message_id": parent_message_id,
                "character_id": character_id,
                "timestamp": timestamp.isoformat(),
                "content": content,
            }
            line = json.dumps(payload)
            file.write(f"{line}\n")

        message = Message(
            message_id,
            parent_message_id,
            character_id,
            timestamp,
            content,
        )
        session.messages[message_id] = message

        return message

    async def make_attendance_message(
        self,
        session_id: str,
        parent_message_id: Optional[str],
        *,
        added: Optional[list[str]] = None,
        removed: Optional[list[str]] = None,
    ) -> Message:
        # TODO support multiple changes in attendees in a single operation
        assert added or removed
        assert not (added and removed)

        session = self.sessions[session_id]

        if added:
            assert len(added) == 1
            # TODO check whether it already exists
            character_id = added[0]
            character = session.characters[character_id]
            content = f"**{character.name} ({character_id}) added.**"

        else:
            assert len(removed) == 1
            # TODO check whether it does not exists
            character_id = removed[0]
            character = session.characters[character_id]
            content = f"**{character.name} ({character_id}) removed.**"

        message = await self.make_message(
            session_id,
            parent_message_id,
            "system",
            content,
        )
        return message
