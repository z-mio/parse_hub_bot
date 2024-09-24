from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI


class LLM:
    def __init__(
        self,
        provider: Literal["openai"],
        api_key: str,
        base_url: str = None,
        model: str = "gpt-4o",
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.provider = self.select_provider(provider)

    def select_provider(self, provider: str) -> BaseChatModel:
        match provider:
            case "openai":
                return ChatOpenAI(
                    api_key=self.api_key, base_url=self.base_url, model=self.model
                )
            case _:
                ...
