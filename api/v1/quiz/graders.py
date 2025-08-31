"""
Grader implementations for different item types.
Provides objective scoring with partial credit support.
"""

import re
from typing import Any


class MCQGrader:
    """Grader for multiple choice questions with exact/partial scoring."""

    def grade(
        self, item_payload: dict[str, Any], response: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Grade MCQ response.

        Args:
            item_payload: MCQ payload with {stem, options, multiple_select?}
            response: User response with {selected_option_ids: [str]}

        Returns:
            {
                "correct": bool,
                "partial": Optional[float],  # 0.0 to 1.0 for partial credit
                "rationale": Optional[str],  # Explanation of scoring
                "normalized_answer": Optional[str]  # Selected option IDs
            }
        """
        selected_ids = set(response.get("selected_option_ids", []))
        options = item_payload["options"]
        multiple_select = item_payload.get("multiple_select", False)

        # Find correct options
        correct_ids = {opt["id"] for opt in options if opt["is_correct"]}

        # Calculate scoring
        if not multiple_select:
            # Single select - exact match required
            is_correct = len(selected_ids) == 1 and selected_ids == correct_ids
            partial_score = 1.0 if is_correct else 0.0
        else:
            # Multiple select - partial credit based on overlap
            if not selected_ids:
                is_correct = False
                partial_score = 0.0
            else:
                true_positives = len(selected_ids.intersection(correct_ids))
                false_positives = len(selected_ids - correct_ids)
                false_negatives = len(correct_ids - selected_ids)

                # Partial credit: TP / (TP + FP + FN)
                total_errors = false_positives + false_negatives
                if total_errors == 0:
                    partial_score = 1.0
                    is_correct = True
                else:
                    partial_score = max(
                        0.0, true_positives / (true_positives + total_errors)
                    )
                    is_correct = partial_score >= 1.0

        # Generate rationale from selected options
        rationale_parts = []
        for option in options:
            if option["id"] in selected_ids:
                status = "✓" if option["is_correct"] else "✗"
                rationale_parts.append(f"{status} {option['id']}: {option['text']}")
                if option.get("rationale"):
                    rationale_parts.append(f"  → {option['rationale']}")

        rationale = (
            "\n".join(rationale_parts) if rationale_parts else "No options selected"
        )

        return {
            "correct": is_correct,
            "partial": partial_score if partial_score < 1.0 else None,
            "rationale": rationale,
            "normalized_answer": sorted(selected_ids),
        }


class ClozeGrader:
    """Grader for cloze deletion with multi-blank partial credit."""

    def grade(
        self, item_payload: dict[str, Any], response: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Grade cloze deletion response.

        Args:
            item_payload: Cloze payload with {text, blanks, context_note?}
            response: User response with {blank_answers: {blank_id: str}}

        Returns:
            {
                "correct": bool,
                "partial": Optional[float],
                "rationale": Optional[str],
                "normalized_answer": dict  # Normalized answers per blank
            }
        """
        blank_answers = response.get("blank_answers", {})
        blanks = item_payload["blanks"]

        correct_count = 0
        total_blanks = len(blanks)
        normalized_answers = {}
        rationale_parts = []

        for blank in blanks:
            blank_id = blank["id"]
            user_answer = blank_answers.get(blank_id, "").strip()

            # Normalize user answer
            if not blank.get("case_sensitive", False):
                user_answer_norm = user_answer.lower()
            else:
                user_answer_norm = user_answer

            normalized_answers[blank_id] = user_answer

            # Check against acceptable answers
            acceptable = blank["answers"]
            alt_acceptable = blank.get("alt_answers", [])
            all_acceptable = acceptable + (alt_acceptable or [])

            # Normalize acceptable answers
            if not blank.get("case_sensitive", False):
                all_acceptable_norm = [ans.lower().strip() for ans in all_acceptable]
            else:
                all_acceptable_norm = [ans.strip() for ans in all_acceptable]

            is_blank_correct = user_answer_norm in all_acceptable_norm
            if is_blank_correct:
                correct_count += 1
                rationale_parts.append(f"✓ {blank_id}: '{user_answer}' (correct)")
            else:
                expected = "/".join(acceptable[:3])  # Show first 3 expected answers
                rationale_parts.append(
                    f"✗ {blank_id}: '{user_answer}' (expected: {expected})"
                )

        # Calculate partial score
        partial_score = correct_count / total_blanks if total_blanks > 0 else 0.0
        is_correct = partial_score >= 1.0

        rationale = "\n".join(rationale_parts)

        return {
            "correct": is_correct,
            "partial": partial_score if partial_score < 1.0 else None,
            "rationale": rationale,
            "normalized_answer": normalized_answers,
        }


class ShortAnswerGrader:
    """Grader for short answer questions with regex and numeric tolerance."""

    def grade(
        self, item_payload: dict[str, Any], response: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Grade short answer response.

        Args:
            item_payload: Short answer payload with {prompt, expected, acceptable_patterns?, grading}
            response: User response with {answer: str}

        Returns:
            {
                "correct": bool,
                "partial": Optional[float],
                "rationale": Optional[str],
                "normalized_answer": str
            }
        """
        user_answer = response.get("answer", "").strip()
        expected = item_payload["expected"]
        grading_method = item_payload["grading"]["method"]
        acceptable_patterns = item_payload.get("acceptable_patterns", [])

        normalized_answer = user_answer
        is_correct = False
        rationale = ""

        if grading_method == "exact":
            expected_value = expected.get("value", "").strip()
            is_correct = user_answer.lower() == expected_value.lower()
            rationale = f"Expected: '{expected_value}', Got: '{user_answer}'"

        elif grading_method == "regex":
            # Check against regex patterns
            for pattern in acceptable_patterns:
                try:
                    if re.match(pattern, user_answer, re.IGNORECASE):
                        is_correct = True
                        break
                except re.error:
                    continue  # Skip invalid regex patterns

            rationale = f"Checked against {len(acceptable_patterns)} pattern(s)"

        elif grading_method == "numeric":
            try:
                # Extract numeric part by taking the first sequence of digits/decimals/commas
                numeric_match = re.search(r"[\d,]+\.?\d*", user_answer.replace(",", ""))
                if not numeric_match:
                    raise ValueError("No numeric value found")

                user_value = float(numeric_match.group())
                expected_value = float(expected.get("value", "0"))

                # 5% tolerance for numeric answers
                tolerance = abs(expected_value * 0.05) if expected_value != 0 else 0.1
                is_correct = abs(user_value - expected_value) <= tolerance

                normalized_answer = str(user_value)
                rationale = (
                    f"Expected: {expected_value} ±{tolerance:.3f}, Got: {user_value}"
                )

                # Check units if provided
                expected_unit = expected.get("unit")
                if expected_unit and is_correct:
                    # Simple unit checking - look for unit in response
                    if expected_unit.lower() not in user_answer.lower():
                        rationale += f" (missing unit: {expected_unit})"
                        is_correct = False

            except (ValueError, TypeError):
                is_correct = False
                rationale = f"Invalid numeric format: '{user_answer}'"

        return {
            "correct": is_correct,
            "partial": None,  # No partial credit for short answers
            "rationale": rationale,
            "normalized_answer": normalized_answer,
        }


class FlashcardGrader:
    """Grader for flashcard items using FSRS rating mapping."""

    def grade(
        self, item_payload: dict[str, Any], response: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Grade flashcard response.

        Args:
            item_payload: Flashcard payload with {front, back, examples?, hints?, pronunciation?}
            response: User response with {rating: int, self_correct?: bool}

        Returns:
            {
                "correct": bool,
                "partial": Optional[float],
                "rationale": Optional[str],
                "normalized_answer": str  # FSRS rating
            }
        """
        rating = response.get("rating", 1)  # Default to "Again" if not provided
        self_correct = response.get("self_correct")

        # FSRS rating mapping: 1=Again, 2=Hard, 3=Good, 4=Easy
        # Convert to correctness for objective scoring
        if self_correct is not None:
            # Use explicit self-assessment if provided
            is_correct = self_correct
        else:
            # Map FSRS rating to correctness: 1-2 = incorrect, 3-4 = correct
            is_correct = rating >= 3

        rating_names = {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}
        rating_name = rating_names.get(rating, "Unknown")

        rationale = f"Self-rated as: {rating_name} ({rating})"
        if self_correct is not None:
            rationale += f", Self-correct: {'Yes' if self_correct else 'No'}"

        return {
            "correct": is_correct,
            "partial": None,  # No partial credit for flashcards
            "rationale": rationale,
            "normalized_answer": str(rating),
        }
