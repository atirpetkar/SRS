"""API Endpoint Wrappers - Type-safe API calls"""

from typing import List, Dict, Any, Optional
from .base import APIClient, LearningOSError


class LearningOSClient:
    """High-level client with typed endpoint methods"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.api = APIClient(base_url)
    
    def __enter__(self):
        self.api.__enter__()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.api.__exit__(exc_type, exc_val, exc_tb)
    
    # Health Check
    def health_check(self) -> Dict[str, Any]:
        """Check API health status"""
        return self.api.get("/healthz")
    
    # Items Endpoints
    def list_items(self, 
                   type: Optional[str] = None,
                   tags: Optional[str] = None, 
                   status: str = "published",
                   limit: int = 20,
                   offset: int = 0) -> Dict[str, Any]:
        """List items with filters"""
        params = {"limit": limit, "offset": offset, "status": status}
        if type:
            params["type"] = type
        if tags:
            params["tags"] = tags
        return self.api.get("/items", params)
    
    def get_item(self, item_id: str) -> Dict[str, Any]:
        """Get specific item by ID"""
        return self.api.get(f"/items/{item_id}")
    
    # Review Endpoints
    def get_review_queue(self, 
                        limit: int = 20,
                        mix_new: float = 0.2,
                        tags: Optional[str] = None,
                        type: Optional[str] = None) -> Dict[str, Any]:
        """Get review queue"""
        params = {"limit": limit, "mix_new": mix_new}
        if tags:
            params["tags"] = tags
        if type:
            params["type"] = type
        return self.api.get("/review/queue", params)
    
    def submit_review(self, 
                     item_id: str, 
                     rating: int,
                     correct: Optional[bool] = None,
                     latency_ms: Optional[int] = None,
                     mode: str = "review") -> Dict[str, Any]:
        """Submit a review"""
        data = {
            "item_id": item_id,
            "rating": rating,
            "mode": mode
        }
        if correct is not None:
            data["correct"] = correct
        if latency_ms is not None:
            data["latency_ms"] = latency_ms
        return self.api.post("/review/record", data)
    
    # Quiz Endpoints
    def start_quiz(self, 
                   mode: str = "drill",
                   tags: Optional[str] = None,
                   type: Optional[str] = None,
                   length: int = 10,
                   time_limit_s: Optional[int] = None) -> Dict[str, Any]:
        """Start a new quiz session"""
        data = {
            "mode": mode,
            "params": {
                "length": length
            }
        }
        if tags:
            data["params"]["tags"] = tags
        if type:
            data["params"]["type"] = type
        if time_limit_s:
            data["params"]["time_limit_s"] = time_limit_s
        return self.api.post("/quiz/start", data)
    
    def submit_quiz_answer(self, 
                          quiz_id: str, 
                          item_id: str, 
                          response: Any) -> Dict[str, Any]:
        """Submit answer for quiz item"""
        data = {
            "quiz_id": quiz_id,
            "item_id": item_id,
            "response": response
        }
        return self.api.post("/quiz/submit", data)
    
    def finish_quiz(self, quiz_id: str) -> Dict[str, Any]:
        """Finish quiz session"""
        data = {"quiz_id": quiz_id}
        return self.api.post("/quiz/finish", data)
    
    # Progress Endpoints
    def get_progress_overview(self) -> Dict[str, Any]:
        """Get learning progress overview"""
        return self.api.get("/progress/overview")
    
    def get_weak_areas(self, top: int = 5) -> Dict[str, Any]:
        """Get weak areas that need practice"""
        params = {"top": top}
        return self.api.get("/progress/weak_areas", params)
    
    def get_forecast(self, days: int = 7) -> Dict[str, Any]:
        """Get review forecast"""
        params = {"days": days}
        return self.api.get("/progress/forecast", params)
