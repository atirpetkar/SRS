from unittest.mock import patch

import pytest

from api.config.settings import AuthMode, SchedulerType, Settings, get_settings


def test_default_settings():
    """Test default settings values."""
    settings = Settings()

    assert settings.app_name == "Learning OS"
    assert settings.version == "1.0.0"
    assert settings.environment == "development"
    assert settings.debug is True
    assert settings.auth_mode == AuthMode.NONE
    assert settings.scheduler == SchedulerType.FSRS_LATEST
    assert settings.enable_llm_creator is False


def test_production_validation_blocks_none_auth():
    """Test that production environment blocks AUTH_MODE=none."""
    with pytest.raises(ValueError, match="AUTH_MODE=none is not allowed in production"):
        Settings(environment="production", auth_mode=AuthMode.NONE)


def test_production_validation_blocks_dev_auth():
    """Test that production environment blocks AUTH_MODE=dev."""
    with pytest.raises(ValueError, match="AUTH_MODE=dev is not allowed in production"):
        Settings(environment="production", auth_mode=AuthMode.DEV)


def test_production_allows_oidc_auth():
    """Test that production environment allows AUTH_MODE=oidc."""
    settings = Settings(environment="production", auth_mode=AuthMode.OIDC)
    assert settings.environment == "production"
    assert settings.auth_mode == AuthMode.OIDC


def test_development_allows_all_auth_modes():
    """Test that development environment allows all auth modes."""
    for auth_mode in AuthMode:
        settings = Settings(environment="development", auth_mode=auth_mode)
        assert settings.auth_mode == auth_mode


def test_settings_dependency_injection():
    """Test the get_settings dependency function."""
    settings = get_settings()
    assert isinstance(settings, Settings)
    assert settings.app_name == "Learning OS"


def test_scheduler_type_updated():
    """Test that scheduler type uses FSRS_LATEST."""
    settings = Settings()
    assert settings.scheduler == SchedulerType.FSRS_LATEST
    assert settings.scheduler.value == "fsrs_latest"


@patch.dict("os.environ", {"AUTH_MODE": "oidc", "ENVIRONMENT": "production"})
def test_env_var_loading():
    """Test that environment variables are loaded correctly."""
    settings = Settings()
    assert settings.auth_mode == AuthMode.OIDC
    assert settings.environment == "production"
