"""
Basic rules generator for educational content creation.

Implements rule-based content generation using NLP techniques without external APIs.
Generates flashcards, MCQs, cloze tests, and short-answer questions from input text.
"""

import hashlib
import random
import re
from typing import Any

import spacy
from spacy.tokens import Doc, Span

from api.v1.core.registries import Generator


class BasicRulesGenerator(Generator):
    """
    Rule-based content generator using spaCy for NLP processing.

    Generates educational items from text input using deterministic rules:
    - Keypoints → flashcards (definitions, term↔value)
    - Numeric facts → MCQ with heuristic distractors
    - Sentences → cloze (mask salient nouns/numbers)
    - Procedures/formulae → short-answer questions
    """

    def __init__(self):
        """Initialize the generator with spaCy English model."""
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError as e:
            raise RuntimeError(
                "spaCy English model not found. Install with: "
                "uv pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
            ) from e

        # Configure pipeline for better performance
        self.nlp.max_length = 10000000  # Allow longer texts

        # Common academic/educational keywords for keypoint detection
        self.definition_markers = {
            "is",
            "are",
            "means",
            "refers to",
            "defined as",
            "known as",
            "called",
            "termed",
            "denotes",
            "represents",
            "signifies",
        }

        # Mathematical operation patterns for formula detection
        self.formula_patterns = [
            r"[A-Za-z]\s*[=]\s*[A-Za-z0-9\+\-\*/\(\)\^\s]+",
            r"\b\w+\s*=\s*[\d\w\+\-\*/\(\)\^\s]+",
            r"formula\s*:?\s*.+",
            r"equation\s*:?\s*.+",
        ]

        # Units for numeric fact generation
        self.common_units = {
            "time": [
                "seconds",
                "minutes",
                "hours",
                "days",
                "years",
                "ms",
                "s",
                "min",
                "hr",
            ],
            "distance": [
                "meters",
                "kilometers",
                "feet",
                "miles",
                "cm",
                "mm",
                "m",
                "km",
                "ft",
                "mi",
            ],
            "mass": ["grams", "kilograms", "pounds", "ounces", "g", "kg", "lb", "oz"],
            "temperature": ["celsius", "fahrenheit", "kelvin", "°C", "°F", "K"],
            "currency": ["dollars", "euros", "pounds", "$", "€", "£"],
            "percentage": ["%", "percent", "percentage"],
        }

    def generate(
        self,
        text: str,
        item_types: list[str] | None = None,
        count: int | None = None,
        difficulty: str | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """
        Generate educational items from input text.

        Args:
            text: Input text to generate items from
            item_types: List of item types to generate (flashcard, mcq, cloze, short_answer)
            count: Target number of items to generate
            difficulty: Difficulty level (intro, core, stretch)
            **kwargs: Additional generation parameters

        Returns:
            List of generated items with metadata
        """
        if not text or len(text.strip()) < 50:
            return []

        # Set defaults
        if item_types is None:
            item_types = ["flashcard", "mcq", "cloze", "short_answer"]
        if count is None:
            count = max(
                12, min(20, len(text) // 50)
            )  # Adaptive count based on text length
        if difficulty is None:
            difficulty = "core"

        # Process text with spaCy
        doc = self.nlp(text)

        # Extract different types of content
        keypoints = self._extract_keypoints(doc)
        numeric_facts = self._extract_numeric_facts(doc)
        sentences = list(doc.sents)
        procedures = self._extract_procedures(doc)

        # Generate items for each type
        generated_items = []

        # Generate flashcards from keypoints
        if "flashcard" in item_types and keypoints:
            flashcards = self._generate_flashcards(keypoints, difficulty, count // 4)
            generated_items.extend(flashcards)

        # Generate MCQs from numeric facts
        if "mcq" in item_types and numeric_facts:
            mcqs = self._generate_mcqs(numeric_facts, difficulty, count // 4)
            generated_items.extend(mcqs)

        # Generate cloze questions from sentences
        if "cloze" in item_types and sentences:
            clozes = self._generate_cloze_questions(sentences, difficulty, count // 4)
            generated_items.extend(clozes)

        # Generate short-answer questions from procedures
        if "short_answer" in item_types and procedures:
            short_answers = self._generate_short_answers(
                procedures, difficulty, count // 4
            )
            generated_items.extend(short_answers)

        # Apply quality gates and shuffle
        quality_items = self._apply_quality_gates(generated_items)
        random.shuffle(quality_items)

        # Return up to the requested count
        return quality_items[:count]

    def _extract_keypoints(self, doc: Doc) -> list[dict[str, Any]]:
        """Extract keypoints that can become flashcards."""
        keypoints = []

        for sent in doc.sents:
            sent_text = sent.text.strip()
            if len(sent_text) < 10 or len(sent_text) > 200:
                continue

            # Look for definition patterns
            for marker in self.definition_markers:
                if marker in sent_text.lower():
                    # Try to split on the definition marker
                    parts = sent_text.lower().split(marker, 1)
                    if len(parts) == 2:
                        term = parts[0].strip().rstrip(" ,")
                        definition = parts[1].strip()

                        if 3 <= len(term) <= 50 and 10 <= len(definition) <= 150:
                            keypoints.append(
                                {
                                    "term": term.title(),
                                    "definition": definition.capitalize(),
                                    "source_sentence": sent_text,
                                    "confidence": 0.8,
                                }
                            )
                            break

            # Look for colon-based definitions
            if ":" in sent_text and sent_text.count(":") == 1:
                parts = sent_text.split(":", 1)
                if len(parts) == 2:
                    term = parts[0].strip()
                    definition = parts[1].strip()

                    if 3 <= len(term) <= 50 and 10 <= len(definition) <= 150:
                        keypoints.append(
                            {
                                "term": term,
                                "definition": definition,
                                "source_sentence": sent_text,
                                "confidence": 0.9,
                            }
                        )

        return keypoints

    def _extract_numeric_facts(self, doc: Doc) -> list[dict[str, Any]]:
        """Extract numeric facts that can become MCQs."""
        numeric_facts = []

        for sent in doc.sents:
            # Find numbers in the sentence
            numbers = []
            units = []

            for token in sent:
                if token.like_num:
                    try:
                        num_val = float(token.text.replace(",", ""))
                        numbers.append(
                            {
                                "value": num_val,
                                "text": token.text,
                                "start": token.idx,
                                "end": token.idx + len(token.text),
                            }
                        )
                    except ValueError:
                        continue

                # Check for units
                for unit_type, unit_list in self.common_units.items():
                    if token.text.lower() in unit_list:
                        units.append(
                            {
                                "unit": token.text,
                                "type": unit_type,
                                "start": token.idx,
                                "end": token.idx + len(token.text),
                            }
                        )

            # Create numeric facts from sentences with numbers
            if numbers and len(sent.text.strip()) > 20:
                for num in numbers:
                    # Find associated unit if nearby
                    associated_unit = None
                    for unit in units:
                        if (
                            abs(unit["start"] - num["end"]) <= 10
                        ):  # Within 10 characters
                            associated_unit = unit
                            break

                    numeric_facts.append(
                        {
                            "sentence": sent.text.strip(),
                            "number": num,
                            "unit": associated_unit,
                            "confidence": 0.7,
                        }
                    )

        return numeric_facts

    def _extract_procedures(self, doc: Doc) -> list[dict[str, Any]]:
        """Extract procedural text and formulas for short-answer questions."""
        procedures = []

        for sent in doc.sents:
            sent_text = sent.text.strip()

            # Check for formula patterns
            for pattern in self.formula_patterns:
                if re.search(pattern, sent_text, re.IGNORECASE):
                    procedures.append(
                        {"text": sent_text, "type": "formula", "confidence": 0.8}
                    )
                    break

            # Look for procedural language
            procedural_indicators = [
                "step",
                "first",
                "then",
                "next",
                "finally",
                "process",
                "method",
                "algorithm",
                "procedure",
                "how to",
                "in order to",
            ]

            if any(
                indicator in sent_text.lower() for indicator in procedural_indicators
            ):
                if len(sent_text) > 30:
                    procedures.append(
                        {"text": sent_text, "type": "procedure", "confidence": 0.6}
                    )

        return procedures

    def _generate_flashcards(
        self, keypoints: list[dict[str, Any]], difficulty: str, target_count: int
    ) -> list[dict[str, Any]]:
        """Generate flashcard items from keypoints."""
        flashcards = []

        # Sort by confidence and take the best ones
        keypoints.sort(key=lambda x: x["confidence"], reverse=True)

        for keypoint in keypoints[:target_count]:
            flashcard = {
                "type": "flashcard",
                "payload": {
                    "front": f"What is {keypoint['term']}?",
                    "back": keypoint["definition"],
                },
                "tags": ["generated", "definition"],
                "difficulty": difficulty,
                "metadata": {
                    "generation_method": "keypoint_extraction",
                    "source_text": keypoint["source_sentence"],
                    "confidence": keypoint["confidence"],
                    "provenance": {
                        "generator": "basic_rules",
                        "rule": "definition_extraction",
                        "source_length": len(keypoint["source_sentence"]),
                    },
                },
            }
            flashcards.append(flashcard)

        return flashcards

    def _generate_mcqs(
        self, numeric_facts: list[dict[str, Any]], difficulty: str, target_count: int
    ) -> list[dict[str, Any]]:
        """Generate MCQ items from numeric facts with heuristic distractors."""
        mcqs = []

        # Sort by confidence
        numeric_facts.sort(key=lambda x: x["confidence"], reverse=True)

        for fact in numeric_facts[:target_count]:
            number = fact["number"]
            sentence = fact["sentence"]
            unit = fact.get("unit")

            # Create question stem by replacing the number with a blank
            question_text = sentence.replace(number["text"], "____")

            # Generate distractors using heuristics
            correct_value = number["value"]
            distractors = self._generate_numeric_distractors(correct_value, unit)

            # Create options
            all_options = [correct_value] + distractors[:3]  # Correct + 3 distractors
            random.shuffle(all_options)

            options = []
            for i, value in enumerate(all_options):
                unit_text = unit["unit"] if unit else ""
                option_text = f"{value} {unit_text}".strip()

                options.append(
                    {
                        "id": str(i),
                        "text": option_text,
                        "is_correct": value == correct_value,
                    }
                )

            mcq = {
                "type": "mcq",
                "payload": {"stem": question_text, "options": options},
                "tags": ["generated", "numeric"],
                "difficulty": difficulty,
                "metadata": {
                    "generation_method": "numeric_fact_extraction",
                    "source_text": sentence,
                    "confidence": fact["confidence"],
                    "provenance": {
                        "generator": "basic_rules",
                        "rule": "numeric_distractor_generation",
                        "correct_value": correct_value,
                        "unit": unit["unit"] if unit else None,
                    },
                },
            }
            mcqs.append(mcq)

        return mcqs

    def _generate_numeric_distractors(
        self, correct_value: float, unit: dict[str, Any] | None
    ) -> list[float]:
        """Generate plausible numeric distractors using heuristics."""
        distractors = set()

        # Strategy 1: Small variations (±10%, ±25%, ±50%)
        for factor in [0.9, 0.75, 0.5, 1.1, 1.25, 1.5, 2.0]:
            distractor = correct_value * factor
            if distractor != correct_value and distractor > 0:
                distractors.add(round(distractor, 2))

        # Strategy 2: Order of magnitude changes
        for exp in [-1, 1]:
            distractor = correct_value * (10**exp)
            if distractor != correct_value and distractor > 0:
                distractors.add(round(distractor, 2))

        # Strategy 3: Common number patterns
        if correct_value >= 1:
            distractors.add(int(correct_value) + 1)
            distractors.add(int(correct_value) - 1)
            distractors.add(int(correct_value) * 10)
            distractors.add(int(correct_value) / 10)

        # Strategy 4: Unit-specific distractors
        if unit and unit["type"] == "percentage":
            distractors.add(100 - correct_value)  # Complement percentage

        # Remove correct value and convert to list
        distractors.discard(correct_value)
        return list(distractors)[:5]  # Return up to 5 distractors

    def _generate_cloze_questions(
        self, sentences: list[Span], difficulty: str, target_count: int
    ) -> list[dict[str, Any]]:
        """Generate cloze deletion questions from sentences."""
        clozes = []

        for sent in sentences:
            if len(sent.text.strip()) < 30 or len(sent.text.strip()) > 200:
                continue

            # Find good candidates for blanking (nouns, proper nouns, numbers)
            candidates = []
            for token in sent:
                if (
                    token.pos_ in ["NOUN", "PROPN", "NUM"]
                    and not token.is_punct
                    and not token.is_space
                    and len(token.text) > 2
                ):
                    candidates.append(token)

            if not candidates:
                continue

            # Select the most informative token to blank
            best_candidate = max(
                candidates, key=lambda t: len(t.text) + (1 if t.pos_ == "PROPN" else 0)
            )

            # Create the cloze text
            cloze_text = sent.text.replace(best_candidate.text, "___BLANK_0___")

            cloze = {
                "type": "cloze",
                "payload": {
                    "text": cloze_text,
                    "blanks": [
                        {
                            "id": "0",
                            "answers": [best_candidate.text],
                            "alt_answers": [],
                            "case_sensitive": best_candidate.pos_
                            == "PROPN",  # Proper nouns are case sensitive
                        }
                    ],
                },
                "tags": ["generated", "cloze"],
                "difficulty": difficulty,
                "metadata": {
                    "generation_method": "pos_based_masking",
                    "source_text": sent.text,
                    "masked_pos": best_candidate.pos_,
                    "confidence": 0.7,
                    "provenance": {
                        "generator": "basic_rules",
                        "rule": "salient_noun_masking",
                        "masked_word": best_candidate.text,
                    },
                },
            }
            clozes.append(cloze)

            if len(clozes) >= target_count:
                break

        return clozes

    def _generate_short_answers(
        self, procedures: list[dict[str, Any]], difficulty: str, target_count: int
    ) -> list[dict[str, Any]]:
        """Generate short-answer questions from procedures and formulas."""
        short_answers = []

        procedures.sort(key=lambda x: x["confidence"], reverse=True)

        for proc in procedures[:target_count]:
            text = proc["text"]
            proc_type = proc["type"]

            if proc_type == "formula":
                # Extract the formula and create a question about it
                formula_match = re.search(r"[A-Za-z]\s*=\s*[^.]+", text)
                if formula_match:
                    formula = formula_match.group(0)
                    question = f"What is the formula mentioned in: {text.replace(formula, '___')}?"
                    expected_answer = formula.strip()
                else:
                    question = (
                        f"What formula is described in the following text: {text}"
                    )
                    expected_answer = "formula"  # Generic fallback

            else:  # procedure
                # Create a "how" question
                question = f"How would you explain the process described in: {text}"
                expected_answer = text  # Full text as expected answer

            short_answer = {
                "type": "short_answer",
                "payload": {
                    "prompt": question,
                    "expected": {"value": expected_answer},
                    "acceptable_patterns": [],
                    "grading": {"method": "similarity"},  # Use semantic similarity
                },
                "tags": ["generated", proc_type],
                "difficulty": difficulty,
                "metadata": {
                    "generation_method": "procedure_extraction",
                    "source_text": text,
                    "procedure_type": proc_type,
                    "confidence": proc["confidence"],
                    "provenance": {
                        "generator": "basic_rules",
                        "rule": f"{proc_type}_question_generation",
                        "source_length": len(text),
                    },
                },
            }
            short_answers.append(short_answer)

        return short_answers

    def _apply_quality_gates(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply quality gates to filter and improve generated items."""
        quality_items = []
        seen_content = set()

        for item in items:
            # Gate 1: Minimum length requirements
            if not self._check_minimum_length(item):
                continue

            # Gate 2: Uniqueness check (simple content-based)
            content_key = self._get_content_key(item)
            if content_key in seen_content:
                continue
            seen_content.add(content_key)

            # Gate 3: Single unambiguous answer key
            if not self._check_answer_clarity(item):
                continue

            # Add generation metadata
            item["metadata"]["generated_at"] = "step9_basic_rules"
            item["metadata"]["quality_gates_passed"] = [
                "length",
                "uniqueness",
                "clarity",
            ]

            quality_items.append(item)

        return quality_items

    def _check_minimum_length(self, item: dict[str, Any]) -> bool:
        """Check if item meets minimum length requirements."""
        item_type = item["type"]
        payload = item["payload"]

        if item_type == "flashcard":
            return (
                len(payload.get("front", "")) >= 5 and len(payload.get("back", "")) >= 5
            )
        elif item_type == "mcq":
            return (
                len(payload.get("stem", "")) >= 10
                and len(payload.get("options", [])) >= 2
            )
        elif item_type == "cloze":
            return (
                len(payload.get("text", "")) >= 20
                and len(payload.get("blanks", [])) >= 1
            )
        elif item_type == "short_answer":
            return (
                len(payload.get("prompt", "")) >= 10
                and len(payload.get("expected", {}).get("value", "")) >= 2
            )

        return False

    def _get_content_key(self, item: dict[str, Any]) -> str:
        """Generate a content key for uniqueness checking."""
        item_type = item["type"]
        payload = item["payload"]

        if item_type == "flashcard":
            content = f"{payload.get('front', '')}{payload.get('back', '')}"
        elif item_type == "mcq":
            content = payload.get("stem", "")
        elif item_type == "cloze":
            content = payload.get("text", "")
        elif item_type == "short_answer":
            content = payload.get("prompt", "")
        else:
            content = str(payload)

        # Create hash of normalized content
        normalized = re.sub(r"\s+", " ", content.lower().strip())
        return hashlib.md5(normalized.encode()).hexdigest()

    def _check_answer_clarity(self, item: dict[str, Any]) -> bool:
        """Check if the item has a clear, unambiguous answer."""
        item_type = item["type"]
        payload = item["payload"]

        if item_type == "flashcard":
            # Flashcards always have clear answers
            return True
        elif item_type == "mcq":
            options = payload.get("options", [])
            correct_count = sum(1 for opt in options if opt.get("is_correct", False))
            return correct_count == 1  # Exactly one correct answer
        elif item_type == "cloze":
            blanks = payload.get("blanks", [])
            return all(blank.get("answers") for blank in blanks)
        elif item_type == "short_answer":
            expected = payload.get("expected", {})
            return bool(expected.get("value"))

        return False
