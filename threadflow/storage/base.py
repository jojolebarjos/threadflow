from __future__ import annotations

from typing import Optional

from ..container import (
    Character,
    Message,
    User,
)


class Storage:
    async def authorize(self, user_id: str, password: str) -> Optional[str]:
        raise NotImplementedError

    async def get_user_by_token(self, token: str) -> Optional[User]:
        raise NotImplementedError

    async def is_allowed(self, session_id: str, user_id: str) -> bool:
        raise NotImplementedError

    async def get_message(self, session_id: str, message_id: str) -> Message:
        raise NotImplementedError

    async def get_messages(self, session_id: str) -> list[Message]:
        # TODO should probably remove this, in favor of better enumeration method
        raise NotImplementedError

    async def get_message_chain(
        self,
        session_id: str,
        message_id: str,
        max_depth: Optional[int] = None,
    ) -> list[Message]:
        raise NotImplementedError

    async def get_character(self, session_id: str, character_id: str) -> Character:
        raise NotImplementedError

    async def get_character_by_name(self, session_id: str, name: str) -> Character:
        raise NotImplementedError

    async def get_characters(self, session_id: str) -> list[Character]:
        raise NotImplementedError

    async def get_characters_at(
        self,
        session_id: str,
        message_id: str,
    ) -> list[Character]:
        raise NotImplementedError

    async def make_message(
        self,
        session_id: str,
        parent_message_id: Optional[str],
        character_id: str,
        content: str,
    ) -> Message:
        raise NotImplementedError

    async def make_attendance_message(
        self,
        session_id: str,
        parent_message_id: Optional[str],
        *,
        added: Optional[list[str]] = None,
        removed: Optional[list[str]] = None,
    ) -> Message:
        raise NotImplementedError
