"""SQLAlchemy models for the audit_log app (stored in Databricks).

One row per processing run, capturing what was processed, how it ended, and
enough detail to diagnose a failure without re-running it.
"""

from __future__ import annotations

import traceback
from datetime import date, datetime, timezone
from enum import StrEnum

from databricks.sqlalchemy import TIMESTAMP
from sqlalchemy import Date, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.models import TimestampedModel
from core.types import JSONText


class ProcessStatus(StrEnum):
    """Lifecycle of a processing run.

    Stored as a plain STRING: Databricks has no enum type and would not enforce
    one anyway, so the constraint lives in Python.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class AuditLog(TimestampedModel):
    """Audit trail for a lease-processing run.

    ``Created_Timestamp`` is the ``created_at`` column inherited from
    ``TimestampedModel``, alongside ``id`` (UUID string) and ``updated_at``.
    """

    __tablename__ = "audit_log"

    # --- what ran -----------------------------------------------------------
    process_id: Mapped[str] = mapped_column(String(64))
    process_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # --- the lease term being processed -------------------------------------
    lease_term_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- outcome ------------------------------------------------------------
    processed_status: Mapped[str] = mapped_column(
        String(16), default=ProcessStatus.PENDING
    )
    log_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- how long it took (distinct from the lease dates above) -------------
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- failure detail -----------------------------------------------------
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # --- output state + metrics --------------------------------------------
    #: Arbitrary structured result (computed figures, downstream ids, ...).
    output_state: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    records_processed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- provenance ---------------------------------------------------------
    triggered_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- state transitions --------------------------------------------------
    def mark_running(self) -> None:
        self.processed_status = ProcessStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)

    def mark_success(
        self,
        *,
        output_state: dict | None = None,
        records_processed: int | None = None,
        log_info: str | None = None,
    ) -> None:
        self.processed_status = ProcessStatus.SUCCESS
        self.output_state = output_state
        self.records_processed = records_processed
        self.log_info = log_info
        self.finish()

    def mark_failed(self, exc: BaseException, *, log_info: str | None = None) -> None:
        """Record a failure, capturing the exception for later diagnosis."""
        self.processed_status = ProcessStatus.FAILED
        self.error_type = type(exc).__name__[:255]
        self.error_message = str(exc)
        self.error_traceback = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        if log_info is not None:
            self.log_info = log_info
        self.finish()

    def finish(self) -> None:
        self.finished_at = datetime.now(timezone.utc)
        if self.started_at is not None:
            delta = self.finished_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)

    def __str__(self) -> str:
        return f"{self.process_id} [{self.processed_status}]"
