"""Tests for CLI commands"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from typer.testing import CliRunner
from cli.main import app
from cli.client.base import LearningOSError


# Test fixtures
@pytest.fixture
def runner():
    """CLI test runner"""
    return CliRunner()


@pytest.fixture 
def mock_client():
    """Mock API client"""
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=None)
    return client


class TestMainCommands:
    """Test main CLI commands"""
    
    @pytest.mark.skip(reason="CLI version callback needs refactoring")
    def test_version(self, runner):
        """Test version command"""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "Learning OS CLI" in result.stdout
    
    def test_quickstart(self, runner):
        """Test quickstart command"""
        result = runner.invoke(app, ["quickstart"])
        assert result.exit_code == 0
        assert "Quick Start Guide" in result.stdout
        assert "learning-os status" in result.stdout
    
    @patch("cli.main.LearningOSClient")
    def test_status_success(self, mock_client_class, runner):
        """Test status command with successful connection"""
        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.health_check.return_value = {
            "version": "1.0.0",
            "environment": "development"
        }
        mock_client_class.return_value = mock_client
        
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Connected Successfully" in result.stdout
    
    @patch("cli.main.LearningOSClient")
    def test_status_failure(self, mock_client_class, runner):
        """Test status command with connection failure"""
        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.health_check.side_effect = LearningOSError("Connection failed")
        mock_client_class.return_value = mock_client
        
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 1
        assert "Connection Failed" in result.stdout


class TestReviewCommands:
    """Test review commands"""
    
    @patch("cli.commands.review.LearningOSClient")
    def test_review_queue_empty(self, mock_client_class, runner):
        """Test review queue when empty"""
        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.get_review_queue.return_value = {"due": [], "new": []}
        mock_client_class.return_value = mock_client
        
        result = runner.invoke(app, ["review", "queue"])
        assert result.exit_code == 0
        assert "No items to review" in result.stdout
    
    @patch("cli.commands.review.LearningOSClient")
    def test_review_queue_with_items(self, mock_client_class, runner):
        """Test review queue with items"""
        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.get_review_queue.return_value = {
            "due": [
                {
                    "id": "item1",
                    "type": "flashcard",
                    "due_at": "2024-01-01T00:00:00Z",
                    "payload": {"front": "Test question", "back": "Test answer"}
                }
            ],
            "new": []
        }
        mock_client_class.return_value = mock_client
        
        result = runner.invoke(app, ["review", "queue"])
        assert result.exit_code == 0
        assert "item1" in result.stdout
    
    @patch("cli.commands.review.LearningOSClient")
    def test_submit_review(self, mock_client_class, runner):
        """Test submitting a review"""
        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.submit_review.return_value = {
            "updated_state": {"due_at": "2024-01-02T00:00:00Z"}
        }
        mock_client_class.return_value = mock_client
        
        result = runner.invoke(app, ["review", "submit", "item1", "--rating", "3"])
        assert result.exit_code == 0
        assert "Review submitted" in result.stdout
    
    def test_submit_review_invalid_rating(self, runner):
        """Test submitting review with invalid rating"""
        result = runner.invoke(app, ["review", "submit", "item1", "--rating", "5"])
        assert result.exit_code == 1
        assert "Rating must be between 1 and 4" in result.stdout


class TestQuizCommands:
    """Test quiz commands"""
    
    @patch("cli.commands.quiz.LearningOSClient")
    def test_start_quiz_non_interactive(self, mock_client_class, runner):
        """Test starting a non-interactive quiz"""
        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.start_quiz.return_value = {
            "quiz_id": "quiz123",
            "items": [
                {
                    "id": "item1",
                    "type": "mcq",
                    "payload": {"stem": "Test question"}
                }
            ]
        }
        mock_client_class.return_value = mock_client
        
        result = runner.invoke(app, ["quiz", "start", "--non-interactive"])
        assert result.exit_code == 0
        assert "Quiz started" in result.stdout
        assert "quiz123" in result.stdout
    
    @patch("cli.commands.quiz.LearningOSClient")
    def test_start_quiz_no_items(self, mock_client_class, runner):
        """Test starting quiz when no items available"""
        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.start_quiz.return_value = {
            "quiz_id": "quiz123",
            "items": []
        }
        mock_client_class.return_value = mock_client
        
        result = runner.invoke(app, ["quiz", "start", "--non-interactive"])
        assert result.exit_code == 1
        assert "No items found for quiz" in result.stdout
    
    @patch("cli.commands.quiz.LearningOSClient")
    def test_submit_quiz_answer(self, mock_client_class, runner):
        """Test submitting a quiz answer"""
        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.submit_quiz_answer.return_value = {
            "correct": True,
            "rationale": "Good job!"
        }
        mock_client_class.return_value = mock_client
        
        result = runner.invoke(app, ["quiz", "submit", "quiz123", "item1", "answer"])
        assert result.exit_code == 0
        assert "Correct!" in result.stdout
    
    @patch("cli.commands.quiz.LearningOSClient")
    def test_finish_quiz(self, mock_client_class, runner):
        """Test finishing a quiz"""
        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.finish_quiz.return_value = {
            "score": 0.8,
            "breakdown": {"correct": 4, "total": 5}
        }
        mock_client_class.return_value = mock_client
        
        result = runner.invoke(app, ["quiz", "finish", "quiz123"])
        assert result.exit_code == 0
        assert "Quiz Complete" in result.stdout


class TestProgressCommands:
    """Test progress commands"""
    
    @patch("cli.commands.progress.LearningOSClient")
    def test_progress_overview(self, mock_client_class, runner):
        """Test progress overview"""
        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.get_progress_overview.return_value = {
            "attempts_7d": 50,
            "accuracy_7d": 0.85,
            "avg_latency_ms_7d": 2500,
            "streak_days": 5,
            "total_items": 100,
            "reviewed_items": 80
        }
        mock_client_class.return_value = mock_client
        
        result = runner.invoke(app, ["progress", "overview"])
        assert result.exit_code == 0
        assert "Progress Overview" in result.stdout
        assert "85.0%" in result.stdout  # accuracy
    
    @patch("cli.commands.progress.LearningOSClient")
    def test_weak_areas(self, mock_client_class, runner):
        """Test weak areas analysis"""
        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.get_weak_areas.return_value = {
            "tags": [
                {"tag": "math", "accuracy": 0.6, "attempts": 20}
            ],
            "types": [
                {"type": "mcq", "accuracy": 0.7, "attempts": 15}
            ]
        }
        mock_client_class.return_value = mock_client
        
        result = runner.invoke(app, ["progress", "weak-areas"])
        assert result.exit_code == 0
        assert "math" in result.stdout
        assert "60.0%" in result.stdout
    
    @patch("cli.commands.progress.LearningOSClient")
    def test_forecast(self, mock_client_class, runner):
        """Test review forecast"""
        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.get_forecast.return_value = {
            "by_day": [
                {"date": "2024-01-01", "due_count": 5},
                {"date": "2024-01-02", "due_count": 3}
            ]
        }
        mock_client_class.return_value = mock_client
        
        result = runner.invoke(app, ["progress", "forecast"])
        assert result.exit_code == 0
        assert "Review Forecast" in result.stdout
        assert "2024-01-01" in result.stdout


class TestItemsCommands:
    """Test items commands"""
    
    @patch("cli.commands.items.LearningOSClient")
    def test_list_items(self, mock_client_class, runner):
        """Test listing items"""
        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.list_items.return_value = {
            "items": [
                {
                    "id": "item1",
                    "type": "flashcard",
                    "tags": ["test"],
                    "difficulty": "easy",
                    "payload": {"front": "Test question"}
                }
            ],
            "total": 1
        }
        mock_client_class.return_value = mock_client
        
        result = runner.invoke(app, ["items", "list"])
        assert result.exit_code == 0
        assert "item1" in result.stdout
        assert "flashcard" in result.stdout
    
    @patch("cli.commands.items.LearningOSClient")
    def test_show_item(self, mock_client_class, runner):
        """Test showing specific item"""
        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.get_item.return_value = {
            "id": "item1",
            "type": "flashcard",
            "tags": ["test"],
            "difficulty": "easy",
            "created_at": "2024-01-01T00:00:00Z",
            "created_by": "user1",
            "status": "published",
            "payload": {"front": "Test question", "back": "Test answer"}
        }
        mock_client_class.return_value = mock_client
        
        result = runner.invoke(app, ["items", "show", "item1"])
        assert result.exit_code == 0
        assert "Item Metadata" in result.stdout
        assert "Test question" in result.stdout


class TestConfigCommands:
    """Test configuration commands"""
    
    @patch("cli.commands.config.config")
    def test_set_config(self, mock_config, runner):
        """Test setting configuration"""
        result = runner.invoke(app, ["config", "set", "api.base_url", "http://localhost:8000"])
        assert result.exit_code == 0
        mock_config.set.assert_called_once_with("api.base_url", "http://localhost:8000")
    
    def test_set_config_invalid_url(self, runner):
        """Test setting invalid URL"""
        result = runner.invoke(app, ["config", "set", "api.base_url", "invalid-url"])
        assert result.exit_code == 1
        assert "must start with http" in result.stdout
    
    @patch("cli.commands.config.config")
    def test_get_config(self, mock_config, runner):
        """Test getting configuration"""
        mock_config.get.return_value = "http://localhost:8000"
        
        result = runner.invoke(app, ["config", "get", "api.base_url"])
        assert result.exit_code == 0
        assert "http://localhost:8000" in result.stdout
    
    @patch("cli.commands.config.config")
    def test_show_config(self, mock_config, runner):
        """Test showing all configuration"""
        mock_config.load_config.return_value = {
            "api": {"base_url": "http://localhost:8000", "timeout": 30}
        }
        
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "Configuration" in result.stdout


class TestErrorHandling:
    """Test error handling scenarios"""
    
    @patch("cli.commands.review.LearningOSClient")
    def test_api_error_handling(self, mock_client_class, runner):
        """Test API error handling"""
        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.get_review_queue.side_effect = LearningOSError("API Error")
        mock_client_class.return_value = mock_client
        
        result = runner.invoke(app, ["review", "queue"])
        assert result.exit_code == 1
        assert "Failed to get review queue" in result.stdout
    
    def test_invalid_command(self, runner):
        """Test invalid command handling"""
        result = runner.invoke(app, ["invalid-command"])
        assert result.exit_code != 0