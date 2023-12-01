from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic.dataclasses import dataclass


@dataclass
class Persona:
    persona_id: str
    name: str
    color: str


@dataclass
class PersonaList:
    entries: list[Persona]


@dataclass
class Message:
    message_id: str
    parent_message_id: Optional[str]
    persona_id: str
    timestamp: datetime
    content: str


@dataclass
class MessageList:
    entries: list[Message]


@dataclass
class UserMessageRequest:
    parent_message_id: Optional[str]
    persona_id: str
    content: str


@dataclass
class AgentMessageRequest:
    parent_message_id: Optional[str]
    persona_id: Optional[str]
