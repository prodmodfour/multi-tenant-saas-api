"""Authentication API workflows.

The classes in this module own registration, login, and current-user business
logic for the local demo authentication model. They keep route handlers thin and
ensure password hashing, token validation, persistence, and audit writes remain
outside the HTTP layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from multi_tenant_saas_api.database import Organisation, OrganisationMembership, User
from multi_tenant_saas_api.domain import (
    AuditAction,
    MembershipID,
    OrganisationID,
    OrganisationRole,
    UserID,
)
from multi_tenant_saas_api.repositories import (
    AuditEventRepository,
    MembershipRepository,
    OrganisationRepository,
    UserRepository,
)
from multi_tenant_saas_api.services.auth import (
    AccessToken,
    AccessTokenError,
    AccessTokenService,
    PasswordHashingService,
    PrincipalType,
)


class AuthAPIServiceError(ValueError):
    """Base class for safe authentication API workflow errors."""


class EmailAlreadyRegisteredError(AuthAPIServiceError):
    """Raised when a registration email is already in use."""


class InvalidCredentialsError(AuthAPIServiceError):
    """Raised when login credentials should receive the generic failure response."""


class InvalidBearerTokenError(AuthAPIServiceError):
    """Raised when a bearer token cannot resolve an active current user."""


@dataclass(frozen=True, slots=True)
class PublicUser:
    """Secret-safe user data returned by authentication workflows."""

    id: UserID
    email: str
    display_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CurrentUserMembership:
    """Membership summary for the current-user response."""

    membership_id: MembershipID
    organisation_id: OrganisationID
    organisation_name: str
    organisation_slug: str
    role: OrganisationRole


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """Current authenticated user and organisation memberships."""

    user: PublicUser
    memberships: list[CurrentUserMembership]


class AuthAPIService:
    """Service layer for local email/password authentication endpoints."""

    __slots__ = (
        "_audit_events",
        "_memberships",
        "_organisations",
        "_passwords",
        "_session",
        "_tokens",
        "_users",
    )

    def __init__(
        self,
        *,
        session: AsyncSession,
        password_service: PasswordHashingService,
        token_service: AccessTokenService,
        user_repository: UserRepository | None = None,
        membership_repository: MembershipRepository | None = None,
        organisation_repository: OrganisationRepository | None = None,
        audit_event_repository: AuditEventRepository | None = None,
    ) -> None:
        """Initialise authentication workflows with repositories and utilities."""

        self._session = session
        self._passwords = password_service
        self._tokens = token_service
        self._users = user_repository or UserRepository(session)
        self._memberships = membership_repository or MembershipRepository(session)
        self._organisations = organisation_repository or OrganisationRepository(session)
        self._audit_events = audit_event_repository or AuditEventRepository(session)

    async def register_user(
        self,
        *,
        email: str,
        password: SecretStr,
        display_name: str,
    ) -> PublicUser:
        """Register a new user, storing only the derived password hash."""

        normalised_email = _normalise_email(email)
        existing_user = await self._users.get_by_email(normalised_email)
        if existing_user is not None:
            raise EmailAlreadyRegisteredError("email is already registered")

        password_hash = self._passwords.hash_password(password.get_secret_value())

        try:
            user = await self._users.create(
                email=normalised_email,
                display_name=display_name,
                password_hash=password_hash,
            )
            await self._audit_events.create(
                action=AuditAction.USER_REGISTERED,
                actor_user_id=user.id,
                target_type="user",
                target_id=user.id,
                event_metadata={},
            )
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise EmailAlreadyRegisteredError("email is already registered") from exc
        except Exception:
            await self._session.rollback()
            raise

        return _public_user_from_model(user)

    async def login_user(
        self,
        *,
        email: str,
        password: SecretStr,
    ) -> AccessToken:
        """Validate credentials and return a signed bearer access token."""

        normalised_email = _normalise_email(email)
        user = await self._users.get_by_email(normalised_email)
        if user is None or not user.is_active:
            raise InvalidCredentialsError("invalid email or password")

        password_matches = self._passwords.verify_password(
            password.get_secret_value(),
            user.password_hash,
        )
        if not password_matches:
            raise InvalidCredentialsError("invalid email or password")

        access_token = self._tokens.create_access_token(UserID(user.id))

        try:
            await self._audit_events.create(
                action=AuditAction.USER_LOGGED_IN,
                actor_user_id=user.id,
                target_type="user",
                target_id=user.id,
                event_metadata={},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return access_token

    async def get_current_user(self, *, bearer_token: str) -> CurrentUser:
        """Resolve a bearer token into the current active user and memberships."""

        try:
            principal = self._tokens.validate_access_token(bearer_token)
        except AccessTokenError as exc:
            raise InvalidBearerTokenError("invalid or expired access token") from exc

        if principal.principal_type is not PrincipalType.USER:
            raise InvalidBearerTokenError("invalid or expired access token")

        user = await self._users.get_by_id(_uuid_from_user_id(principal.user_id))
        if user is None or not user.is_active:
            raise InvalidBearerTokenError("invalid or expired access token")

        memberships = await self._memberships.list_for_user(user.id)
        current_user_memberships: list[CurrentUserMembership] = []
        for membership in memberships:
            organisation = await self._organisations.get_by_id(membership.organisation_id)
            if organisation is None:
                continue
            current_user_memberships.append(
                _current_user_membership_from_models(membership, organisation)
            )

        return CurrentUser(
            user=_public_user_from_model(user),
            memberships=current_user_memberships,
        )


def _normalise_email(email: str) -> str:
    """Normalise email addresses before uniqueness checks and login lookup."""

    return email.strip().lower()


def _uuid_from_user_id(user_id: UserID) -> UUID:
    """Return the runtime UUID value held by a typed user identifier."""

    return UUID(str(user_id))


def _public_user_from_model(user: User) -> PublicUser:
    """Build a public user DTO without exposing the stored password hash."""

    return PublicUser(
        id=UserID(user.id),
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _current_user_membership_from_models(
    membership: OrganisationMembership,
    organisation: Organisation,
) -> CurrentUserMembership:
    """Build a current-user membership DTO from repository models."""

    return CurrentUserMembership(
        membership_id=MembershipID(membership.id),
        organisation_id=OrganisationID(organisation.id),
        organisation_name=organisation.name,
        organisation_slug=organisation.slug,
        role=membership.role,
    )


__all__ = [
    "AuthAPIService",
    "AuthAPIServiceError",
    "CurrentUser",
    "CurrentUserMembership",
    "EmailAlreadyRegisteredError",
    "InvalidBearerTokenError",
    "InvalidCredentialsError",
    "PublicUser",
]
