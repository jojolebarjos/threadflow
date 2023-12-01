import os

from openai import AsyncAzureOpenAI


def create_client():
    # TODO improve client configuration
    assert os.environ.get("OPENAI_API_TYPE") == "azure"
    client = AsyncAzureOpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        api_version=os.environ["OPENAI_API_VERSION"],
        azure_endpoint=os.environ["OPENAI_API_BASE"],
    )
    return client


class Agent:
    def __init__(self):
        self.client = create_client()

    async def do_completion(self, messages) -> str:
        # TODO select deployment from config
        model = "gpt-35-turbo"

        # TODO `frequency_penalty`
        # TODO `logit_bias`
        # TODO `max_tokens`
        # TODO `stop`, which may be used to stop generation early
        # TODO `temperature`, typically between 0.0 and 2.0
        # TODO `user`, which is a way to identify the actual end user and identify abuse

        completion = await self.client.chat.completions.create(
            messages=messages,
            model=model,
        )

        # TODO log token `usage`

        # TODO can it be more than one?
        assert len(completion.choices) == 1
        choice = completion.choices[0]

        return choice.message.content
