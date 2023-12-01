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
    Persona,
    UserMessageRequest,
)

from .strategy import Strategy


PERSONA_PATTERN = r"[a-z][a-z0-9\-]*[a-z0-9]?"


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
        self.personas = {}
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

        self.personas = {}
        for persona_id, properties in self.config["personas"].items():
            if not re.fullmatch(PERSONA_PATTERN, persona_id) or persona_id == "system":
                raise RuntimeError(f'"{persona_id}" is not a valid persona identifier')
            self.personas[persona_id] = Persona(
                persona_id,
                properties["name"],
                properties.get("color", "black"),
            )
            self.public_prompts[persona_id] = properties["public-prompt"]
            self.private_prompts[persona_id] = properties["private-prompt"]

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
                        payload["persona_id"],
                        datetime.fromisoformat(payload["timestamp"]),
                        payload["content"],
                    )
                    self.messages[message.message_id] = message

    def match_persona(self, text) -> Optional[str]:
        # Exact match of identifier takes precedence
        persona_id = text.lower()
        if persona_id in self.personas:
            return persona_id

        # Otherwise, use fuzzy matching on display name
        choices, persona_ids = zip(*[(p.name, i) for i, p in self.personas.items()])
        _, score, index = rapidfuzz.process.extractOne(text, choices)
        if score >= 50:
            return persona_ids[index]

        return None

    async def generate_unique_identifier(self) -> str:
        # TODO should probably use uuid.uuid4?
        while True:
            identifier = secrets.token_hex(8)
            if identifier not in self.messages:
                return identifier

    async def get_active_personas(self, message_id: str) -> list[str]:
        # TODO refactor where we have these helpers
        messages = await self.engine.strategy.build_messages(
            self,
            message_id,
            include_system=True,
        )

        persona_ids = set(self.personas.keys())
        for message in messages:
            if message.persona_id == "system":
                match = re.search(r"\((\w+)\) added", message.content)
                if match:
                    persona_id = match.group(1)
                    persona_ids.add(persona_id)

                match = re.search(r"\((\w+)\) removed", message.content)
                if match:
                    persona_id = match.group(1)
                    persona_ids.remove(persona_id)

        return sorted(persona_ids)

    async def handle_command(self, request: UserMessageRequest) -> str:
        command = request.content
        assert command.startswith("/")

        match = re.match(r"/(\w*)\s*", command)
        assert match
        name = match.group(1).lower()
        payload = command[match.end() :]

        if name == "add":
            persona_id = self.match_persona(payload)
            if persona_id is None:
                return f'**"{payload}" not found, cannot add.**'
            # TODO check whether it already exists
            return f"**{self.personas[persona_id].name} ({persona_id}) added.**"

        if name == "remove":
            persona_id = self.match_persona(payload)
            if persona_id is None:
                return f'**"{payload}" not found, cannot add.**'
            # TODO check whether it does not exists
            return f"**{self.personas[persona_id].name} ({persona_id}) removed.**"

        # TODO handle other commands
        return f"**Command /{name} not found.**"

    async def make_message(
        self,
        parent_message_id: str,
        persona_id: str,
        content: str,
    ) -> Message:
        message_id = await self.generate_unique_identifier()
        timestamp = datetime.now(timezone.utc)
        message = Message(
            message_id,
            parent_message_id,
            persona_id,
            timestamp,
            content,
        )

        # TODO write async
        history_path = os.path.join(self.session_folder, "history.jl")
        with open(history_path, "a", encoding="utf-8") as file:
            payload = {
                "message_id": message.message_id,
                "parent_message_id": message.parent_message_id,
                "persona_id": message.persona_id,
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
        if request.persona_id not in self.personas and request.persona_id != "system":
            raise HTTPException(400, f'Persona "{request.persona_id}" not found')
        is_command = request.content.startswith("/")
        if is_command:
            persona_id = "system"
            content = await self.handle_command(request)
        else:
            persona_id = request.persona_id
            if persona_id == "system":
                raise HTTPException(400, 'Cannot add user message as "system"')
            content = request.content
        message = await self.make_message(
            request.parent_message_id,
            persona_id,
            content,
        )
        return message

    async def do_agent_message(self, request: AgentMessageRequest) -> Message:
        parent_message_id = request.parent_message_id
        if parent_message_id is not None and parent_message_id not in self.messages:
            raise HTTPException(400, f'Parent message "{parent_message_id}" not found')

        persona_id = request.persona_id
        if persona_id == "system":
            raise HTTPException(400, 'Cannot add agent message as "system"')
        if persona_id is not None and persona_id not in self.personas:
            raise HTTPException(400, f'Persona "{persona_id}" not found')

        if persona_id is None:
            persona_id = await self.engine.strategy.choose_persona(
                self,
                parent_message_id,
            )

        content = await self.engine.strategy.handle(self, parent_message_id, persona_id)

        message = await self.make_message(
            parent_message_id,
            persona_id,
            content,
        )
        return message
