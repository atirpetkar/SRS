"""
FSRS-6 (Free Spaced Repetition Scheduler) Algorithm Implementation.

Based on the DSR (Difficulty, Stability, Retrievability) model.
This implementation follows the FSRS-6 specification with 21 parameters.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from api.v1.review.schemas import SchedulerStateResponse


# FSRS-6 Default Parameters (21 parameters)
DEFAULT_FSRS_PARAMS = [
    0.4197, 1.1869, 3.0412, 15.2441, 7.1434, 0.6477, 1.0007, 0.0674, 1.6597, 0.1712,
    1.1178, 2.0225, 0.0904, 0.3025, 2.1214, 0.2498, 2.9466, 0.4891, 0.6468, 0.1563, 1.0000
]


@dataclass
class FSRSState:
    """FSRS state representing memory state for a user/item pair."""
    user_id: str
    item_id: str
    difficulty: float
    stability: float
    due_at: datetime
    last_interval: int
    reps: int
    lapses: int
    last_reviewed_at: datetime | None = None


class FSRSScheduler:
    """FSRS-6 scheduler implementation."""
    
    def __init__(self, parameters: list[float] | None = None):
        """Initialize FSRS scheduler with parameters."""
        self.params = parameters or DEFAULT_FSRS_PARAMS
        if len(self.params) != 21:
            raise ValueError(f"FSRS-6 requires exactly 21 parameters, got {len(self.params)}")
    
    def seed(self, user_id: str, item_id: str) -> FSRSState:
        """Initialize scheduler state for a new user/item pair."""
        # Initial difficulty should be reasonable, around 5.0 for new items
        initial_difficulty = 5.0
        # Initial stability is parameter 1 (index 0)  
        initial_stability = self.params[0]
        # Due immediately for first review
        due_at = datetime.now(timezone.utc)
        
        return FSRSState(
            user_id=user_id,
            item_id=item_id,
            difficulty=initial_difficulty,
            stability=initial_stability,
            due_at=due_at,
            last_interval=0,
            reps=0,
            lapses=0,
            last_reviewed_at=None
        )
    
    def update(
        self, 
        state: FSRSState, 
        rating: int, 
        correct: bool | None, 
        latency_ms: int
    ) -> FSRSState:
        """Update scheduler state based on review results."""
        if rating < 1 or rating > 4:
            raise ValueError(f"Rating must be between 1-4, got {rating}")
        
        now = datetime.now(timezone.utc)
        
        # Calculate retrievability at time of review
        if state.last_reviewed_at and state.stability > 0:
            days_elapsed = (now - state.last_reviewed_at).days
            retrievability = self._calculate_retrievability(state.stability, days_elapsed)
        else:
            retrievability = 1.0  # First review
        
        # Update state based on rating
        if rating == 1:  # Again
            new_state = self._handle_lapse(state, now)
        else:  # Hard (2), Good (3), Easy (4)
            new_state = self._handle_success(state, rating, retrievability, now)
        
        return new_state
    
    def _calculate_retrievability(self, stability: float, days_elapsed: int) -> float:
        """Calculate retrievability using forgetting curve."""
        if days_elapsed <= 0 or stability <= 0:
            return 1.0
        return math.exp(-days_elapsed / stability)
    
    def _handle_lapse(self, state: FSRSState, now: datetime) -> FSRSState:
        """Handle lapse (rating = 1, Again)."""
        # New difficulty after lapse
        new_difficulty = self._next_difficulty_after_failure(state.difficulty)
        
        # New stability after lapse using parameter 11 (index 10)
        new_stability = self.params[10] * state.difficulty * (state.stability ** -0.13) * (
            (1 + math.exp(self.params[12] * (11 - state.reps))) ** -1
        ) * (1 - self.params[13] * (state.difficulty - 3))
        
        new_stability = max(0.01, new_stability)  # Minimum stability
        
        # Short interval for lapse (1 day)
        new_interval = 1
        due_at = now + timedelta(days=new_interval)
        
        return FSRSState(
            user_id=state.user_id,
            item_id=state.item_id,
            difficulty=new_difficulty,
            stability=new_stability,
            due_at=due_at,
            last_interval=new_interval,
            reps=state.reps + 1,
            lapses=state.lapses + 1,
            last_reviewed_at=now
        )
    
    def _handle_success(
        self, 
        state: FSRSState, 
        rating: int, 
        retrievability: float, 
        now: datetime
    ) -> FSRSState:
        """Handle successful review (rating 2, 3, or 4)."""
        # New difficulty after success
        new_difficulty = self._next_difficulty_after_success(state.difficulty, rating)
        
        # New stability calculation
        if state.reps == 0:
            # First successful review
            new_stability = self.params[rating - 1]  # params[1], [2], or [3] for ratings 2, 3, 4
        else:
            # Subsequent reviews
            stability_factor = self._calculate_stability_factor(rating, retrievability)
            new_stability = state.stability * stability_factor
        
        new_stability = max(0.01, new_stability)  # Minimum stability
        
        # Calculate new interval
        new_interval = self._calculate_interval(new_stability, rating)
        due_at = now + timedelta(days=new_interval)
        
        return FSRSState(
            user_id=state.user_id,
            item_id=state.item_id,
            difficulty=new_difficulty,
            stability=new_stability,
            due_at=due_at,
            last_interval=new_interval,
            reps=state.reps + 1,
            lapses=state.lapses,
            last_reviewed_at=now
        )
    
    def _next_difficulty_after_failure(self, difficulty: float) -> float:
        """Calculate new difficulty after failure."""
        # Parameter 15 (index 14) controls difficulty increase after lapse
        # For lapses, difficulty increases but shouldn't exceed original too much
        new_difficulty = min(difficulty + self.params[14], difficulty * 1.2)
        return min(10.0, max(1.0, new_difficulty))  # Clamp between 1 and 10
    
    def _next_difficulty_after_success(self, difficulty: float, rating: int) -> float:
        """Calculate new difficulty after success."""
        # Parameters 5-8 (indices 4-7) control difficulty changes
        if rating == 2:  # Hard
            delta = self.params[5] * (difficulty - 1)
        elif rating == 3:  # Good  
            delta = self.params[6] * (difficulty - 3)
        elif rating == 4:  # Easy
            delta = self.params[7] * (difficulty - 6)
        else:
            delta = 0
        
        new_difficulty = difficulty - delta
        return min(10.0, max(1.0, new_difficulty))  # Clamp between 1 and 10
    
    def _calculate_stability_factor(self, rating: int, retrievability: float) -> float:
        """Calculate stability factor for successful reviews."""
        # FSRS-6 stability factor calculation using parameters 8-11
        if rating == 2:  # Hard
            factor = self.params[8] * (1 + self.params[9] * retrievability)
        elif rating == 3:  # Good
            factor = 1 + self.params[10] * (1 - retrievability)
        elif rating == 4:  # Easy
            factor = 1 + self.params[11] * (1 - retrievability) * self.params[12]
        else:
            factor = 1.0
        
        return max(0.01, factor)  # Minimum factor
    
    def _calculate_interval(self, stability: float, rating: int) -> int:
        """Calculate interval based on stability and rating."""
        # Base interval is stability * factor
        if rating == 2:  # Hard
            factor = self.params[16]  # Parameter 17 (index 16)
        elif rating == 3:  # Good
            factor = 1.0
        elif rating == 4:  # Easy  
            factor = self.params[17]  # Parameter 18 (index 17)
        else:
            factor = 1.0
        
        interval = stability * factor
        return max(1, int(round(interval)))
    
    def calculate_next_intervals(self, state: FSRSState) -> dict[int, int]:
        """Calculate next intervals for each rating (1-4)."""
        intervals = {}
        for rating in range(1, 5):
            temp_state = self.update(state, rating, None, 0)
            intervals[rating] = temp_state.last_interval
        return intervals


def fsrs_state_from_db(db_state) -> FSRSState:
    """Convert database SchedulerState to FSRSState."""
    return FSRSState(
        user_id=db_state.user_id,
        item_id=str(db_state.item_id),
        difficulty=db_state.difficulty,
        stability=db_state.stability,
        due_at=db_state.due_at,
        last_interval=db_state.last_interval,
        reps=db_state.reps,
        lapses=db_state.lapses,
        last_reviewed_at=db_state.last_reviewed_at
    )


def fsrs_state_to_db_dict(fsrs_state: FSRSState) -> dict:
    """Convert FSRSState to database update dictionary."""
    return {
        "difficulty": fsrs_state.difficulty,
        "stability": fsrs_state.stability,
        "due_at": fsrs_state.due_at,
        "last_interval": fsrs_state.last_interval,
        "reps": fsrs_state.reps,
        "lapses": fsrs_state.lapses,
        "last_reviewed_at": fsrs_state.last_reviewed_at,
        "version": 1  # Will be handled by optimistic locking
    }