from dataclasses import dataclass
from uuid import NAMESPACE_DNS, UUID, uuid5

from fastapi import Depends, Header, HTTPException, status

from api.config.settings import AuthMode, settings


def string_to_uuid(text: str) -> UUID:
    """Convert a string to a deterministic UUID using namespace DNS."""
    return uuid5(NAMESPACE_DNS, text)


@dataclass
class Principal:
    """Represents the current authenticated user/context."""

    user_id: str
    org_id: str
    roles: list[str]
    email: str | None = None

    @property
    def user_uuid(self) -> UUID:
        """Get the user ID as a UUID for database operations."""
        return string_to_uuid(self.user_id)

    @property
    def org_uuid(self) -> UUID:
        """Get the org ID as a UUID for database operations."""
        return string_to_uuid(self.org_id)


async def get_principal(
    x_user_id: str | None = Header(None, alias="X-User-ID"),
    x_org_id: str | None = Header(None, alias="X-Org-ID"),
) -> Principal:
    """
    Dependency injection function to get the current principal.

    Behavior based on AUTH_MODE:
    - none: Returns dev defaults with admin role
    - dev: Extract from headers and create users/orgs on first sight
    - oidc: TODO (Step 13) - Verify JWT and map to user
    """
    if settings.auth_mode == AuthMode.NONE:
        return Principal(
            user_id=settings.dev_user_id, org_id=settings.dev_org_id, roles=["admin"]
        )
    elif settings.auth_mode == AuthMode.DEV:
        # Require headers in dev mode
        if x_user_id is None or x_org_id is None or not x_user_id or not x_org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-User-ID and X-Org-ID headers are required in dev auth mode",
            )

        return Principal(
            user_id=x_user_id,
            org_id=x_org_id,
            roles=["admin"],  # Default role in dev mode
        )
    elif settings.auth_mode == AuthMode.OIDC:
        # TODO: Step 13 - Verify JWT token and map to user
        raise NotImplementedError("OIDC auth mode not implemented yet")
    else:
        raise ValueError(f"Unknown auth mode: {settings.auth_mode}")


# Convenience type alias for dependency injection
PrincipalDep = Depends(get_principal)
