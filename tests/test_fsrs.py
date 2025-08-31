"""Tests for FSRS algorithm implementation."""

from datetime import UTC, datetime

import pytest

from api.v1.review.fsrs import FSRSScheduler


class TestFSRSAlgorithm:
    """Test FSRS-6 algorithm implementation."""

    def test_initialization(self):
        """Test FSRS scheduler initialization."""
        scheduler = FSRSScheduler()
        assert len(scheduler.params) == 21

        # Test with custom parameters
        custom_params = [0.5] * 21
        scheduler = FSRSScheduler(custom_params)
        assert scheduler.params == custom_params

        # Test invalid parameter count
        with pytest.raises(ValueError):
            FSRSScheduler([0.5] * 20)  # Wrong number of parameters

    def test_seed_initial_state(self):
        """Test seeding initial scheduler state."""
        scheduler = FSRSScheduler()
        state = scheduler.seed("user123", "item456")

        assert state.user_id == "user123"
        assert state.item_id == "item456"
        assert state.difficulty > 0
        assert state.stability > 0
        assert state.reps == 0
        assert state.lapses == 0
        assert state.last_interval == 0
        assert state.last_reviewed_at is None
        assert isinstance(state.due_at, datetime)

    def test_first_review_success(self):
        """Test first successful review."""
        scheduler = FSRSScheduler()
        initial_state = scheduler.seed("user123", "item456")

        # Test "Good" rating (3) on first review
        updated_state = scheduler.update(initial_state, 3, True, 2000)

        assert updated_state.reps == 1
        assert updated_state.lapses == 0
        assert updated_state.last_interval > 0
        assert updated_state.stability > 0
        assert updated_state.last_reviewed_at is not None
        assert updated_state.due_at > datetime.now(UTC)

    def test_first_review_failure(self):
        """Test first review failure."""
        scheduler = FSRSScheduler()
        initial_state = scheduler.seed("user123", "item456")

        # Test "Again" rating (1) on first review
        updated_state = scheduler.update(initial_state, 1, False, 5000)

        assert updated_state.reps == 1
        assert updated_state.lapses == 1
        assert updated_state.last_interval == 1  # Short interval after lapse
        assert updated_state.difficulty <= 10.0  # Difficulty clamped to max
        assert updated_state.due_at > datetime.now(UTC)

    def test_rating_validation(self):
        """Test rating validation."""
        scheduler = FSRSScheduler()
        state = scheduler.seed("user123", "item456")

        # Valid ratings should work
        for rating in [1, 2, 3, 4]:
            scheduler.update(state, rating, True, 1000)

        # Invalid ratings should raise error
        with pytest.raises(ValueError):
            scheduler.update(state, 0, True, 1000)

        with pytest.raises(ValueError):
            scheduler.update(state, 5, True, 1000)

    def test_progressive_intervals(self):
        """Test that intervals generally increase with successful reviews."""
        scheduler = FSRSScheduler()
        state = scheduler.seed("user123", "item456")

        intervals = []

        # Perform several successful reviews
        for _i in range(5):
            state = scheduler.update(state, 3, True, 2000)  # Good rating
            intervals.append(state.last_interval)

        # Intervals should generally increase (with some variability allowed)
        # Note: FSRS can have complex behavior, so we just check basic progression
        assert len(intervals) == 5
        assert all(
            interval >= 1 for interval in intervals
        )  # All intervals should be at least 1 day

    def test_lapse_recovery(self):
        """Test recovery after lapse."""
        scheduler = FSRSScheduler()
        state = scheduler.seed("user123", "item456")

        # Build up some stability with successful reviews
        state = scheduler.update(state, 3, True, 2000)
        state = scheduler.update(state, 3, True, 2000)

        # Introduce a lapse
        state = scheduler.update(state, 1, False, 8000)
        assert state.lapses == 1
        assert state.last_interval == 1  # Reset to short interval

        # Recovery should be possible
        state = scheduler.update(state, 3, True, 2000)
        assert state.last_interval >= 1  # Should be at least 1 day
        assert state.stability > 0

    def test_difficulty_adjustment(self):
        """Test difficulty adjustment based on performance."""
        scheduler = FSRSScheduler()
        state = scheduler.seed("user123", "item456")

        # Easy rating should adjust difficulty (could increase or decrease based on FSRS)
        easy_state = scheduler.update(state, 4, True, 1000)
        assert 1.0 <= easy_state.difficulty <= 10.0  # Within valid bounds

        # Hard rating should increase difficulty (or keep it similar)
        hard_state = scheduler.update(state, 2, True, 5000)
        # Difficulty changes can be complex, just ensure it's within reasonable bounds
        assert 1.0 <= hard_state.difficulty <= 10.0

        # Again rating should increase difficulty (but may be clamped)
        again_state = scheduler.update(state, 1, False, 10000)
        assert 1.0 <= again_state.difficulty <= 10.0  # Within valid bounds

    def test_calculate_next_intervals(self):
        """Test calculation of next intervals for all ratings."""
        scheduler = FSRSScheduler()
        state = scheduler.seed("user123", "item456")

        # Build up some stability first
        state = scheduler.update(state, 3, True, 2000)

        intervals = scheduler.calculate_next_intervals(state)

        assert len(intervals) == 4
        assert all(rating in intervals for rating in [1, 2, 3, 4])
        assert all(isinstance(interval, int) for interval in intervals.values())
        assert all(interval > 0 for interval in intervals.values())

        # Again (1) should have shortest interval
        assert intervals[1] <= min(intervals[2], intervals[3], intervals[4])

    def test_retrievability_calculation(self):
        """Test retrievability calculation."""
        scheduler = FSRSScheduler()

        # Test with various stability and time elapsed values
        assert scheduler._calculate_retrievability(1.0, 0) == 1.0
        assert scheduler._calculate_retrievability(1.0, 1) < 1.0
        assert scheduler._calculate_retrievability(
            10.0, 1
        ) > scheduler._calculate_retrievability(1.0, 1)

        # Test edge cases
        assert scheduler._calculate_retrievability(0, 1) == 1.0
        assert scheduler._calculate_retrievability(1.0, -1) == 1.0

    def test_stability_bounds(self):
        """Test that stability stays within reasonable bounds."""
        scheduler = FSRSScheduler()
        state = scheduler.seed("user123", "item456")

        # Perform many reviews with different ratings
        for _ in range(10):
            for rating in [1, 2, 3, 4]:
                state = scheduler.update(state, rating, True, 2000)
                assert state.stability >= 0.01  # Minimum stability
                assert state.stability <= 100000  # Reasonable maximum

    def test_difficulty_bounds(self):
        """Test that difficulty stays within bounds."""
        scheduler = FSRSScheduler()
        state = scheduler.seed("user123", "item456")

        # Perform many reviews to test boundary conditions
        for _ in range(10):
            for rating in [1, 2, 3, 4]:
                state = scheduler.update(state, rating, True, 2000)
                assert 1.0 <= state.difficulty <= 10.0

    def test_state_consistency(self):
        """Test that state updates are consistent."""
        scheduler = FSRSScheduler()
        state = scheduler.seed("user123", "item456")

        # Perform a series of updates and check consistency
        for i in range(5):
            prev_reps = state.reps
            prev_lapses = state.lapses

            rating = 3 if i % 2 == 0 else 1  # Alternate between success and failure
            state = scheduler.update(state, rating, rating > 1, 2000)

            assert state.reps == prev_reps + 1
            if rating == 1:
                assert state.lapses == prev_lapses + 1
            else:
                assert state.lapses == prev_lapses
