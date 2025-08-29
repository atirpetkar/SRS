from typing import Any

import pytest

from api.v1.core.registries import (
    Registry,
    generator_registry,
    grader_registry,
    importer_registry,
    item_type_registry,
    scheduler_registry,
    vectorizer_registry,
)


class MockItemTypeValidator:
    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    def render(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload


class MockGrader:
    def grade(
        self, item_payload: dict[str, Any], response: dict[str, Any]
    ) -> dict[str, Any]:
        return {"correct": True, "partial": None, "rationale": "Mock grading"}


def test_registry_basic_operations():
    """Test basic registry register, get, list operations."""
    registry = Registry[str]("Test")

    # Test empty registry
    assert registry.list() == []

    # Test register and get
    registry.register("test_impl", "test_value")
    assert registry.get("test_impl") == "test_value"
    assert registry.list() == ["test_impl"]

    # Test KeyError for missing implementation
    with pytest.raises(KeyError, match="No test implementation registered"):
        registry.get("nonexistent")


def test_registry_multiple_implementations():
    """Test registry with multiple implementations."""
    registry = Registry[str]("Test")

    registry.register("impl1", "value1")
    registry.register("impl2", "value2")
    registry.register("impl3", "value3")

    assert set(registry.list()) == {"impl1", "impl2", "impl3"}
    assert registry.get("impl1") == "value1"
    assert registry.get("impl2") == "value2"
    assert registry.get("impl3") == "value3"


def test_item_type_registry():
    """Test item type registry with mock validator."""
    # Register mock validator
    validator = MockItemTypeValidator()
    item_type_registry.register("test_flashcard", validator)

    # Test retrieval
    retrieved = item_type_registry.get("test_flashcard")
    assert retrieved == validator
    assert "test_flashcard" in item_type_registry.list()

    # Test validator methods work
    payload = {"front": "Test", "back": "Answer"}
    assert retrieved.validate(payload) == payload
    assert retrieved.render(payload) == payload


def test_grader_registry():
    """Test grader registry with mock grader."""
    # Register mock grader
    grader = MockGrader()
    grader_registry.register("test_mcq", grader)

    # Test retrieval
    retrieved = grader_registry.get("test_mcq")
    assert retrieved == grader
    assert "test_mcq" in grader_registry.list()

    # Test grader method works
    result = retrieved.grade({}, {"answer": "A"})
    assert result["correct"] is True


def test_all_registries_are_singletons():
    """Test that all registries are properly instantiated as singletons."""
    registries = [
        item_type_registry,
        grader_registry,
        scheduler_registry,
        importer_registry,
        generator_registry,
        vectorizer_registry,
    ]

    for registry in registries:
        assert registry is not None
        assert hasattr(registry, "register")
        assert hasattr(registry, "get")
        assert hasattr(registry, "list")
        assert callable(registry.register)
        assert callable(registry.get)
        assert callable(registry.list)


def test_registry_overwrites_implementation():
    """Test that registering the same name overwrites previous implementation."""
    registry = Registry[str]("Test")

    registry.register("same_name", "first_value")
    assert registry.get("same_name") == "first_value"

    registry.register("same_name", "second_value")
    assert registry.get("same_name") == "second_value"
    assert registry.list() == ["same_name"]  # Only one entry
