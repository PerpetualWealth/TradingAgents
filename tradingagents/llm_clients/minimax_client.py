from typing import Any, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .openai_client import OpenAIClient
from .base_client import BaseLLMClient


class MiniMaxChatOpenAI(ChatOpenAI):
    """MiniMax-specific ChatOpenAI that handles reasoning_split response format.

    When using reasoning_split=True, MiniMax returns responses with extra fields
    like 'base_resp' and 'choices' may be null. We need to unwrap the base_resp
    field to get the actual response data.
    """

    def _create_chat_result(
        self,
        response: dict | object,
        generation_info: dict | None = None,
    ) -> ChatResult:
        """Override to handle MiniMax's base_resp wrapped response format."""
        # Convert response to dict if it's a Pydantic model
        if hasattr(response, 'model_dump'):
            response_dict = response.model_dump()
        elif isinstance(response, dict):
            response_dict = response
        else:
            # Fallback to default behavior
            return super()._create_chat_result(response, generation_info)

        # Check if response has 'base_resp' field and choices is null
        if "base_resp" in response_dict:
            base_resp = response_dict.get("base_resp", {})
            if isinstance(base_resp, dict) and "choices" in base_resp:
                # Unwrap: replace the top-level choices with base_resp.choices
                response_dict = dict(response_dict)  # Make a copy
                response_dict["choices"] = base_resp["choices"]

        # Call parent with the unwrapped dict
        return super()._create_chat_result(response_dict, generation_info)


class MiniMaxClient(OpenAIClient):
    """MiniMax-specific client with reasoning_split support.

    MiniMax API is OpenAI-compatible but requires special parameters
    like reasoning_split to handle thinking mode properly.
    """

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        # Initialize with provider="openai" since MiniMax uses OpenAI-compatible API
        super().__init__(model, base_url, provider="minimax", **kwargs)

    def get_llm(self) -> Any:
        """Return configured MiniMaxChatOpenAI instance with MiniMax-specific parameters."""
        # Get base configuration from parent
        llm_kwargs = {"model": self.model}

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

        # MiniMax: 强制启用 reasoning_split，避免 think 标签污染 JSON 报告
        llm_kwargs["extra_body"] = {"reasoning_split": True}

        # Pass through standard kwargs
        for key in ("timeout", "max_retries", "api_key", "callbacks"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return MiniMaxChatOpenAI(**llm_kwargs)
