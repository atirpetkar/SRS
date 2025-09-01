"""Items Commands - Content management and browsing"""


import typer
from rich.console import Console
from rich.panel import Panel

from ..client.endpoints import LearningOSClient, LearningOSError
from ..utils.config_manager import config
from ..utils.formatting import (
    create_items_table,
    display_item_content,
    print_error,
    print_info,
)

console = Console()
app = typer.Typer(name="items", help="Item management and browsing commands")


@app.command("list")
def list_items(
    limit: int = typer.Option(20, "--limit", "-l", help="Number of items to show"),
    type: str | None = typer.Option(None, "--type", "-t", help="Filter by type"),
    tags: str | None = typer.Option(None, "--tags", help="Filter by tags"),
    status: str = typer.Option("published", "--status", "-s", help="Filter by status"),
    offset: int = typer.Option(0, "--offset", "-o", help="Skip first N items"),
):
    """📋 List items in the system"""
    base_url = config.get("api.base_url")

    try:
        with LearningOSClient(base_url) as client:
            print_info(f"Fetching items (limit: {limit}, type: {type or 'all'}, status: {status})")

            items_data = client.list_items(
                type=type,
                tags=tags,
                status=status,
                limit=limit,
                offset=offset
            )

            items = items_data.get("items", [])
            total = items_data.get("total", len(items))

            if not items:
                console.print(Panel(
                    "📭 [yellow]No items found![/yellow]\n\n"
                    f"Filters applied:\n"
                    f"• Type: {type or 'any'}\n"
                    f"• Tags: {tags or 'any'}\n"
                    f"• Status: {status}\n\n"
                    "Try adjusting your filters or add some content!",
                    title="Empty Results",
                    border_style="yellow"
                ))
                return

            # Display items table
            table = create_items_table(items)
            console.print(table)

            # Show pagination info
            showing = min(len(items), limit)
            console.print(f"\n📊 Showing [cyan]{showing}[/cyan] of [yellow]{total}[/yellow] items")

            if offset + limit < total:
                console.print(f"💡 Use [cyan]--offset {offset + limit}[/cyan] to see more")

    except LearningOSError as e:
        print_error(f"Failed to list items: {e}")
        raise typer.Exit(1) from None


@app.command("show")
def show_item(
    item_id: str = typer.Argument(..., help="Item ID to show"),
):
    """🔍 Show detailed information about a specific item"""
    base_url = config.get("api.base_url")

    try:
        with LearningOSClient(base_url) as client:
            print_info(f"Fetching item details: {item_id}")

            item = client.get_item(item_id)

            # Display item metadata
            metadata_content = f"""
🆔 [bold]ID:[/bold] [cyan]{item.get('id', 'unknown')}[/cyan]
📝 [bold]Type:[/bold] [magenta]{item.get('type', 'unknown')}[/magenta]
🏷️ [bold]Tags:[/bold] [green]{', '.join(item.get('tags', []))}[/green]
📊 [bold]Difficulty:[/bold] [yellow]{item.get('difficulty', 'unknown')}[/yellow]
📅 [bold]Created:[/bold] [blue]{item.get('created_at', 'unknown')}[/blue]
👤 [bold]Author:[/bold] [purple]{item.get('created_by', 'unknown')}[/purple]
✅ [bold]Status:[/bold] [{'green' if item.get('status') == 'published' else 'yellow'}]{item.get('status', 'unknown')}[/]
            """

            console.print(Panel(
                metadata_content.strip(),
                title="Item Metadata",
                border_style="blue"
            ))

            # Display content based on type
            console.print("\n[bold blue]Content:[/bold blue]")
            display_item_content(item)

            # Show additional info if available
            media = item.get("media", {})
            if media:
                console.print(f"\n📎 [bold]Media:[/bold] {media}")

            metadata = item.get("metadata", {})
            if metadata:
                console.print(f"\n⚙️ [bold]Metadata:[/bold] {metadata}")

    except LearningOSError as e:
        print_error(f"Failed to get item: {e}")
        raise typer.Exit(1) from None


@app.command("search")
def search_items(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of results to show"),
    type: str | None = typer.Option(None, "--type", "-t", help="Filter by type"),
    tags: str | None = typer.Option(None, "--tags", help="Filter by tags"),
):
    """🔍 Search items by content (when search is implemented)"""
    console.print(Panel(
        f"🔍 [yellow]Search feature coming in Step 7![/yellow]\n\n"
        f"Your query: [cyan]{query}[/cyan]\n"
        f"For now, use [green]learning-os items list[/green] with filters:\n"
        f"• --type {type or 'TYPE'}\n"
        f"• --tags {tags or 'TAGS'}",
        title="Search Not Yet Available",
        border_style="yellow"
    ))


@app.command("stats")
def show_stats():
    """📊 Show item statistics"""
    base_url = config.get("api.base_url")

    try:
        with LearningOSClient(base_url) as client:
            print_info("Fetching item statistics...")

            # Get items with different filters to build stats
            all_items = client.list_items(limit=1000, status="published")  # Get more for stats
            draft_items = client.list_items(limit=1000, status="draft")

            published_items = all_items.get("items", [])
            draft_count = len(draft_items.get("items", []))

            # Calculate stats
            total_published = len(published_items)
            type_counts = {}
            tag_counts = {}
            difficulty_counts = {}

            for item in published_items:
                # Count by type
                item_type = item.get("type", "unknown")
                type_counts[item_type] = type_counts.get(item_type, 0) + 1

                # Count by difficulty
                difficulty = item.get("difficulty", "unknown")
                difficulty_counts[difficulty] = difficulty_counts.get(difficulty, 0) + 1

                # Count tags
                for tag in item.get("tags", []):
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

            # Display stats
            stats_content = f"""
📊 [bold blue]Content Statistics[/bold blue]

📝 [bold]Items by Status:[/bold]
• Published: [green]{total_published}[/green]
• Draft: [yellow]{draft_count}[/yellow]
• Total: [cyan]{total_published + draft_count}[/cyan]

🔤 [bold]Items by Type:[/bold]
{_format_count_list(type_counts)}

🎯 [bold]Items by Difficulty:[/bold]
{_format_count_list(difficulty_counts)}

🏷️ [bold]Top Tags:[/bold]
{_format_count_list(dict(sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]))}
            """

            console.print(Panel(
                stats_content.strip(),
                title="Item Statistics",
                border_style="green"
            ))

    except LearningOSError as e:
        print_error(f"Failed to get statistics: {e}")
        raise typer.Exit(1) from None


def _format_count_list(counts: dict, max_items: int = 10) -> str:
    """Format a count dictionary as a bullet list"""
    if not counts:
        return "• None"

    lines = []
    for key, count in list(counts.items())[:max_items]:
        lines.append(f"• {key}: [yellow]{count}[/yellow]")

    return "\n".join(lines)
