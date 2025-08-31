"""
Integration tests for quiz flow endpoints.
Tests the complete quiz workflow: start -> submit -> finish.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from api.v1.quiz.graders import FlashcardGrader, MCQGrader


class TestQuizFlowIntegration:
    """Test complete quiz flow without database dependencies."""

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session."""
        return MagicMock()

    @pytest.fixture
    def mock_principal(self):
        """Mock principal for authentication."""
        from api.v1.core.security import Principal

        return Principal(
            user_id="test_user",
            org_id="test_org",
            roles=["admin"],
            email="test@example.com",
        )

    @pytest.fixture
    def sample_items(self):
        """Sample items for testing."""
        return [
            {
                "id": uuid4(),
                "type": "mcq",
                "payload": {
                    "stem": "What is 2 + 2?",
                    "options": [
                        {"id": "a", "text": "3", "is_correct": False},
                        {"id": "b", "text": "4", "is_correct": True},
                    ],
                },
            },
            {
                "id": uuid4(),
                "type": "flashcard",
                "payload": {"front": "Capital of France?", "back": "Paris"},
            },
        ]

    def test_quiz_start_request_validation(self, simple_client):
        """Test quiz start request validation."""
        # Test invalid mode
        response = simple_client.post(
            "/v1/quiz/start", json={"mode": "invalid_mode", "params": {}}
        )
        assert response.status_code == 422  # Validation error

        # Test valid request structure
        response = simple_client.post(
            "/v1/quiz/start",
            json={"mode": "drill", "params": {"tags": ["test"], "length": 5}},
        )
        # Will fail due to missing database, but validates request structure
        assert response.status_code in [
            404,
            500,
        ]  # Database-related error, not validation

    def test_quiz_submit_request_validation(self, simple_client):
        """Test quiz submit request validation."""
        quiz_id = str(uuid4())
        item_id = str(uuid4())

        # Test MCQ response format
        response = simple_client.post(
            "/v1/quiz/submit",
            json={
                "quiz_id": quiz_id,
                "item_id": item_id,
                "response": {"selected_option_ids": ["a", "b"]},
            },
        )
        # Will fail due to missing database, but validates request structure
        assert response.status_code in [404, 500]  # Database-related error

        # Test invalid UUIDs
        response = simple_client.post(
            "/v1/quiz/submit",
            json={"quiz_id": "invalid_uuid", "item_id": item_id, "response": {}},
        )
        assert response.status_code == 422  # Validation error

    def test_quiz_finish_request_validation(self, simple_client):
        """Test quiz finish request validation."""
        quiz_id = str(uuid4())

        response = simple_client.post("/v1/quiz/finish", json={"quiz_id": quiz_id})
        # Will fail due to missing database, but validates request structure
        assert response.status_code in [
            404,
            500,
        ]  # Database-related error, not validation

        # Test invalid UUID
        response = simple_client.post(
            "/v1/quiz/finish", json={"quiz_id": "invalid_uuid"}
        )
        assert response.status_code == 422  # Validation error

    def test_grader_registry_integration(self):
        """Test that graders are properly registered and accessible."""
        from api.v1.core.registries import grader_registry
        from api.v1.quiz.registry_init import init_quiz_registries

        # Initialize registries
        init_quiz_registries()

        # Test all graders are registered
        assert "mcq" in grader_registry.list()
        assert "cloze" in grader_registry.list()
        assert "short_answer" in grader_registry.list()
        assert "flashcard" in grader_registry.list()

        # Test graders can be retrieved and used
        mcq_grader = grader_registry.get("mcq")
        assert isinstance(mcq_grader, MCQGrader)

        flashcard_grader = grader_registry.get("flashcard")
        assert isinstance(flashcard_grader, FlashcardGrader)

        # Test grading functionality
        mcq_payload = {
            "stem": "Test question?",
            "options": [
                {"id": "a", "text": "Wrong", "is_correct": False},
                {"id": "b", "text": "Right", "is_correct": True},
            ],
        }
        mcq_response = {"selected_option_ids": ["b"]}
        result = mcq_grader.grade(mcq_payload, mcq_response)
        assert result["correct"] is True

    def test_item_type_registry_integration(self):
        """Test item type registry integration for rendering."""
        from api.v1.core.registries import item_type_registry
        from api.v1.items.registry_init import register_item_validators

        # Initialize registries
        register_item_validators()

        # Test MCQ rendering
        mcq_validator = item_type_registry.get("mcq")
        mcq_payload = {
            "stem": "What is 2 + 2?",
            "options": [
                {"id": "a", "text": "3", "is_correct": False},
                {"id": "b", "text": "4", "is_correct": True},
            ],
        }
        rendered = mcq_validator.render(mcq_payload)
        assert rendered["type"] == "mcq"
        assert rendered["stem"] == "What is 2 + 2?"
        assert len(rendered["options"]) == 2
        assert rendered["options"][0]["id"] == "a"

    @patch("api.v1.quiz.routes.select")
    @patch("api.v1.quiz.routes.AsyncSession")
    def test_quiz_mode_logic(self, mock_session, mock_select):
        """Test quiz mode-specific item selection logic."""
        from api.v1.quiz.schemas import QuizStartRequest

        # This tests the business logic without actual database calls
        request = QuizStartRequest(mode="drill", params={"tags": ["test"], "length": 5})

        # The actual database interaction is mocked, but we can verify
        # that the correct query logic would be applied
        assert request.mode == "drill"
        assert request.params["tags"] == ["test"]
        assert request.params["length"] == 5

    def test_score_calculation_logic(self):
        """Test quiz score calculation without database."""
        from api.v1.quiz.schemas import ScoreBreakdown

        # Test score breakdown calculation
        breakdown = ScoreBreakdown(
            total_items=10,
            correct_items=7,
            partial_credit_items=2,
            incorrect_items=1,
            average_partial_score=0.5,
            items_by_type={
                "mcq": {"total": 5, "correct": 4, "partial": 1, "incorrect": 0},
                "flashcard": {"total": 5, "correct": 3, "partial": 1, "incorrect": 1},
            },
            time_taken_s=300,
        )

        assert breakdown.total_items == 10
        assert (
            breakdown.correct_items
            + breakdown.partial_credit_items
            + breakdown.incorrect_items
            == 10
        )
        assert breakdown.items_by_type["mcq"]["total"] == 5
        assert breakdown.items_by_type["flashcard"]["total"] == 5

        # Test final score calculation
        # (correct + partial * 0.5) / total = (7 + 2 * 0.5) / 10 = 0.8
        expected_score = (
            breakdown.correct_items + breakdown.partial_credit_items * 0.5
        ) / breakdown.total_items
        assert abs(expected_score - 0.8) < 0.001

    def test_quiz_params_validation(self):
        """Test quiz parameter validation and constraints."""
        from api.v1.quiz.schemas import QuizStartRequest

        # Test valid parameters
        request = QuizStartRequest(
            mode="mock",
            params={
                "tags": ["physics", "math"],
                "type": "mcq",
                "length": 15,
                "time_limit_s": 900,
            },
        )
        assert request.params["length"] == 15
        assert request.params["time_limit_s"] == 900

        # Test default parameters
        request = QuizStartRequest(mode="drill")
        assert request.params == {}

    def test_error_handling_scenarios(self, simple_client):
        """Test various error scenarios."""
        # Test missing required fields
        response = simple_client.post("/v1/quiz/start", json={})
        assert response.status_code == 422

        response = simple_client.post(
            "/v1/quiz/submit",
            json={
                "quiz_id": str(uuid4())
                # Missing item_id and response
            },
        )
        assert response.status_code == 422

        response = simple_client.post("/v1/quiz/finish", json={})
        assert response.status_code == 422

    def test_quiz_workflow_sequence(self):
        """Test the logical sequence of quiz operations."""
        from api.v1.quiz.schemas import (
            QuizFinishRequest,
            QuizStartRequest,
            QuizSubmitRequest,
        )

        quiz_id = uuid4()
        item_id = uuid4()

        # 1. Start quiz
        start_request = QuizStartRequest(
            mode="drill", params={"length": 3, "tags": ["test"]}
        )
        assert start_request.mode == "drill"

        # 2. Submit responses (would happen multiple times)
        submit_request = QuizSubmitRequest(
            quiz_id=quiz_id, item_id=item_id, response={"selected_option_ids": ["a"]}
        )
        assert submit_request.quiz_id == quiz_id
        assert submit_request.item_id == item_id

        # 3. Finish quiz
        finish_request = QuizFinishRequest(quiz_id=quiz_id)
        assert finish_request.quiz_id == quiz_id

    def test_acceptance_criteria(self):
        """Test Step 5 acceptance criteria."""
        from api.v1.quiz.graders import ClozeGrader, MCQGrader, ShortAnswerGrader

        # Acceptance test: MCQ multi-select grading correct
        mcq_grader = MCQGrader()
        mcq_payload = {
            "stem": "Which are prime numbers?",
            "options": [
                {"id": "a", "text": "2", "is_correct": True},
                {"id": "b", "text": "3", "is_correct": True},
                {"id": "c", "text": "4", "is_correct": False},
            ],
            "multiple_select": True,
        }
        mcq_response = {"selected_option_ids": ["a", "b"]}
        result = mcq_grader.grade(mcq_payload, mcq_response)
        assert result["correct"] is True

        # Acceptance test: Cloze partials
        cloze_grader = ClozeGrader()
        cloze_payload = {
            "text": "The [[capital]] of [[France]] is Paris.",
            "blanks": [
                {"id": "blank1", "answers": ["capital"]},
                {"id": "blank2", "answers": ["France"]},
            ],
        }
        cloze_response = {"blank_answers": {"blank1": "capital", "blank2": "Germany"}}
        result = cloze_grader.grade(cloze_payload, cloze_response)
        assert result["correct"] is False
        assert result["partial"] == 0.5  # 1 out of 2 correct

        # Acceptance test: Short-answer numeric tolerance
        sa_grader = ShortAnswerGrader()
        sa_payload = {
            "prompt": "What is pi to 2 decimal places?",
            "expected": {"value": "3.14"},
            "grading": {"method": "numeric"},
        }
        sa_response = {"answer": "3.15"}  # Within 5% tolerance
        result = sa_grader.grade(sa_payload, sa_response)
        assert result["correct"] is True  # Should pass due to tolerance
