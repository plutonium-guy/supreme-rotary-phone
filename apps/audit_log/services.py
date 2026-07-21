"""Business logic for the audit_log app.

The intended entry point is :func:`audit_run`, an async context manager that
brackets a processing run and records its outcome whether it succeeds or
raises::

    async with audit_run(
        process_id="RUN-2026-07-001",
        process_name="ifrs16_remeasurement",
        lease_id="LEASE-42",
        lease_term_months=36,
        start_date=date(2026, 1, 1),
        end_date=date(2028, 12, 31),
    ) as run:
        result = do_the_work()
        run.succeed(output_state=result, records_processed=len(result))

If the block raises, the failure (type, message, traceback) is recorded and the
exception is re-raised — auditing never swallows an error.

Each run costs two warehouse round-trips: one to persist the RUNNING row, one
to finalise it. That is deliberate; a crash mid-run leaves a RUNNING row behind
rather than no evidence at all.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from typing import Any, AsyncIterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.audit_log.models import AuditLog, ProcessStatus
from core.db import run_db


class RunHandle:
    """Mutable handle yielded by :func:`audit_run`.

    Collects the outcome during the block; :func:`audit_run` persists it on
    exit. A block that completes without calling anything still records
    SUCCESS.
    """

    def __init__(self, log_id: str) -> None:
        self.id = log_id
        self.output_state: dict | None = None
        self.records_processed: int | None = None
        self.records_failed: int | None = None
        self.log_info: str | None = None
        self.status: ProcessStatus | None = None

    def succeed(
        self,
        *,
        output_state: dict | None = None,
        records_processed: int | None = None,
        records_failed: int | None = None,
        log_info: str | None = None,
    ) -> None:
        self.status = ProcessStatus.SUCCESS
        self.output_state = output_state
        self.records_processed = records_processed
        self.records_failed = records_failed
        self.log_info = log_info

    def partial(self, **kwargs: Any) -> None:
        """Completed, but not everything landed (some records failed)."""
        self.succeed(**kwargs)
        self.status = ProcessStatus.PARTIAL

    def skip(self, log_info: str | None = None) -> None:
        self.status = ProcessStatus.SKIPPED
        self.log_info = log_info


async def start_run(
    *,
    process_id: str,
    process_name: str | None = None,
    lease_id: str | None = None,
    lease_term_months: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    triggered_by: str | None = None,
    environment: str | None = None,
) -> str:
    """Persist a RUNNING audit row and return its id."""

    def _work(session: Session) -> str:
        row = AuditLog(
            process_id=process_id,
            process_name=process_name,
            lease_id=lease_id,
            lease_term_months=lease_term_months,
            start_date=start_date,
            end_date=end_date,
            triggered_by=triggered_by,
            environment=environment,
        )
        row.mark_running()
        session.add(row)
        return row.id

    return await run_db(_work)


async def finish_run(handle: RunHandle, status: ProcessStatus) -> None:
    def _work(session: Session) -> None:
        row = session.get(AuditLog, handle.id)
        if row is None:
            return
        row.processed_status = status
        row.output_state = handle.output_state
        row.records_processed = handle.records_processed
        row.records_failed = handle.records_failed
        if handle.log_info is not None:
            row.log_info = handle.log_info
        row.finish()

    await run_db(_work)


async def fail_run(handle: RunHandle, exc: BaseException) -> None:
    def _work(session: Session) -> None:
        row = session.get(AuditLog, handle.id)
        if row is None:
            return
        row.mark_failed(exc, log_info=handle.log_info)
        row.records_processed = handle.records_processed
        row.records_failed = handle.records_failed

    await run_db(_work)


@asynccontextmanager
async def audit_run(**kwargs: Any) -> AsyncIterator[RunHandle]:
    """Bracket a processing run, recording SUCCESS or FAILED on exit."""
    log_id = await start_run(**kwargs)
    handle = RunHandle(log_id)
    try:
        yield handle
    except BaseException as exc:
        await fail_run(handle, exc)
        raise  # auditing must never swallow the error
    else:
        await finish_run(handle, handle.status or ProcessStatus.SUCCESS)


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #
async def get_entry(entry_id: str) -> AuditLog | None:
    return await run_db(lambda s: s.get(AuditLog, entry_id))


async def list_entries(
    *,
    process_id: str | None = None,
    lease_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditLog]:
    def _work(session: Session) -> list[AuditLog]:
        stmt = select(AuditLog)
        if process_id:
            stmt = stmt.where(AuditLog.process_id == process_id)
        if lease_id:
            stmt = stmt.where(AuditLog.lease_id == lease_id)
        if status:
            stmt = stmt.where(AuditLog.processed_status == status)
        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        return list(session.scalars(stmt))

    return await run_db(_work)
