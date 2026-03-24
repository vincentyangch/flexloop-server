from datetime import datetime

from pydantic import BaseModel


class TemplateCreate(BaseModel):
    user_id: int
    name: str
    exercises_json: list[dict]


class TemplateUpdate(BaseModel):
    name: str | None = None
    exercises_json: list[dict] | None = None


class TemplateResponse(BaseModel):
    id: int
    user_id: int
    name: str
    exercises_json: list[dict]
    created_at: datetime

    model_config = {"from_attributes": True}
