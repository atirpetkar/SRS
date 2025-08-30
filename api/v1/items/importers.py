"""
Item importers for various formats (markdown, CSV, JSON).

Implements the ImporterRegistry protocol for parsing external content
into item dictionaries that can be staged and later approved.
"""

import csv
import json
import re
from io import StringIO
from typing import Any

from api.v1.core.registries import Importer


class MarkdownImporter(Importer):
    """
    Importer for markdown files with mini-DSL syntax.

    Supports:
    :::flashcard
    Q: Question here
    A: Answer here
    HINT: Optional hint
    AUDIO: Optional audio URI
    :::

    :::mcq
    STEM: Question stem
    A) Option A *correct
    B) Option B
    C) Option C
    D) Option D
    :::

    :::cloze
    TEXT: The capital of France is [[Paris|paris]].
    :::

    :::short
    PROMPT: What is 2+2?
    EXPECTED: 4
    PATTERN: ^[0-9]+$
    :::
    """

    def parse(self, data: str | bytes, **kwargs: Any) -> list[dict[str, Any]]:
        """Parse markdown content into item dictionaries."""
        if isinstance(data, bytes):
            data = data.decode("utf-8")

        items = []
        diagnostics = kwargs.get("diagnostics", [])

        # Find all code blocks with item type annotations
        pattern = r":::(\w+)(.*?):::"
        matches = re.finditer(pattern, data, re.DOTALL)

        for match in matches:
            item_type = match.group(1).lower()
            content = match.group(2).strip()
            line_start = data[: match.start()].count("\n") + 1

            try:
                if item_type == "flashcard":
                    item = self._parse_flashcard(content, line_start, diagnostics)
                elif item_type == "mcq":
                    item = self._parse_mcq(content, line_start, diagnostics)
                elif item_type == "cloze":
                    item = self._parse_cloze(content, line_start, diagnostics)
                elif item_type == "short":
                    item = self._parse_short_answer(content, line_start, diagnostics)
                else:
                    diagnostics.append(
                        {
                            "line": line_start,
                            "issue": f"Unknown item type: {item_type}",
                            "severity": "error",
                        }
                    )
                    continue

                if item:
                    items.append(item)

            except Exception as e:
                diagnostics.append(
                    {
                        "line": line_start,
                        "issue": f"Error parsing {item_type}: {str(e)}",
                        "severity": "error",
                    }
                )

        return items

    def _parse_flashcard(
        self, content: str, line_start: int, diagnostics: list
    ) -> dict[str, Any] | None:
        """Parse flashcard content."""
        lines = content.strip().split("\n")
        payload = {}
        tags = []
        difficulty = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("Q:"):
                payload["front"] = line[2:].strip()
            elif line.startswith("A:"):
                payload["back"] = line[2:].strip()
            elif line.startswith("HINT:"):
                payload["hints"] = [line[5:].strip()]
            elif line.startswith("AUDIO:"):
                payload["pronunciation"] = line[6:].strip()
            elif line.startswith("EXAMPLES:"):
                payload["examples"] = [ex.strip() for ex in line[9:].split(",")]
            elif line.startswith("TAGS:"):
                tags = [tag.strip() for tag in line[5:].split(",")]
            elif line.startswith("DIFFICULTY:"):
                difficulty = line[11:].strip().lower()

        if not payload.get("front") or not payload.get("back"):
            diagnostics.append(
                {
                    "line": line_start,
                    "issue": "Flashcard missing required Q: and/or A: fields",
                    "severity": "error",
                }
            )
            return None

        return {
            "type": "flashcard",
            "payload": payload,
            "tags": tags,
            "difficulty": difficulty,
            "metadata": {"source_format": "markdown", "source_line": line_start},
        }

    def _parse_mcq(
        self, content: str, line_start: int, diagnostics: list
    ) -> dict[str, Any] | None:
        """Parse multiple choice question content."""
        lines = content.strip().split("\n")
        payload = {"options": []}
        tags = []
        difficulty = None
        option_counter = 0

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("STEM:"):
                payload["stem"] = line[5:].strip()
            elif line.startswith("TAGS:"):
                tags = [tag.strip() for tag in line[5:].split(",")]
            elif line.startswith("DIFFICULTY:"):
                difficulty = line[11:].strip().lower()
            elif re.match(r"^[A-Z]\)", line):
                # Parse option line like "A) Option text *correct"
                is_correct = line.endswith(" *correct")
                text = line[2:].strip()
                if is_correct:
                    text = text[:-9].strip()  # Remove ' *correct'

                payload["options"].append(
                    {"id": str(option_counter), "text": text, "is_correct": is_correct}
                )
                option_counter += 1

        if not payload.get("stem"):
            diagnostics.append(
                {
                    "line": line_start,
                    "issue": "MCQ missing required STEM field",
                    "severity": "error",
                }
            )
            return None

        if len(payload["options"]) < 2:
            diagnostics.append(
                {
                    "line": line_start,
                    "issue": "MCQ must have at least 2 options",
                    "severity": "error",
                }
            )
            return None

        if not any(opt["is_correct"] for opt in payload["options"]):
            diagnostics.append(
                {
                    "line": line_start,
                    "issue": "MCQ must have at least one correct option",
                    "severity": "error",
                }
            )
            return None

        return {
            "type": "mcq",
            "payload": payload,
            "tags": tags,
            "difficulty": difficulty,
            "metadata": {"source_format": "markdown", "source_line": line_start},
        }

    def _parse_cloze(
        self, content: str, line_start: int, diagnostics: list
    ) -> dict[str, Any] | None:
        """Parse cloze deletion content."""
        lines = content.strip().split("\n")
        payload = {}
        tags = []
        difficulty = None
        blanks = []  # Move outside the loop to avoid B023 violation

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("TEXT:"):
                text = line[5:].strip()
                # Parse blanks in format [[Answer|Alt Answer]]
                blanks.clear()  # Reset blanks for this TEXT block
                blank_pattern = r"\[\[([^\]]+)\]\]"
                blank_id = 0

                def replace_blank(match):
                    nonlocal blank_id
                    answers_text = match.group(1)
                    answers = [ans.strip() for ans in answers_text.split("|")]

                    blanks.append(
                        {
                            "id": str(blank_id),
                            "answers": [answers[0]],  # Primary answer
                            "alt_answers": answers[1:] if len(answers) > 1 else [],
                            "case_sensitive": False,  # Default to case insensitive
                        }
                    )
                    placeholder = f"___BLANK_{blank_id}___"
                    blank_id += 1
                    return placeholder

                processed_text = re.sub(blank_pattern, replace_blank, text)
                payload["text"] = processed_text
                payload["blanks"] = blanks

            elif line.startswith("TAGS:"):
                tags = [tag.strip() for tag in line[5:].split(",")]
            elif line.startswith("DIFFICULTY:"):
                difficulty = line[11:].strip().lower()
            elif line.startswith("CONTEXT:"):
                payload["context_note"] = line[8:].strip()

        if not payload.get("text") or not payload.get("blanks"):
            diagnostics.append(
                {
                    "line": line_start,
                    "issue": "Cloze missing required TEXT field with blanks [[answer]]",
                    "severity": "error",
                }
            )
            return None

        return {
            "type": "cloze",
            "payload": payload,
            "tags": tags,
            "difficulty": difficulty,
            "metadata": {"source_format": "markdown", "source_line": line_start},
        }

    def _parse_short_answer(
        self, content: str, line_start: int, diagnostics: list
    ) -> dict[str, Any] | None:
        """Parse short answer content."""
        lines = content.strip().split("\n")
        payload = {"acceptable_patterns": [], "grading": {"method": "exact"}}
        tags = []
        difficulty = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("PROMPT:"):
                payload["prompt"] = line[7:].strip()
            elif line.startswith("EXPECTED:"):
                expected_text = line[9:].strip()
                # Try to parse as number with unit
                if " " in expected_text:
                    value, unit = expected_text.rsplit(" ", 1)
                    try:
                        float(value)
                        payload["expected"] = {"value": value, "unit": unit}
                    except ValueError:
                        payload["expected"] = {"value": expected_text}
                else:
                    payload["expected"] = {"value": expected_text}
            elif line.startswith("PATTERN:"):
                pattern = line[8:].strip()
                payload["acceptable_patterns"].append(pattern)
            elif line.startswith("TAGS:"):
                tags = [tag.strip() for tag in line[5:].split(",")]
            elif line.startswith("DIFFICULTY:"):
                difficulty = line[11:].strip().lower()

        if not payload.get("prompt"):
            diagnostics.append(
                {
                    "line": line_start,
                    "issue": "Short answer missing required PROMPT field",
                    "severity": "error",
                }
            )
            return None

        return {
            "type": "short_answer",
            "payload": payload,
            "tags": tags,
            "difficulty": difficulty,
            "metadata": {"source_format": "markdown", "source_line": line_start},
        }


class CSVImporter(Importer):
    """Importer for CSV files with predefined column structure."""

    def parse(self, data: str | bytes, **kwargs: Any) -> list[dict[str, Any]]:
        """Parse CSV content into item dictionaries."""
        if isinstance(data, bytes):
            data = data.decode("utf-8")

        items = []
        diagnostics = kwargs.get("diagnostics", [])

        try:
            reader = csv.DictReader(StringIO(data))

            for row_num, row in enumerate(
                reader, start=2
            ):  # Start at 2 since header is row 1
                try:
                    item_type = row.get("type", "").lower()
                    if not item_type:
                        diagnostics.append(
                            {
                                "row": row_num,
                                "issue": "Missing item type",
                                "severity": "error",
                            }
                        )
                        continue

                    # Parse payload from JSON string
                    payload_str = row.get("payload", "{}")
                    payload = json.loads(payload_str) if payload_str else {}

                    # Parse tags
                    tags_str = row.get("tags", "")
                    tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]

                    item = {
                        "type": item_type,
                        "payload": payload,
                        "tags": tags,
                        "difficulty": row.get("difficulty") or None,
                        "metadata": {"source_format": "csv", "source_row": row_num},
                    }

                    items.append(item)

                except json.JSONDecodeError as e:
                    diagnostics.append(
                        {
                            "row": row_num,
                            "issue": f"Invalid JSON in payload: {str(e)}",
                            "severity": "error",
                        }
                    )
                except Exception as e:
                    diagnostics.append(
                        {
                            "row": row_num,
                            "issue": f"Error parsing row: {str(e)}",
                            "severity": "error",
                        }
                    )

        except Exception as e:
            diagnostics.append(
                {"issue": f"Error parsing CSV: {str(e)}", "severity": "error"}
            )

        return items


class JSONImporter(Importer):
    """Importer for JSON files with item arrays."""

    def parse(self, data: str | bytes, **kwargs: Any) -> list[dict[str, Any]]:
        """Parse JSON content into item dictionaries."""
        if isinstance(data, bytes):
            data = data.decode("utf-8")

        items = []
        diagnostics = kwargs.get("diagnostics", [])

        try:
            parsed_data = json.loads(data)

            # Handle both array format and object with 'items' key
            if isinstance(parsed_data, list):
                items_data = parsed_data
            elif isinstance(parsed_data, dict) and "items" in parsed_data:
                items_data = parsed_data["items"]
            else:
                diagnostics.append(
                    {
                        "issue": 'JSON must be an array of items or object with "items" key',
                        "severity": "error",
                    }
                )
                return []

            for idx, item_data in enumerate(items_data):
                try:
                    if not isinstance(item_data, dict):
                        diagnostics.append(
                            {
                                "item": idx,
                                "issue": "Item must be an object",
                                "severity": "error",
                            }
                        )
                        continue

                    # Validate required fields
                    if "type" not in item_data:
                        diagnostics.append(
                            {
                                "item": idx,
                                "issue": 'Missing required "type" field',
                                "severity": "error",
                            }
                        )
                        continue

                    if "payload" not in item_data:
                        diagnostics.append(
                            {
                                "item": idx,
                                "issue": 'Missing required "payload" field',
                                "severity": "error",
                            }
                        )
                        continue

                    item = {
                        "type": item_data["type"],
                        "payload": item_data["payload"],
                        "tags": item_data.get("tags", []),
                        "difficulty": item_data.get("difficulty"),
                        "metadata": item_data.get("metadata", {}),
                    }

                    # Add source tracking
                    item["metadata"].update(
                        {"source_format": "json", "source_item": idx}
                    )

                    items.append(item)

                except Exception as e:
                    diagnostics.append(
                        {
                            "item": idx,
                            "issue": f"Error parsing item: {str(e)}",
                            "severity": "error",
                        }
                    )

        except json.JSONDecodeError as e:
            diagnostics.append(
                {"issue": f"Invalid JSON: {str(e)}", "severity": "error"}
            )
        except Exception as e:
            diagnostics.append(
                {"issue": f"Error parsing JSON: {str(e)}", "severity": "error"}
            )

        return items
