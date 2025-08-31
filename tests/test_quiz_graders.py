"""
Unit tests for quiz grader implementations.
Tests the core grading logic for all item types.
"""

from api.v1.quiz.graders import (
    ClozeGrader,
    FlashcardGrader,
    MCQGrader,
    ShortAnswerGrader,
)


class TestMCQGrader:
    """Test MCQ grader implementation."""

    def test_single_select_correct(self):
        """Test single select MCQ with correct answer."""
        grader = MCQGrader()
        payload = {
            "stem": "What is 2 + 2?",
            "options": [
                {"id": "a", "text": "3", "is_correct": False},
                {
                    "id": "b",
                    "text": "4",
                    "is_correct": True,
                    "rationale": "Correct addition",
                },
                {"id": "c", "text": "5", "is_correct": False},
            ],
            "multiple_select": False,
        }
        response = {"selected_option_ids": ["b"]}

        result = grader.grade(payload, response)

        assert result["correct"] is True
        assert result["partial"] is None
        assert "✓ b: 4" in result["rationale"]
        assert "Correct addition" in result["rationale"]
        assert result["normalized_answer"] == ["b"]

    def test_single_select_incorrect(self):
        """Test single select MCQ with incorrect answer."""
        grader = MCQGrader()
        payload = {
            "stem": "What is 2 + 2?",
            "options": [
                {"id": "a", "text": "3", "is_correct": False, "rationale": "Too low"},
                {"id": "b", "text": "4", "is_correct": True},
                {"id": "c", "text": "5", "is_correct": False},
            ],
            "multiple_select": False,
        }
        response = {"selected_option_ids": ["a"]}

        result = grader.grade(payload, response)

        assert result["correct"] is False
        assert result["partial"] == 0.0
        assert "✗ a: 3" in result["rationale"]
        assert "Too low" in result["rationale"]
        assert result["normalized_answer"] == ["a"]

    def test_multiple_select_perfect(self):
        """Test multiple select MCQ with perfect answer."""
        grader = MCQGrader()
        payload = {
            "stem": "Which are prime numbers?",
            "options": [
                {"id": "a", "text": "2", "is_correct": True},
                {"id": "b", "text": "3", "is_correct": True},
                {"id": "c", "text": "4", "is_correct": False},
                {"id": "d", "text": "5", "is_correct": True},
            ],
            "multiple_select": True,
        }
        response = {"selected_option_ids": ["a", "b", "d"]}

        result = grader.grade(payload, response)

        assert result["correct"] is True
        assert result["partial"] is None
        assert "✓ a: 2" in result["rationale"]
        assert "✓ b: 3" in result["rationale"]
        assert "✓ d: 5" in result["rationale"]

    def test_multiple_select_partial(self):
        """Test multiple select MCQ with partial credit."""
        grader = MCQGrader()
        payload = {
            "stem": "Which are prime numbers?",
            "options": [
                {"id": "a", "text": "2", "is_correct": True},
                {"id": "b", "text": "3", "is_correct": True},
                {"id": "c", "text": "4", "is_correct": False},
                {"id": "d", "text": "5", "is_correct": True},
            ],
            "multiple_select": True,
        }
        # Select 2 correct + 1 incorrect, missing 1 correct
        # TP=2, FP=1, FN=1 -> score = 2/(2+1+1) = 0.5
        response = {"selected_option_ids": ["a", "b", "c"]}

        result = grader.grade(payload, response)

        assert result["correct"] is False
        assert result["partial"] == 0.5
        assert "✓ a: 2" in result["rationale"]
        assert "✓ b: 3" in result["rationale"]
        assert "✗ c: 4" in result["rationale"]

    def test_no_selection(self):
        """Test MCQ with no options selected."""
        grader = MCQGrader()
        payload = {
            "stem": "What is 2 + 2?",
            "options": [
                {"id": "a", "text": "3", "is_correct": False},
                {"id": "b", "text": "4", "is_correct": True},
            ],
            "multiple_select": False,
        }
        response = {"selected_option_ids": []}

        result = grader.grade(payload, response)

        assert result["correct"] is False
        assert result["rationale"] == "No options selected"


class TestClozeGrader:
    """Test Cloze grader implementation."""

    def test_single_blank_correct(self):
        """Test cloze with single blank, correct answer."""
        grader = ClozeGrader()
        payload = {
            "text": "The capital of France is [[Paris]]",
            "blanks": [{"id": "blank1", "answers": ["Paris"], "case_sensitive": False}],
        }
        response = {"blank_answers": {"blank1": "paris"}}

        result = grader.grade(payload, response)

        assert result["correct"] is True
        assert result["partial"] is None
        assert "✓ blank1: 'paris' (correct)" in result["rationale"]
        assert result["normalized_answer"] == {"blank1": "paris"}

    def test_multiple_blanks_partial(self):
        """Test cloze with multiple blanks, partial credit."""
        grader = ClozeGrader()
        payload = {
            "text": "The capital of [[France]] is [[Paris]]",
            "blanks": [
                {"id": "blank1", "answers": ["France"], "case_sensitive": False},
                {"id": "blank2", "answers": ["Paris"], "case_sensitive": False},
            ],
        }
        response = {"blank_answers": {"blank1": "France", "blank2": "London"}}

        result = grader.grade(payload, response)

        assert result["correct"] is False
        assert result["partial"] == 0.5  # 1 out of 2 correct
        assert "✓ blank1: 'France' (correct)" in result["rationale"]
        assert "✗ blank2: 'London' (expected: Paris)" in result["rationale"]

    def test_alternative_answers(self):
        """Test cloze with alternative acceptable answers."""
        grader = ClozeGrader()
        payload = {
            "text": "The color is [[red]]",
            "blanks": [
                {
                    "id": "blank1",
                    "answers": ["red"],
                    "alt_answers": ["crimson", "scarlet"],
                    "case_sensitive": False,
                }
            ],
        }
        response = {"blank_answers": {"blank1": "crimson"}}

        result = grader.grade(payload, response)

        assert result["correct"] is True
        assert result["partial"] is None
        assert "✓ blank1: 'crimson' (correct)" in result["rationale"]

    def test_case_sensitive(self):
        """Test case sensitive cloze grading."""
        grader = ClozeGrader()
        payload = {
            "text": "The name is [[John]]",
            "blanks": [{"id": "blank1", "answers": ["John"], "case_sensitive": True}],
        }
        response = {"blank_answers": {"blank1": "john"}}

        result = grader.grade(payload, response)

        assert result["correct"] is False
        assert result["partial"] == 0.0
        assert "✗ blank1: 'john' (expected: John)" in result["rationale"]

    def test_empty_response(self):
        """Test cloze with empty response."""
        grader = ClozeGrader()
        payload = {
            "text": "The capital is [[Paris]]",
            "blanks": [{"id": "blank1", "answers": ["Paris"], "case_sensitive": False}],
        }
        response = {"blank_answers": {}}

        result = grader.grade(payload, response)

        assert result["correct"] is False
        assert result["partial"] == 0.0
        assert "✗ blank1: '' (expected: Paris)" in result["rationale"]


class TestShortAnswerGrader:
    """Test Short Answer grader implementation."""

    def test_exact_match_correct(self):
        """Test exact match grading with correct answer."""
        grader = ShortAnswerGrader()
        payload = {
            "prompt": "What is the capital of France?",
            "expected": {"value": "Paris"},
            "grading": {"method": "exact"},
        }
        response = {"answer": "paris"}

        result = grader.grade(payload, response)

        assert result["correct"] is True
        assert result["partial"] is None
        assert "Expected: 'Paris', Got: 'paris'" in result["rationale"]

    def test_numeric_with_tolerance(self):
        """Test numeric grading with tolerance."""
        grader = ShortAnswerGrader()
        payload = {
            "prompt": "What is 10 * 3.14?",
            "expected": {"value": "31.4", "unit": "units"},
            "grading": {"method": "numeric"},
        }
        response = {"answer": "31.5 units"}  # Within 5% tolerance

        result = grader.grade(payload, response)

        assert result["correct"] is True
        assert result["partial"] is None
        assert "31.4" in result["rationale"]
        assert "31.5" in result["rationale"]

    def test_numeric_missing_unit(self):
        """Test numeric grading with missing unit."""
        grader = ShortAnswerGrader()
        payload = {
            "prompt": "What is the distance?",
            "expected": {"value": "100", "unit": "meters"},
            "grading": {"method": "numeric"},
        }
        response = {"answer": "100"}  # Missing unit

        result = grader.grade(payload, response)

        assert result["correct"] is False
        assert result["partial"] is None
        assert "missing unit: meters" in result["rationale"]

    def test_regex_pattern_match(self):
        """Test regex pattern matching."""
        grader = ShortAnswerGrader()
        payload = {
            "prompt": "Enter an email address",
            "expected": {"value": ""},
            "acceptable_patterns": [r"^[\w\.-]+@[\w\.-]+\.\w+$"],
            "grading": {"method": "regex"},
        }
        response = {"answer": "test@example.com"}

        result = grader.grade(payload, response)

        assert result["correct"] is True
        assert result["partial"] is None
        assert "Checked against 1 pattern(s)" in result["rationale"]

    def test_invalid_numeric_format(self):
        """Test invalid numeric input."""
        grader = ShortAnswerGrader()
        payload = {
            "prompt": "What is 2 + 2?",
            "expected": {"value": "4"},
            "grading": {"method": "numeric"},
        }
        response = {"answer": "not a number"}

        result = grader.grade(payload, response)

        assert result["correct"] is False
        assert result["partial"] is None
        assert "Invalid numeric format" in result["rationale"]


class TestFlashcardGrader:
    """Test Flashcard grader implementation."""

    def test_rating_good(self):
        """Test flashcard with 'Good' rating."""
        grader = FlashcardGrader()
        payload = {"front": "What is the capital of France?", "back": "Paris"}
        response = {"rating": 3}  # Good

        result = grader.grade(payload, response)

        assert result["correct"] is True
        assert result["partial"] is None
        assert "Self-rated as: Good (3)" in result["rationale"]
        assert result["normalized_answer"] == "3"

    def test_rating_again(self):
        """Test flashcard with 'Again' rating."""
        grader = FlashcardGrader()
        payload = {"front": "Difficult question", "back": "Complex answer"}
        response = {"rating": 1}  # Again

        result = grader.grade(payload, response)

        assert result["correct"] is False
        assert result["partial"] is None
        assert "Self-rated as: Again (1)" in result["rationale"]
        assert result["normalized_answer"] == "1"

    def test_explicit_self_correct_override(self):
        """Test explicit self-correct override."""
        grader = FlashcardGrader()
        payload = {"front": "Question", "back": "Answer"}
        response = {
            "rating": 1,
            "self_correct": True,
        }  # Low rating but explicit correct

        result = grader.grade(payload, response)

        assert result["correct"] is True  # Overridden by self_correct
        assert result["partial"] is None
        assert "Self-rated as: Again (1)" in result["rationale"]
        assert "Self-correct: Yes" in result["rationale"]

    def test_all_rating_levels(self):
        """Test all FSRS rating levels."""
        grader = FlashcardGrader()
        payload = {"front": "Q", "back": "A"}

        # Test each rating level
        test_cases = [
            (1, "Again", False),
            (2, "Hard", False),
            (3, "Good", True),
            (4, "Easy", True),
        ]

        for rating, name, expected_correct in test_cases:
            response = {"rating": rating}
            result = grader.grade(payload, response)

            assert result["correct"] is expected_correct
            assert f"Self-rated as: {name} ({rating})" in result["rationale"]
            assert result["normalized_answer"] == str(rating)

    def test_default_rating(self):
        """Test default rating when not provided."""
        grader = FlashcardGrader()
        payload = {"front": "Q", "back": "A"}
        response = {}  # No rating provided

        result = grader.grade(payload, response)

        assert result["correct"] is False  # Default rating 1 = Again
        assert result["normalized_answer"] == "1"
