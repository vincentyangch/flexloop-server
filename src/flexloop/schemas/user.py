from datetime import datetime

from pydantic import BaseModel


class UserCreate(BaseModel):
    name: str
    gender: str
    age: int
    height_cm: float
    weight_kg: float
    experience_level: str
    goals: str
    available_equipment: list[str] = []


class UserUpdate(BaseModel):
    name: str | None = None
    gender: str | None = None
    age: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    experience_level: str | None = None
    goals: str | None = None
    available_equipment: list[str] | None = None


class UserResponse(BaseModel):
    id: int
    name: str
    gender: str
    age: int
    height_cm: float
    weight_kg: float
    experience_level: str
    goals: str
    available_equipment: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}
