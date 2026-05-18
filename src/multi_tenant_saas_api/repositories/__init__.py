"""Repository layer exports.

Repositories are the only layer that should build SQLAlchemy statements for
business persistence operations. Services and routes should depend on these
classes rather than querying ORM models directly.
"""

from multi_tenant_saas_api.repositories.api_keys import APIKeyRepository
from multi_tenant_saas_api.repositories.audit_events import AuditEventRepository
from multi_tenant_saas_api.repositories.idempotency import IdempotencyRecordRepository
from multi_tenant_saas_api.repositories.memberships import MembershipRepository
from multi_tenant_saas_api.repositories.organisations import OrganisationRepository
from multi_tenant_saas_api.repositories.projects import ProjectRepository
from multi_tenant_saas_api.repositories.readiness import DatabaseReadinessRepository
from multi_tenant_saas_api.repositories.users import UserRepository

__all__ = [
    "APIKeyRepository",
    "AuditEventRepository",
    "DatabaseReadinessRepository",
    "IdempotencyRecordRepository",
    "MembershipRepository",
    "OrganisationRepository",
    "ProjectRepository",
    "UserRepository",
]
