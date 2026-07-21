"""Pydantic schemas for the audit_log app."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from apps.audit_log.models import ProcessStatus


class AuditLogCreate(BaseModel):
    """Payload for creating an audit entry.

    Only ``process_id`` is required; a row can be opened with nothing else and
    filled in as the run progresses.
    """

    process_id: str = Field(min_length=1, max_length=64)
    process_name: str | None = Field(default=None, max_length=128)
    lease_id: str | None = Field(default=None, max_length=64)

    lease_term_months: int | None = Field(default=None, ge=0)
    start_date: date | None = None
    end_date: date | None = None

    processed_status: ProcessStatus = ProcessStatus.PENDING
    log_info: str | None = None

    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)

    error_type: str | None = Field(default=None, max_length=255)
    error_message: str | None = None
    error_traceback: str | None = None
    retry_count: int = Field(default=0, ge=0)

    output_state: dict | None = None
    records_processed: int | None = Field(default=None, ge=0)
    records_failed: int | None = Field(default=None, ge=0)

    triggered_by: str | None = Field(default=None, max_length=128)
    environment: str | None = Field(default=None, max_length=32)


class AuditLogUpdate(BaseModel):
    """Partial update. Only fields actually supplied are applied.

    ``process_id`` is deliberately absent: re-pointing an audit row at a
    different run would falsify the trail.
    """

    process_name: str | None = Field(default=None, max_length=128)
    lease_id: str | None = Field(default=None, max_length=64)

    lease_term_months: int | None = Field(default=None, ge=0)
    start_date: date | None = None
    end_date: date | None = None

    processed_status: ProcessStatus | None = None
    log_info: str | None = None

    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)

    error_type: str | None = Field(default=None, max_length=255)
    error_message: str | None = None
    error_traceback: str | None = None
    retry_count: int | None = Field(default=None, ge=0)

    output_state: dict | None = None
    records_processed: int | None = Field(default=None, ge=0)
    records_failed: int | None = Field(default=None, ge=0)

    triggered_by: str | None = Field(default=None, max_length=128)
    environment: str | None = Field(default=None, max_length=32)


class AuditLogOut(BaseModel):
    """Full audit row, including failure detail and output state."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    process_id: str
    process_name: str | None
    lease_id: str | None

    lease_term_months: int | None
    start_date: date | None
    end_date: date | None

    processed_status: str
    log_info: str | None

    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None

    error_type: str | None
    error_message: str | None
    error_traceback: str | None
    retry_count: int

    output_state: dict | None
    records_processed: int | None
    records_failed: int | None

    triggered_by: str | None
    environment: str | None

    created_at: datetime


class AuditLogSummary(BaseModel):
    """Trimmed row for listings — omits traceback and output payload."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    process_id: str
    process_name: str | None
    lease_id: str | None
    processed_status: str
    start_date: date | None
    end_date: date | None
    records_processed: int | None
    duration_ms: int | None
    error_message: str | None
    created_at: datetime
