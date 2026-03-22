from typing import Any, Optional

from .openai_client import OpenAIClient
from .base_client import BaseLLMClient


class MiniMaxClient(OpenAIClient):
    """MiniMax-specific client with reasoning_split support.

    MiniMax API is OpenAI-compatible but requires special parameters
    like reasoning_split to handle thinking mode properly.
    """

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        # Initialize with provider="openai" since MiniMax uses OpenAI-compatible API
        super().__init__(model, base_url, provider="minimax", **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI instance with MiniMax-specific parameters."""
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

        from .openai_client import UnifiedChatOpenAI
        return UnifiedChatOpenAI(**llm_kwargs)
