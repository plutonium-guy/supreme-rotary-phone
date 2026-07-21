"""Admin registration for the audit_log app."""

from core.admin import register_model

from apps.audit_log.models import AuditLog

register_model(
    AuditLog,
    list_display=(
        "process_id",
        "process_name",
        "lease_id",
        "processed_status",
        "start_date",
        "end_date",
        "records_processed",
        "created_at",
    ),
    search_fields=("process_id", "lease_id", "process_name", "error_message"),
    list_filter=("processed_status", "environment"),
)
