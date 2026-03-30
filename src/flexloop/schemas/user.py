from datetime import datetime

from pydantic import BaseModel


class UserCreate(BaseModel):
    name: str
    gender: str
    age: int
    height: float
    weight: float
    weight_unit: str = "kg"
    height_unit: str = "cm"
    experience_level: str
    goals: str
    available_equipment: list[str] = []


class UserUpdate(BaseModel):
    name: str | None = None
    gender: str | None = None
    age: int | None = None
    height: float | None = None
    weight: float | None = None
    experience_level: str | None = None
    goals: str | None = None
    available_equipment: list[str] | None = None


class UserResponse(BaseModel):
    id: int
    name: str
    gender: str
    age: int
    height: float
    weight: float
    weight_unit: str
    height_unit: str
    experience_level: str
    goals: str
    available_equipment: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}
