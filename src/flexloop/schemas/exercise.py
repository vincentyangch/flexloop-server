from pydantic import BaseModel


class ExerciseResponse(BaseModel):
    id: int
    name: str
    muscle_group: str
    equipment: str
    category: str
    difficulty: str
    source_plugin: str | None = None
    metadata_json: dict | None = None

    model_config = {"from_attributes": True}


class ExerciseListResponse(BaseModel):
    exercises: list[ExerciseResponse]
    total: int
