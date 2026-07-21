"""Routes for the audit_log app (auto-mounted at /api/audit_log).

Read-only. Audit rows are written by the processing code via
``services.audit_run``, never over HTTP — an audit trail an API client can
forge is not an audit trail.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from apps.audit_log import services
from apps.audit_log.models import ProcessStatus
from apps.audit_log.schemas import AuditLogOut, AuditLogSummary

router = APIRouter()


@router.get("", response_model=list[AuditLogSummary], operation_id="audit_log_list")
async def list_entries(
    process_id: str | None = None,
    lease_id: str | None = None,
    status_filter: ProcessStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, le=500),
    offset: int = 0,
) -> list[AuditLogSummary]:
    entries = await services.list_entries(
        process_id=process_id,
        lease_id=lease_id,
        status=status_filter.value if status_filter else None,
        limit=limit,
        offset=offset,
    )
    return [AuditLogSummary.model_validate(e) for e in entries]


@router.get("/{entry_id}", response_model=AuditLogOut, operation_id="audit_log_retrieve")
async def retrieve_entry(entry_id: str) -> AuditLogOut:
    entry = await services.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audit entry not found")
    return AuditLogOut.model_validate(entry)
