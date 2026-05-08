"""Pydantic schemas for the training endpoints."""
from pydantic import BaseModel


class QuestionOut(BaseModel):
    id: str
    text: str
    choices: list[str]


class GoldDocOut(BaseModel):
    gold_id: str
    content: str


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
    content: str
    expected_concepts: list[ConceptInput]
    min_concept_count: int


class GoldDocsListResponse(BaseModel):
    resolved: list[dict]
    overrides: list[dict]
