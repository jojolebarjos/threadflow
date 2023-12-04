import inspect
import random
import re
from typing import Optional

from ..agent import Agent
from ..container import Message
from ..storage import Storage

from .base import Strategy


class PlayStrategy(Strategy):
    def __init__(self, storage: Storage, agent: Agent):
        self.storage = storage
        self.agent = agent

    async def handle(
        self,
        session_id: str,
        parent_message_id: Optional[str],
        character_id: Optional[str],
    ) -> Message:
        # TODO can we get that as a single call?
        messages = await self.storage.get_message_chain(session_id, parent_message_id)
        characters = await self.storage.get_characters_at(session_id, parent_message_id)

        character_map = {character.character_id: character for character in characters}

        if character_id is None:
            target_character = random.choice(characters)
        else:
            target_character = character_map[character_id]

        system_content = clean(
            """
            You are an expert writer, helping the user write the scenario for a play.
            Your style expresses the personality of the character speaking.
            """
        )

        parts = []
        for character in characters:
            if character is target_character:
                prompt = character.public_prompt + " " + character.private_prompt
            else:
                prompt = character.public_prompt
            part = f" - {character.name}: {prompt}"
            parts.append(part)
        characters_prompt = "\n".join(parts)

        parts = []
        for message in messages:
            if message.character_id != "system":
                name = characters[message.character_id].name.upper()
                content = message.content.strip()
                part = f"{name}:\n{content}"
                parts.append(part)
        script_prompt = "\n\n".join(parts)

        if not script_prompt:
            user_content = clean(
                """

                ## CHARACTERS

                {characters}

                ## TASK

                Given the context, the characters that are in the scene, what does
                {name} says to start the conversation? Only reply what is said by the
                character, nothing more.

                """
            ).format(
                characters=characters_prompt,
                name=target_character.name,
            )

        else:
            user_content = clean(
                """

                ## CHARACTERS

                {characters}

                ## SCRIPT

                {script}

                ## TASK

                Given the context, the characters that are in the scene, and the
                current script, what does {name} say next? Only reply what is said by
                the character, nothing more.

                """
            ).format(
                characters=characters_prompt,
                script=script_prompt,
                name=target_character.name,
            )

        prompt = [
            {
                "role": "system",
                "content": system_content,
            },
            {
                "role": "user",
                "content": user_content,
            },
        ]
        print(repr(prompt))

        content = await self.agent.do_completion(prompt)
        # TODO use stop to avoid multi answers by agent
        print(repr(content))

        # TODO improve this, as this is not robust
        # TODO also remove any enclosing quotes
        content = re.sub(
            f"^\\s*{target_character.name}\\s*:\\s*",
            "",
            content,
            flags=re.IGNORECASE,
        )

        message = await self.storage.make_message(
            session_id,
            parent_message_id,
            target_character.character_id,
            content,
        )

        # TODO log token usage with associated message_id

        return message


def clean(text):
    text = inspect.cleandoc(text)
    text = re.sub(r"(?<=\S) *\r?\n(?=\S)", " ", text)
    return text
