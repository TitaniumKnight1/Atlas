from __future__ import annotations

from pydantic import BaseModel, Field


class AuditReference(BaseModel):
    ref_type: str
    ref_id: str


class ErrorPayload(BaseModel):
    code: str
    message: str


class ResponseEnvelope(BaseModel):
    ok: bool
    data: dict | list[dict] | None = None
    error: ErrorPayload | None = None
    warnings: list[str] = Field(default_factory=list)
    audit_ref: AuditReference | None = None


class DiscoverGitRequest(BaseModel):
    path_filters: list[str] | None = None


class CloneRepositoryRequest(BaseModel):
    remote_url: str
    destination_path: str
    repository_role: str = "resource"


class PullRepositoryRequest(BaseModel):
    idempotency_key: str | None = None


class CreateBranchRequest(BaseModel):
    branch_name: str
    idempotency_key: str | None = None


class CheckoutRefRequest(BaseModel):
    ref_name: str
    idempotency_key: str | None = None


class DeleteBranchRequest(BaseModel):
    branch_name: str
    idempotency_key: str | None = None


class CreateCommitRequest(BaseModel):
    message: str
    paths: list[str] | None = None
    idempotency_key: str | None = None
