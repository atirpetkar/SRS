"""Rich Formatting Utilities for Beautiful CLI Output"""

from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def print_success(message: str):
    """Print success message with green styling"""
    console.print(f"[green]✓ {message}[/green]")


def print_error(message: str):
    """Print error message with red styling"""
    console.print(f"[red]✗ {message}[/red]")


def print_warning(message: str):
    """Print warning message with yellow styling"""
    console.print(f"[yellow]⚠ {message}[/yellow]")


def print_info(message: str):
    """Print info message with blue styling"""
    console.print(f"[blue]ℹ {message}[/blue]")


def create_items_table(items: list[dict[str, Any]]) -> Table:
    """Create a formatted table for items list"""
    table = Table(title="Items", box=box.ROUNDED)

    table.add_column("ID", justify="left", style="cyan", no_wrap=True)
    table.add_column("Type", justify="center", style="magenta")
    table.add_column("Tags", justify="left", style="green")
    table.add_column("Difficulty", justify="center", style="yellow")
    table.add_column("Content Preview", justify="left", style="white")

    for item in items:
        # Extract content preview based on item type
        preview = _get_content_preview(item)
        tags_str = ", ".join(item.get("tags", []))

        table.add_row(
            item.get("id", "")[:8],  # Short ID
            item.get("type", ""),
            tags_str if tags_str else "—",
            item.get("difficulty", "—"),
            preview,
        )

    return table


def create_review_queue_table(queue_data: dict[str, Any]) -> Table:
    """Create formatted table for review queue"""
    table = Table(title="Review Queue", box=box.ROUNDED)

    table.add_column("Status", justify="center", style="bold")
    table.add_column("ID", justify="left", style="cyan", no_wrap=True)
    table.add_column("Type", justify="center", style="magenta")
    table.add_column("Due", justify="center", style="yellow")
    table.add_column("Content", justify="left", style="white")

    # Add due items
    for item in queue_data.get("due", []):
        preview = _get_content_preview(item)
        table.add_row(
            "📅 Due",
            item.get("id", "")[:8],
            item.get("type", ""),
            item.get("due_at", "now"),
            preview,
        )

    # Add new items
    for item in queue_data.get("new", []):
        preview = _get_content_preview(item)
        table.add_row(
            "🆕 New", item.get("id", "")[:8], item.get("type", ""), "—", preview
        )

    return table


def create_progress_panel(progress_data: dict[str, Any]) -> Panel:
    """Create formatted panel for progress overview"""
    content = f"""
📊 [bold blue]Learning Statistics[/bold blue]

• Reviews (7 days): [green]{progress_data.get("attempts_7d", 0)}[/green]
• Accuracy: [green]{progress_data.get("accuracy_7d", 0):.1%}[/green]
• Avg Response Time: [yellow]{progress_data.get("avg_latency_ms_7d", 0)}ms[/yellow]
• Current Streak: [cyan]{progress_data.get("streak_days", 0)} days[/cyan]
• Total Items: [blue]{progress_data.get("total_items", 0)}[/blue]
• Items Reviewed: [purple]{progress_data.get("reviewed_items", 0)}[/purple]
"""

    return Panel(content, title="Progress Overview", border_style="green")


def display_item_content(item: dict[str, Any]):
    """Display formatted item content based on type"""
    item_type = item.get("type", "")
    payload = item.get("payload", {})

    if item_type == "flashcard":
        _display_flashcard(payload)
    elif item_type == "mcq":
        _display_mcq(payload)
    elif item_type == "cloze":
        _display_cloze(payload)
    elif item_type == "short_answer":
        _display_short_answer(payload)
    else:
        console.print(Panel(str(payload), title=f"Unknown Type: {item_type}"))


def _get_content_preview(item: dict[str, Any]) -> str:
    """Get content preview for table display"""
    item_type = item.get("type", "")
    payload = item.get("payload", {})

    if item_type == "flashcard":
        front = payload.get("front", "")
        return front[:50] + "..." if len(front) > 50 else front
    elif item_type == "mcq":
        stem = payload.get("stem", "")
        return stem[:50] + "..." if len(stem) > 50 else stem
    elif item_type == "cloze":
        text = payload.get("text", "")
        return text[:50] + "..." if len(text) > 50 else text
    elif item_type == "short_answer":
        prompt = payload.get("prompt", "")
        return prompt[:50] + "..." if len(prompt) > 50 else prompt

    return "—"


def _display_flashcard(payload: dict[str, Any]):
    """Display flashcard content"""
    front = payload.get("front", "")
    back = payload.get("back", "")

    console.print(Panel(front, title="📚 Front", border_style="blue"))
    console.print(Panel(back, title="📖 Back", border_style="green"))


def _display_mcq(payload: dict[str, Any]):
    """Display MCQ content"""
    stem = payload.get("stem", "")
    options = payload.get("options", [])

    console.print(Panel(stem, title="❓ Question", border_style="blue"))

    for i, option in enumerate(options):
        letter = chr(65 + i)  # A, B, C, D...
        text = option.get("text", "")
        is_correct = option.get("is_correct", False)
        style = "green" if is_correct else "white"
        console.print(f"  [{style}]{letter}) {text}[/{style}]")


def _display_cloze(payload: dict[str, Any]):
    """Display cloze content"""
    text = payload.get("text", "")
    console.print(Panel(text, title="📝 Fill in the blanks", border_style="yellow"))


def _display_short_answer(payload: dict[str, Any]):
    """Display short answer content"""
    prompt = payload.get("prompt", "")
    expected = payload.get("expected", {})

    console.print(Panel(prompt, title="✏️ Question", border_style="cyan"))
    if expected:
        console.print(f"Expected: [dim]{expected}[/dim]")
