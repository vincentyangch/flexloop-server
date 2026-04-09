from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    @property
    def cache_hit(self) -> bool:
        return self.cache_read_tokens > 0

    @property
    def tokens_saved(self) -> int:
        """Tokens that were served from cache instead of reprocessed."""
        return self.cache_read_tokens


@dataclass
class ToolDef:
    """Provider-agnostic tool definition."""
    name: str
    description: str
    input_schema: dict


@dataclass
class ToolCall:
    """A tool call extracted from a model response."""
    id: str
    name: str
    input: dict


@dataclass
class ToolUseResponse:
    """Response from a tool_use() call, possibly containing tool calls."""
    content: list
    tool_calls: list
    text: str
    stop_reason: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    def to_llm_response(self) -> "LLMResponse":
        return LLMResponse(
            content=self.text,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_read_tokens=self.cache_read_tokens,
            cache_creation_tokens=self.cache_creation_tokens,
        )


@dataclass
class StreamEvent:
    """A single event emitted by ``LLMAdapter.stream_generate``.

    ``type`` is one of:
    - ``"content"``: incremental text chunk; ``delta`` holds the bytes.
    - ``"usage"``: terminal token/latency info; populated fields are
      ``input_tokens``, ``output_tokens``, ``cache_read_tokens``, ``latency_ms``.
    - ``"done"``: explicit end-of-stream marker — frontends use this to
      render a "complete" state before the HTTP connection closes.
    - ``"error"``: adapter failure during streaming; ``error`` holds the
      human-readable message. Streams with an error event also emit a
      final ``"done"`` event.
    """
    type: str
    delta: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    latency_ms: int | None = None
    error: str | None = None


class LLMAdapter(ABC):
    def __init__(self, model: str, api_key: str, base_url: str = "", **kwargs):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    async def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        pass

    @abstractmethod
    async def chat(
        self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 2000,
    ) -> LLMResponse:
        pass

    async def tool_use(
        self, system_prompt: str, messages: list[dict], tools: list,
        tool_choice: str = "auto", temperature: float = 0.7, max_tokens: int = 2000,
    ) -> ToolUseResponse:
        """Send a request with tool definitions. Override in adapters that support tool use."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support tool_use()")
