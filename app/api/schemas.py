"""Pydantic DTOs at the HTTP boundary.

Mirrors the read/write payloads documented in:
- specs/001-verify-and-review/contracts/api.md
- specs/001-verify-and-review/data-model.md
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# --- Submission status / verdict literal types ----------------------------

SubmissionStatus = Literal[
    "loaded",
    "processing",
    "ready_for_review",
    "approved",
    "rejected",
    "extraction_failed",
]
ModelVerdict = Literal["pass", "fail", "not_applicable"]
OverrideVerdict = Literal["pass", "fail"]
EffectiveVerdict = Literal["pass", "fail", "not_applicable"]
DecisionKind = Literal["approved", "rejected"]
Confidence = Literal["hi", "med", "low"]
DiffKind = Literal["equal", "added", "removed"]


# --- Expected values --------------------------------------------------------


class ExpectedValues(BaseModel):
    """The expected-values payload stored on a submission (JSONB column).

    Cross-field rule: if `is_imported` is true, `country_of_origin` must be a
    non-empty string. Validated at the API boundary; the DB column is JSONB and
    does not enforce shape.
    """

    model_config = ConfigDict(extra="forbid")

    brand: Annotated[str, StringConstraints(min_length=1)]
    class_type: Annotated[str, StringConstraints(min_length=1)]
    alcohol_content: float
    net_contents: Annotated[str, StringConstraints(min_length=1)]
    producer_name: Annotated[str, StringConstraints(min_length=1)]
    producer_address: Annotated[str, StringConstraints(min_length=1)]
    is_imported: bool
    country_of_origin: str | None = None

    @model_validator(mode="after")
    def _country_required_if_imported(self) -> ExpectedValues:
        if self.is_imported and not (self.country_of_origin and self.country_of_origin.strip()):
            raise ValueError(
                "country_of_origin is required and must be non-empty when is_imported is true"
            )
        return self


# --- Queue list -------------------------------------------------------------


class SubmissionListItem(BaseModel):
    id: UUID
    status: SubmissionStatus
    brand: str = Field(description="Derived from expected_values.brand for display.")
    is_fixture: bool
    created_at: datetime
    thumbnail_url: str
    has_extraction_error: bool


# --- Word-diff token --------------------------------------------------------


class DiffToken(BaseModel):
    text: str
    kind: DiffKind


# --- Review payload ---------------------------------------------------------


class OverrideOut(BaseModel):
    field: str
    original_verdict: ModelVerdict
    override_verdict: OverrideVerdict
    comment: str
    created_at: datetime


class FieldRowOut(BaseModel):
    id: UUID = Field(description="comparisons.id — referenced from rejection_field_ids.")
    field: str
    extracted: str | None = Field(alias="extracted_value", default=None)
    expected: str | None = Field(alias="expected_value", default=None)
    model_verdict: ModelVerdict
    effective_verdict: EffectiveVerdict
    rule: str
    reason: str | None = None
    confidence: Confidence | None = None
    diff_extracted: list[DiffToken] | None = None
    diff_expected: list[DiffToken] | None = None
    override: OverrideOut | None = None

    model_config = ConfigDict(populate_by_name=True)


class FieldGroupOut(BaseModel):
    name: Literal["Identity", "Producer", "Quantitative", "Origin", "Government Warning"]
    fields: list[FieldRowOut]


class ExtractionTokens(BaseModel):
    input: int | None = None
    output: int | None = None


class ExtractionOut(BaseModel):
    model: str
    latency_ms: int | None = None
    tokens: ExtractionTokens
    error: str | None = None


class ReviewOut(BaseModel):
    decision: DecisionKind
    comment: str | None = None
    rejection_field_ids: list[UUID] | None = None
    created_at: datetime


class SubmissionDetailOut(BaseModel):
    id: UUID
    status: SubmissionStatus
    is_fixture: bool
    created_at: datetime
    image_url: str
    expected_values: ExpectedValues
    extraction: ExtractionOut | None = None
    groups: list[FieldGroupOut] = Field(default_factory=list)
    review: ReviewOut | None = None


# --- Overrides --------------------------------------------------------------


class OverrideIn(BaseModel):
    field: Annotated[str, StringConstraints(min_length=1)]
    override_verdict: OverrideVerdict
    comment: Annotated[str, StringConstraints(max_length=2000)] = ""


# --- Decisions --------------------------------------------------------------


class DecisionIn(BaseModel):
    decision: DecisionKind
    comment: Annotated[str, StringConstraints(max_length=2000)] | None = None
    rejection_field_ids: list[UUID] | None = None

    @model_validator(mode="after")
    def _reject_requires_reasons_approve_forbids_them(self) -> DecisionIn:
        if self.decision == "rejected":
            if not self.rejection_field_ids:
                raise ValueError(
                    "rejection_field_ids must be a non-empty list when decision is 'rejected'"
                )
        else:  # approved
            if self.rejection_field_ids:
                raise ValueError(
                    "rejection_field_ids must be omitted or empty when decision is 'approved'"
                )
        return self


class DecisionOut(BaseModel):
    decision: DecisionKind
    comment: str | None = None
    rejection_field_ids: list[UUID] | None = None
    created_at: datetime


# --- Submission write/start outputs ----------------------------------------


class SubmissionCreateOut(BaseModel):
    id: UUID
    status: SubmissionStatus


class BulkErrorOut(BaseModel):
    row: int | None = Field(
        default=None,
        description="1-based CSV row number (excluding header). None for batch-level errors.",
    )
    filename: str | None = None
    reason: str


class BulkCreateOut(BaseModel):
    created: list[SubmissionCreateOut]
    errors: list[BulkErrorOut]


class StartOut(BaseModel):
    scheduled: int
    submission_ids: list[UUID]


# --- Admin -----------------------------------------------------------------


class AdminResetIn(BaseModel):
    confirm: bool

    @model_validator(mode="after")
    def _must_be_true(self) -> AdminResetIn:
        if self.confirm is not True:
            raise ValueError("confirm must be exactly true")
        return self


class AdminResetOut(BaseModel):
    deleted_submissions: int
    restored_fixtures: int


# --- Errors -----------------------------------------------------------------


class ApiError(BaseModel):
    """Shape of FastAPI's default error response. Documented for the OpenAPI doc."""

    detail: str | list[dict[str, Any]]
    code: str | None = None


# --- Field-set constants (UI grouping) -------------------------------------

FIELD_GROUPS: list[tuple[str, list[str]]] = [
    ("Identity", ["brand", "class_type"]),
    ("Producer", ["producer_name", "producer_address"]),
    ("Quantitative", ["alcohol_content", "net_contents"]),
    ("Origin", ["is_imported", "country_of_origin"]),
    (
        "Government Warning",
        ["government_warning_text", "government_warning_style"],
    ),
]

ALL_FIELDS: list[str] = [f for _, fields in FIELD_GROUPS for f in fields]
