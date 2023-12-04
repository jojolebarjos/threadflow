import os

from openai import AsyncAzureOpenAI, AsyncOpenAI

from .base import Agent


def create_client() -> AsyncOpenAI:
    api_type = os.environ.get("OPENAI_API_TYPE")

    if api_type == "azure":
        return AsyncAzureOpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            api_version=os.environ["OPENAI_API_VERSION"],
            azure_endpoint=os.environ["OPENAI_API_BASE"],
        )

    if api_type == "openai":
        return AsyncOpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.environ.get("OPENAI_API_BASE"),
        )

    raise KeyError(api_type)


class OpenAIAgent(Agent):
    def __init__(self, model_name: str):
        self.client = create_client()
        self.model_name = model_name

    async def do_completion(self, messages) -> str:
        # TODO `frequency_penalty`
        # TODO `logit_bias`
        # TODO `max_tokens`
        # TODO `stop`, which may be used to stop generation early
        # TODO `temperature`, typically between 0.0 and 2.0
        # TODO `user`, which is a way to identify the actual end user and identify abuse

        completion = await self.client.chat.completions.create(
            messages=messages,
            model=self.model_name,
        )

        # TODO log token `usage`

        # TODO can it be more than one?
        assert len(completion.choices) == 1
        choice = completion.choices[0]

        return choice.message.content
