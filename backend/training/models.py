"""Pydantic schemas for the training endpoints."""
from pydantic import BaseModel, Field, model_validator


class QuestionOut(BaseModel):
    id: str
    text: str
    choices: list[str]


class GoldDocOut(BaseModel):
    gold_id: str
    content: str
    expected_concepts: list[dict]   # 16c.1 — reveal panel needs this
    min_concept_count: int          # 16c.1 — reveal panel label


class StartResponse(BaseModel):
    attempt_id: int
    attempt_number: int
    questions: list[QuestionOut]
    gold_docs: list[GoldDocOut]


class QuizSubmitRequest(BaseModel):
    attempt_id: int
    answers: dict[str, int]


class QuizSubmitResponse(BaseModel):
    score: int
    total: int


class AnnotateSubmitRequest(BaseModel):
    attempt_id: int
    gold_id: str
    references: list[dict]


class AnnotateSubmitResponse(BaseModel):
    passed: bool
    matched_count: int
    expected_count: int
    min_concept_count: int


class OkResponse(BaseModel):
    ok: bool = True


class ConceptInput(BaseModel):
    kanun_no: str
    kanun_ad: str | None = None
    madde: str | None = None
    fikra: str | None = None
    bent: str | None = None


class GoldDocUpsertRequest(BaseModel):
    content: str = Field(min_length=1)
    expected_concepts: list[ConceptInput] = Field(min_length=1, max_length=50)
    min_concept_count: int = Field(ge=1)

    @model_validator(mode='after')
    def check_min_concept_count_in_range(self):
        if self.min_concept_count > len(self.expected_concepts):
            raise ValueError(
                f"min_concept_count ({self.min_concept_count}) cannot exceed "
                f"expected_concepts length ({len(self.expected_concepts)})"
            )
        return self


class GoldDocsListResponse(BaseModel):
    resolved: list[dict]
    overrides: list[dict]


class QuizUpsertRequest(BaseModel):
    text: str = Field(min_length=1)
    choices: list[str] = Field(min_length=2, max_length=8)
    correct_choice_idx: int = Field(ge=0)

    @model_validator(mode='after')
    def check_correct_idx_in_range(self):
        if self.correct_choice_idx >= len(self.choices):
            raise ValueError(
                f"correct_choice_idx ({self.correct_choice_idx}) must be in range "
                f"[0, {len(self.choices)})"
            )
        if any(not c.strip() for c in self.choices):
            raise ValueError("choices entries must be non-empty strings")
        return self


class QuizListResponse(BaseModel):
    resolved: list[dict]
    overrides: list[dict]
