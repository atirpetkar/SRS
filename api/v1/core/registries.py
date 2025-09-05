from typing import Any, Generic, Protocol, TypeVar

# Base registry implementation
T = TypeVar("T")


class Registry(Generic[T]):
    """Generic registry for pluggable implementations."""

    def __init__(self, name: str):
        self.name = name
        self._implementations: dict[str, T] = {}
        self._frozen = False

    def register(self, name: str, implementation: T) -> None:
        """Register an implementation with a given name."""
        if self._frozen:
            raise RuntimeError(
                f"Cannot register '{name}' in {self.name.lower()} registry: "
                "registry is frozen in production mode"
            )
        self._implementations[name] = implementation

    def get(self, name: str) -> T:
        """Get an implementation by name."""
        if name not in self._implementations:
            raise KeyError(
                f"No {self.name.lower()} implementation registered with name: {name}"
            )
        return self._implementations[name]

    def list(self) -> list[str]:
        """List all registered implementation names."""
        return list(self._implementations.keys())

    def freeze(self) -> None:
        """Freeze the registry to prevent further modifications."""
        self._frozen = True

    def is_frozen(self) -> bool:
        """Check if the registry is frozen."""
        return self._frozen


# Item Type Registry - validates and renders item payloads
class ItemTypeValidator(Protocol):
    """Protocol for item type validators."""

    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize item payload."""
        ...

    def render(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Render item for display/practice."""
        ...


class ItemTypeRegistry(Registry[ItemTypeValidator]):
    """Registry for item type validators (flashcard, mcq, cloze, short_answer)."""

    def __init__(self):
        super().__init__("ItemType")


# Grader Registry - objective scoring for different item types
class Grader(Protocol):
    """Protocol for graders that score responses."""

    def grade(
        self, item_payload: dict[str, Any], response: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Grade a response and return score information.

        Returns:
        {
            "correct": bool,
            "partial": Optional[float],  # 0.0 to 1.0 for partial credit
            "rationale": Optional[str],  # Explanation of scoring
            "normalized_answer": Optional[str]  # Cleaned up response
        }
        """
        ...


class GraderRegistry(Registry[Grader]):
    """Registry for graders (mcq, cloze, short_answer, flashcard_rating)."""

    def __init__(self):
        super().__init__("Grader")


# Scheduler Registry - SRS algorithms
class SchedulerState(Protocol):
    """Protocol for scheduler state."""

    user_id: str
    item_id: str
    due_at: Any  # datetime
    stability: float
    difficulty: float
    last_interval: int
    reps: int
    lapses: int


class Scheduler(Protocol):
    """Protocol for SRS schedulers."""

    def seed(self, user_id: str, item_id: str) -> SchedulerState:
        """Initialize scheduler state for a new user/item pair."""
        ...

    def update(
        self, state: SchedulerState, rating: int, correct: bool | None, latency_ms: int
    ) -> SchedulerState:
        """Update scheduler state based on review results."""
        ...


class SchedulerRegistry(Registry[Scheduler]):
    """Registry for SRS schedulers (fsrs_v7, etc.)."""

    def __init__(self):
        super().__init__("Scheduler")


# Importer Registry - parse external content into items
class Importer(Protocol):
    """Protocol for content importers."""

    def parse(self, data: str | bytes, **kwargs: Any) -> list[dict[str, Any]]:
        """
        Parse external data into item dictionaries.

        Returns list of items in format:
        {
            "type": str,
            "payload": Dict[str, Any],
            "tags": List[str],
            "difficulty": Optional[str],
            "metadata": Dict[str, Any]
        }
        """
        ...


class ImporterRegistry(Registry[Importer]):
    """Registry for importers (markdown, csv, json)."""

    def __init__(self):
        super().__init__("Importer")


# Generator Registry - create items from text
class Generator(Protocol):
    """Protocol for content generators."""

    def generate(
        self,
        text: str,
        item_types: list[str] | None = None,
        count: int | None = None,
        difficulty: str | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """
        Generate items from input text.

        Returns list of generated items with same format as Importer.
        """
        ...


class GeneratorRegistry(Registry[Generator]):
    """Registry for generators (basic_rules, llm_upgrade, etc.)."""

    def __init__(self):
        super().__init__("Generator")


# Vectorizer Registry - compute embeddings
class Vectorizer(Protocol):
    """Protocol for embedding vectorizers."""

    def vectorize(self, text: str) -> list[float]:
        """Compute embedding vector for text."""
        ...

    def get_dimension(self) -> int:
        """Get the dimension of vectors produced."""
        ...

    def get_model_version(self) -> str:
        """Get the model version identifier."""
        ...


class VectorizerRegistry(Registry[Vectorizer]):
    """Registry for vectorizers (stub, sbert, openai)."""

    def __init__(self):
        super().__init__("Vectorizer")


# Job Registry - background processing handlers
class JobHandler(Protocol):
    """Protocol for job handlers that process background tasks."""

    async def handle(
        self,
        session: Any,  # AsyncSession
        principal_ctx: Any,  # Principal context for org/user isolation
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Handle a background job.

        Args:
            session: Database session for job processing
            principal_ctx: Principal context with org_id/user_id for isolation
            payload: Job-specific parameters

        Returns:
            Optional result dictionary to store with completed job
        """
        ...


class JobRegistry(Registry[JobHandler]):
    """Registry for background job handlers."""

    def __init__(self):
        super().__init__("Job")


# Global registry instances (singletons)
item_type_registry = ItemTypeRegistry()
grader_registry = GraderRegistry()
scheduler_registry = SchedulerRegistry()
importer_registry = ImporterRegistry()
generator_registry = GeneratorRegistry()
vectorizer_registry = VectorizerRegistry()
job_registry = JobRegistry()
