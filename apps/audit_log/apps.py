"""App configuration for the audit_log app."""

from core.apps import AppConfig


class AuditLogConfig(AppConfig):
    name = "apps.audit_log"
    label = "audit_log"
    verbose_name = "Audit Log"
