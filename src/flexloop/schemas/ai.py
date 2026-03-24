from pydantic import BaseModel


class AIChatRequest(BaseModel):
    user_id: int
    message: str


class AIChatResponse(BaseModel):
    reply: str
    input_tokens: int
    output_tokens: int


class AIReviewRequest(BaseModel):
    user_id: int
    plan_id: int | None = None


class AISuggestion(BaseModel):
    text: str
    confidence: str
    reasoning: str


class AIReviewResponse(BaseModel):
    id: int
    review_type: str
    summary: dict
    suggestions: list[AISuggestion]
    model_used: str
    input_tokens: int
    output_tokens: int
    estimated_cost: float

    model_config = {"from_attributes": True}


class AISuggestionUpdate(BaseModel):
    accepted: bool


class AIUsageResponse(BaseModel):
    month: str
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    estimated_cost: float
    call_count: int

    model_config = {"from_attributes": True}
