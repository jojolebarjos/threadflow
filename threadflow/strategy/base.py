from __future__ import annotations

from typing import Optional

from ..container import AgentMessageRequest, Message


class Strategy:
    async def handle(
        self,
        session,
        parent_message_id: Optional[str],
        persona_id: str,
    ) -> str:
        raise NotImplementedError

    async def build_messages(
        self,
        session,
        message_id: str,
        *,
        include_system: bool = False,
    ) -> list[Message]:
        # TODO add recursion limit
        messages = []
        while message_id is not None:
            message = session.messages[message_id]
            if include_system or message.persona_id != "system":
                messages.append(message)
            message_id = message.parent_message_id

        messages.reverse()

        return messages

    async def choose_persona(self, session, message_id: str) -> str:
        raise NotImplementedError
