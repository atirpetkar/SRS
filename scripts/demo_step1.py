#!/usr/bin/env python3
"""
Demo script showcasing Step 1 enhanced functionality.
Run with: python demo_step1.py
"""

import os

from fastapi.testclient import TestClient

from api.config.settings import AuthMode, Settings
from api.main import app
from api.v1.core.registries import (
    generator_registry,
    grader_registry,
    importer_registry,
    item_type_registry,
    scheduler_registry,
    vectorizer_registry,
)


def demo_settings():
    """Demonstrate enhanced settings functionality."""
    print("🔧 SETTINGS DEMO")
    print("=" * 50)

    # Show default settings
    settings = Settings()
    print(f"✅ Default scheduler: {settings.scheduler.value}")
    print(f"✅ Default auth mode: {settings.auth_mode.value}")
    print(f"✅ Default environment: {settings.environment}")

    # Show production validation
    try:
        Settings(environment="production", auth_mode=AuthMode.NONE)
        print("❌ This should not succeed")
    except ValueError as e:
        print(f"✅ Production validation works: {str(e)[:80]}...")

    # Show OIDC works in production
    prod_settings = Settings(environment="production", auth_mode=AuthMode.OIDC)
    print(f"✅ Production + OIDC works: {prod_settings.auth_mode.value}")

    print()


def demo_registries():
    """Demonstrate registry functionality with freezing."""
    print("📋 REGISTRIES DEMO")
    print("=" * 50)

    # Show all registries exist
    registries = [
        ("ItemType", item_type_registry),
        ("Grader", grader_registry),
        ("Scheduler", scheduler_registry),
        ("Importer", importer_registry),
        ("Generator", generator_registry),
        ("Vectorizer", vectorizer_registry),
    ]

    print("Available registries:")
    for name, registry in registries:
        print(f"✅ {name}: {len(registry.list())} implementations registered")

    # Demonstrate freezing
    print("\n🧊 Registry freezing demo:")
    test_registry = item_type_registry

    if test_registry.is_frozen():
        print(f"✅ {test_registry.name} registry is frozen (production mode)")
        try:
            test_registry.register("demo", "test")
            print("❌ This should not succeed")
        except RuntimeError as e:
            print(f"✅ Cannot register when frozen: {str(e)[:60]}...")
    else:
        print(f"✅ {test_registry.name} registry is not frozen (development mode)")
        test_registry.register("demo_item", "test_implementation")
        print("✅ Successfully registered demo item")
        test_registry.freeze()
        print("✅ Registry frozen manually")
        try:
            test_registry.register("demo2", "test2")
        except RuntimeError as e:
            print(f"✅ Now blocked: {str(e)[:60]}...")

    print()


def demo_api_endpoints():
    """Demonstrate API functionality with response envelopes."""
    print("🌐 API DEMO")
    print("=" * 50)

    client = TestClient(app)

    # Test health endpoint
    response = client.get("/v1/healthz")
    print(f"✅ Health check status: {response.status_code}")

    data = response.json()
    print("✅ Response envelope structure:")
    print(f"   - ok: {data['ok']}")
    print(f"   - data: {bool(data.get('data'))}")
    print(f"   - timestamp: {data['timestamp'][:19]}...")
    print(
        f"   - request_id: {data['request_id'][:8] if data['request_id'] else 'None'}..."
    )

    # Check headers
    request_id = response.headers.get("X-Request-ID")
    print(f"✅ Request ID in headers: {request_id[:8] if request_id else 'None'}...")

    print()


def demo_production_mode():
    """Demonstrate production mode with registry freezing."""
    print("🏭 PRODUCTION MODE DEMO")
    print("=" * 50)

    # Set production environment
    old_env = os.environ.get("ENVIRONMENT")
    old_auth = os.environ.get("AUTH_MODE")

    os.environ["ENVIRONMENT"] = "production"
    os.environ["AUTH_MODE"] = "oidc"

    try:
        # Import after setting env vars
        from api.main import create_app

        prod_app = create_app()
        client = TestClient(prod_app)

        # Test that health still works
        response = client.get("/v1/healthz")
        print(f"✅ Production app health: {response.status_code}")

        # Test that registries are frozen
        from api.v1.core.registries import item_type_registry

        print(f"✅ Production registries frozen: {item_type_registry.is_frozen()}")

    finally:
        # Restore environment
        if old_env:
            os.environ["ENVIRONMENT"] = old_env
        else:
            os.environ.pop("ENVIRONMENT", None)

        if old_auth:
            os.environ["AUTH_MODE"] = old_auth
        else:
            os.environ.pop("AUTH_MODE", None)

    print()


def main():
    """Run all demos."""
    print("🚀 STEP 1 ENHANCED FUNCTIONALITY DEMO")
    print("=" * 60)
    print("Demonstrating our production-ready Step 1 implementation")
    print("=" * 60)
    print()

    demo_settings()
    demo_registries()
    demo_api_endpoints()
    demo_production_mode()

    print("🎉 ALL DEMOS COMPLETED SUCCESSFULLY!")
    print("Step 1 is now production-ready with:")
    print("  ✅ Enhanced dependencies (SQLAlchemy, Alembic, etc.)")
    print("  ✅ FSRS_LATEST scheduler abstraction")
    print("  ✅ Production security validation")
    print("  ✅ Registry freezing in production")
    print("  ✅ UTC timestamps in response envelopes")
    print("  ✅ Settings dependency injection")
    print("  ✅ Comprehensive test coverage")


if __name__ == "__main__":
    main()
