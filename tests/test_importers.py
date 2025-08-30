"""
Tests for the import functionality.
"""

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.v1.items.importers import CSVImporter, JSONImporter, MarkdownImporter


class TestMarkdownImporter:
    """Test the markdown importer."""

    def test_parse_flashcard(self):
        """Test parsing a simple flashcard."""
        importer = MarkdownImporter()
        content = """
:::flashcard
Q: What is the capital of France?
A: Paris
HINT: It's known as the City of Light
TAGS: geography, france
DIFFICULTY: intro
:::
"""
        diagnostics = []
        items = importer.parse(content, diagnostics=diagnostics)

        assert len(items) == 1
        assert len(diagnostics) == 0

        item = items[0]
        assert item["type"] == "flashcard"
        assert item["payload"]["front"] == "What is the capital of France?"
        assert item["payload"]["back"] == "Paris"
        assert item["payload"]["hints"] == ["It's known as the City of Light"]
        assert item["tags"] == ["geography", "france"]
        assert item["difficulty"] == "intro"

    def test_parse_mcq(self):
        """Test parsing a multiple choice question."""
        importer = MarkdownImporter()
        content = """
:::mcq
STEM: What is 2 + 2?
A) 3
B) 4 *correct
C) 5
D) 6
TAGS: math, basic
:::
"""
        diagnostics = []
        items = importer.parse(content, diagnostics=diagnostics)

        assert len(items) == 1
        assert len(diagnostics) == 0

        item = items[0]
        assert item["type"] == "mcq"
        assert item["payload"]["stem"] == "What is 2 + 2?"
        assert len(item["payload"]["options"]) == 4

        # Check correct option
        correct_options = [
            opt for opt in item["payload"]["options"] if opt["is_correct"]
        ]
        assert len(correct_options) == 1
        assert correct_options[0]["text"] == "4"
        assert correct_options[0]["id"] == "1"  # Should be string, not integer

    def test_parse_cloze(self):
        """Test parsing a cloze deletion."""
        importer = MarkdownImporter()
        content = """
:::cloze
TEXT: The capital of France is [[Paris|paris]].
TAGS: geography
:::
"""
        diagnostics = []
        items = importer.parse(content, diagnostics=diagnostics)

        assert len(items) == 1
        assert len(diagnostics) == 0

        item = items[0]
        assert item["type"] == "cloze"
        assert "The capital of France is ___BLANK_0___" in item["payload"]["text"]
        assert len(item["payload"]["blanks"]) == 1

        blank = item["payload"]["blanks"][0]
        assert blank["id"] == "0"  # Should be string, not integer
        assert blank["answers"] == ["Paris"]
        assert blank["alt_answers"] == ["paris"]

    def test_parse_short_answer(self):
        """Test parsing a short answer question."""
        importer = MarkdownImporter()
        content = """
:::short
PROMPT: What is the speed of light in m/s?
EXPECTED: 299792458 m/s
PATTERN: ^\\d+\\s*m/s$
:::
"""
        diagnostics = []
        items = importer.parse(content, diagnostics=diagnostics)

        assert len(items) == 1
        assert len(diagnostics) == 0

        item = items[0]
        assert item["type"] == "short_answer"
        assert item["payload"]["prompt"] == "What is the speed of light in m/s?"
        assert item["payload"]["expected"]["value"] == "299792458"
        assert item["payload"]["expected"]["unit"] == "m/s"
        assert "^\\d+\\s*m/s$" in item["payload"]["acceptable_patterns"]

    def test_parse_multiple_items(self):
        """Test parsing multiple items in one document."""
        importer = MarkdownImporter()
        content = """
:::flashcard
Q: What is 1 + 1?
A: 2
:::

:::mcq
STEM: What color is the sky?
A) Red
B) Blue *correct
C) Green
:::
"""
        diagnostics = []
        items = importer.parse(content, diagnostics=diagnostics)

        assert len(items) == 2
        assert len(diagnostics) == 0
        assert items[0]["type"] == "flashcard"
        assert items[1]["type"] == "mcq"

    def test_parse_invalid_item_type(self):
        """Test parsing with invalid item type."""
        importer = MarkdownImporter()
        content = """
:::invalid_type
Q: Some question
A: Some answer
:::
"""
        diagnostics = []
        items = importer.parse(content, diagnostics=diagnostics)

        assert len(items) == 0
        assert len(diagnostics) == 1
        assert diagnostics[0]["severity"] == "error"
        assert "Unknown item type: invalid_type" in diagnostics[0]["issue"]

    def test_parse_incomplete_flashcard(self):
        """Test parsing incomplete flashcard."""
        importer = MarkdownImporter()
        content = """
:::flashcard
Q: What is the capital of France?
:::
"""
        diagnostics = []
        items = importer.parse(content, diagnostics=diagnostics)

        assert len(items) == 0
        assert len(diagnostics) == 1
        assert diagnostics[0]["severity"] == "error"
        assert "missing required Q: and/or A: fields" in diagnostics[0]["issue"]


class TestCSVImporter:
    """Test the CSV importer."""

    def test_parse_simple_csv(self):
        """Test parsing a simple CSV file."""
        importer = CSVImporter()
        content = """type,payload,tags,difficulty
flashcard,"{""front"": ""Question"", ""back"": ""Answer""}",geography,intro
mcq,"{""stem"": ""What is 2+2?"", ""options"": [{""id"": 0, ""text"": ""4"", ""is_correct"": true}]}",math,core"""

        diagnostics = []
        items = importer.parse(content, diagnostics=diagnostics)

        assert len(items) == 2
        assert items[0]["type"] == "flashcard"
        assert items[1]["type"] == "mcq"
        assert items[0]["tags"] == ["geography"]
        assert items[0]["difficulty"] == "intro"

    def test_parse_invalid_json_payload(self):
        """Test parsing CSV with invalid JSON payload."""
        importer = CSVImporter()
        content = """type,payload,tags,difficulty
flashcard,"{invalid json}",geography,intro"""

        diagnostics = []
        items = importer.parse(content, diagnostics=diagnostics)

        assert len(items) == 0
        assert len(diagnostics) == 1
        assert diagnostics[0]["severity"] == "error"
        assert "Invalid JSON in payload" in diagnostics[0]["issue"]


class TestJSONImporter:
    """Test the JSON importer."""

    def test_parse_json_array(self):
        """Test parsing JSON array format."""
        importer = JSONImporter()
        content = json.dumps(
            [
                {
                    "type": "flashcard",
                    "payload": {"front": "Question", "back": "Answer"},
                    "tags": ["test"],
                    "difficulty": "intro",
                },
                {
                    "type": "mcq",
                    "payload": {
                        "stem": "What is 2+2?",
                        "options": [{"id": 0, "text": "4", "is_correct": True}],
                    },
                },
            ]
        )

        diagnostics = []
        items = importer.parse(content, diagnostics=diagnostics)

        assert len(items) == 2
        assert items[0]["type"] == "flashcard"
        assert items[1]["type"] == "mcq"

    def test_parse_json_object_with_items_key(self):
        """Test parsing JSON object with 'items' key."""
        importer = JSONImporter()
        content = json.dumps(
            {
                "metadata": {"source": "test"},
                "items": [
                    {
                        "type": "flashcard",
                        "payload": {"front": "Question", "back": "Answer"},
                    }
                ],
            }
        )

        diagnostics = []
        items = importer.parse(content, diagnostics=diagnostics)

        assert len(items) == 1
        assert items[0]["type"] == "flashcard"

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON."""
        importer = JSONImporter()
        content = "{invalid json}"

        diagnostics = []
        items = importer.parse(content, diagnostics=diagnostics)

        assert len(items) == 0
        assert len(diagnostics) == 1
        assert diagnostics[0]["severity"] == "error"
        assert "Invalid JSON" in diagnostics[0]["issue"]

    def test_parse_missing_required_fields(self):
        """Test parsing items missing required fields."""
        importer = JSONImporter()
        content = json.dumps(
            [
                {"type": "flashcard"},  # Missing payload
                {"payload": {"front": "Q", "back": "A"}},  # Missing type
            ]
        )

        diagnostics = []
        items = importer.parse(content, diagnostics=diagnostics)

        assert len(items) == 0
        assert len(diagnostics) == 2
        assert all(d["severity"] == "error" for d in diagnostics)


@pytest.fixture
def client():
    """Create a test client."""
    app = create_app()
    return TestClient(app)


class TestImportEndpoints:
    """Test the import API endpoints."""

    def test_import_markdown_flashcards(self, client):
        """Test importing markdown flashcards."""
        markdown_content = """
:::flashcard
Q: What is the capital of France?
A: Paris
TAGS: geography, europe
DIFFICULTY: intro
:::

:::flashcard
Q: What is 2 + 2?
A: 4
TAGS: math, basic
:::
"""

        response = client.post(
            "/v1/items/import",
            json={
                "format": "markdown",
                "data": markdown_content,
                "metadata": {"test": "data"},
            },
        )

        assert response.status_code == 200
        result = response.json()

        assert result["total_parsed"] == 2
        assert result["total_created"] == 2
        assert result["total_errors"] == 0
        assert len(result["staged_ids"]) == 2

    def test_import_invalid_format(self, client):
        """Test importing with invalid format."""
        response = client.post(
            "/v1/items/import", json={"format": "invalid", "data": "some content"}
        )

        assert response.status_code == 400
        error = response.json()
        assert "Unsupported import format" in error["detail"]

    def test_import_with_validation_errors(self, client):
        """Test importing content with validation errors."""
        markdown_content = """
:::flashcard
Q: Question with no answer
:::

:::invalid_type
Q: Invalid item type
A: Answer
:::
"""

        response = client.post(
            "/v1/items/import", json={"format": "markdown", "data": markdown_content}
        )

        assert response.status_code == 200
        result = response.json()

        assert result["total_parsed"] == 2
        assert result["total_created"] == 0
        assert result["total_errors"] == 2
        assert len(result["diagnostics"]) == 2

    def test_get_staged_items(self, client):
        """Test getting staged items."""
        # First import some items
        markdown_content = """
:::flashcard
Q: Test question
A: Test answer
:::
"""

        import_response = client.post(
            "/v1/items/import", json={"format": "markdown", "data": markdown_content}
        )
        assert import_response.status_code == 200

        # Then get staged items
        response = client.get("/v1/items/staged")
        assert response.status_code == 200

        result = response.json()
        assert result["total"] >= 1
        # All items should be in draft status
        for item in result["items"]:
            assert item["status"] == "draft"

    def test_approve_staged_items(self, client):
        """Test approving staged items."""
        # First import some items
        markdown_content = """
:::flashcard
Q: Test question for approval
A: Test answer
:::
"""

        import_response = client.post(
            "/v1/items/import", json={"format": "markdown", "data": markdown_content}
        )
        assert import_response.status_code == 200

        staged_ids = import_response.json()["staged_ids"]
        assert len(staged_ids) == 1

        # Approve the items
        approval_response = client.post("/v1/items/approve", json={"ids": staged_ids})
        assert approval_response.status_code == 200

        result = approval_response.json()
        assert len(result["approved_ids"]) == 1
        assert len(result["failed_ids"]) == 0

        # Verify items are now published
        item_response = client.get(f"/v1/items/{staged_ids[0]}")
        assert item_response.status_code == 200
        assert item_response.json()["status"] == "published"

    def test_approve_nonexistent_items(self, client):
        """Test approving non-existent items."""
        fake_id = str(uuid4())

        response = client.post("/v1/items/approve", json={"ids": [fake_id]})
        assert response.status_code == 200

        result = response.json()
        assert len(result["approved_ids"]) == 0
        assert len(result["failed_ids"]) == 1
        assert fake_id in result["errors"]
