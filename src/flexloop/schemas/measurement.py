from datetime import date

from pydantic import BaseModel


class MeasurementCreate(BaseModel):
    user_id: int
    date: date
    type: str
    value: float
    notes: str | None = None


class MeasurementResponse(BaseModel):
    id: int
    user_id: int
    date: date
    type: str
    value: float
    notes: str | None = None

    model_config = {"from_attributes": True}
