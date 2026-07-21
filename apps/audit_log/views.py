"""Routes for the audit_log app (auto-mounted at /api/audit_log).

Full CRUD over audit entries, except that editing and deleting are gated
behind ``settings.AUDIT_LOG_ALLOW_MUTATION`` (off by default) — see
:func:`require_mutation`. Creating and reading are always available, so the
table stays append-only unless mutation is deliberately switched on.

Note that the normal way to produce a row is ``services.audit_run`` from inside
the processing code, not these endpoints — it captures timing and exceptions
automatically. The write endpoints exist for backfills, corrections and
integrations that record their own runs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from apps.audit_log import services
from apps.audit_log.models import ProcessStatus
from apps.audit_log.schemas import (
    AuditLogCreate,
    AuditLogOut,
    AuditLogSummary,
    AuditLogUpdate,
)
from config.settings import settings

router = APIRouter()


def require_mutation() -> None:
    """Reject edits/deletes unless ``AUDIT_LOG_ALLOW_MUTATION`` is enabled.

    Read at request time rather than import time so the gate can be flipped in
    tests and in a running process without rebuilding the router.
    """
    if not settings.AUDIT_LOG_ALLOW_MUTATION:
        raise HTTPException(
            status.HTTP_405_METHOD_NOT_ALLOWED,
            "Audit entries are append-only. Set AUDIT_LOG_ALLOW_MUTATION=true "
            "to permit edits and deletes.",
            headers={"Allow": "GET, POST"},
        )


@router.post(
    "",
    response_model=AuditLogOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="audit_log_create",
)
async def create_entry(payload: AuditLogCreate) -> AuditLogOut:
    entry = await services.create_entry(payload)
    return AuditLogOut.model_validate(entry)


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


@router.patch(
    "/{entry_id}",
    response_model=AuditLogOut,
    operation_id="audit_log_update",
    dependencies=[Depends(require_mutation)],
)
async def update_entry(entry_id: str, payload: AuditLogUpdate) -> AuditLogOut:
    entry = await services.update_entry(entry_id, payload)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audit entry not found")
    return AuditLogOut.model_validate(entry)


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="audit_log_delete",
    dependencies=[Depends(require_mutation)],
)
async def delete_entry(entry_id: str) -> Response:
    if not await services.delete_entry(entry_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audit entry not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
