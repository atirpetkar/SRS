from dataclasses import dataclass

from fastapi import Depends

from api.config.settings import AuthMode, settings


@dataclass
class Principal:
    """Represents the current authenticated user/context."""

    user_id: str
    org_id: str
    roles: list[str]
    email: str | None = None


async def get_principal() -> Principal:
    """
    Dependency injection function to get the current principal.

    Behavior based on AUTH_MODE:
    - none: Returns dev defaults with admin role
    - dev: TODO (Step 10) - Extract from headers and create users/orgs
    - oidc: TODO (Step 13) - Verify JWT and map to user
    """
    if settings.auth_mode == AuthMode.NONE:
        return Principal(
            user_id=settings.dev_user_id, org_id=settings.dev_org_id, roles=["admin"]
        )
    elif settings.auth_mode == AuthMode.DEV:
        # TODO: Step 10 - Extract X-User-ID, X-Org-ID headers
        raise NotImplementedError("Dev auth mode not implemented yet")
    elif settings.auth_mode == AuthMode.OIDC:
        # TODO: Step 13 - Verify JWT token and map to user
        raise NotImplementedError("OIDC auth mode not implemented yet")
    else:
        raise ValueError(f"Unknown auth mode: {settings.auth_mode}")


# Convenience type alias for dependency injection
PrincipalDep = Depends(get_principal)
