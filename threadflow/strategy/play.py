import inspect
import random
import re
from typing import Optional

from ..container import AgentMessageRequest
from ..agent import Agent

from .base import Strategy


class PlayStrategy(Strategy):
    def __init__(self, agent: Agent):
        self.agent = agent

    async def build_prompt(
        self,
        session,
        parent_message_id: Optional[str],
        character_id: str,
    ) -> str:
        messages = await self.build_messages(session, parent_message_id)

        system_content = clean(
            """
            You are an expert writer, helping the user write the scenario for a play.
            Your style expresses the personality of the character speaking.
            """
        )

        # TODO should fetch participant list more cleverly
        participant_ids = list(session.characters.keys())

        participants = []
        for i in participant_ids:
            name = session.characters[i].name
            prompt = session.public_prompts[i]
            if i == character_id:
                prompt += " " + session.private_prompts[i]
            participant = name, prompt
            participants.append(participant)

        participants_prompt = "\n\n".join(
            f" - {name}: {prompt}" for name, prompt in participants
        )

        fragments = []
        for message in messages:
            name = session.characters[message.character_id].name
            content = message.content.strip()
            fragment = f"{name.upper()}:\n{content}"
            fragments.append(fragment)
        history_prompt = "\n\n".join(fragments)

        if len(messages) == 0:
            user_content = clean(
                """

                ## CONTEXT

                {context}

                ## CHARACTERS

                {characters}

                ## TASK

                Given the context, the characters that are in the scene, what does
                {name} says to start the conversation? Only reply what is said by the
                character, nothing more.

                """
            ).format(
                context=session.pre_prompt,
                characters=participants_prompt,
                name=session.characters[character_id].name,
            )

        else:
            user_content = clean(
                """

                ## CONTEXT

                {context}

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
                context=session.pre_prompt,
                characters=participants_prompt,
                script=history_prompt,
                name=session.characters[character_id].name,
            )

        return [
            {
                "role": "system",
                "content": system_content,
            },
            {
                "role": "user",
                "content": user_content,
            },
        ]

    async def handle(
        self,
        session,
        parent_message_id: Optional[str],
        character_id: str,
    ) -> str:
        prompt = await self.build_prompt(session, parent_message_id, character_id)
        print(repr(prompt))

        content = await self.agent.do_completion(prompt)
        # TODO use stop to avoid multi answers by agent
        print(repr(content))

        name = session.characters[character_id].name
        content = re.sub(f"^\\s*{name}\\s*:\\s*", "", content, flags=re.IGNORECASE)
        return content

    async def choose_character(self, session, message_id: str) -> str:
        # TODO ask agent
        character_ids = await session.get_active_characters(message_id)
        character_id = random.choice(character_ids)
        return character_id


def clean(text):
    text = inspect.cleandoc(text)
    text = re.sub(r"(?<=\S) *\r?\n(?=\S)", " ", text)
    return text
