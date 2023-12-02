from __future__ import annotations

from typing import Optional

from ..container import Message


class Strategy:
    async def handle(
        self,
        session_id: str,
        parent_message_id: Optional[str],
        character_id: Optional[str],
    ) -> Message:
        raise NotImplementedError
