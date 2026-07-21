"""Pydantic schemas for the audit_log app."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


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
