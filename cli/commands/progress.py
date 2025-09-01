"""Progress Commands - Analytics and learning statistics"""

from typing import Any

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..client.endpoints import LearningOSClient, LearningOSError
from ..utils.config_manager import config
from ..utils.formatting import create_progress_panel, print_error, print_info

console = Console()
app = typer.Typer(name="progress", help="Progress analytics and statistics commands")


@app.command("overview")
def show_overview():
    """📊 Show learning progress overview"""
    base_url = config.get("api.base_url")

    try:
        with LearningOSClient(base_url) as client:
            print_info("Fetching learning progress...")

            progress_data = client.get_progress_overview()

            # Display the progress panel
            panel = create_progress_panel(progress_data)
            console.print(panel)

            # Add suggestions based on progress
            _show_progress_suggestions(progress_data)

    except LearningOSError as e:
        print_error(f"Failed to get progress overview: {e}")
        raise typer.Exit(1) from None


@app.command("weak-areas")
def show_weak_areas(
    top: int = typer.Option(5, "--top", "-t", help="Number of weak areas to show"),
):
    """🎯 Show areas that need more practice"""
    base_url = config.get("api.base_url")

    try:
        with LearningOSClient(base_url) as client:
            print_info(f"Analyzing weak areas (top {top})...")

            weak_areas = client.get_weak_areas(top=top)

            _display_weak_areas_table(weak_areas, top)

    except LearningOSError as e:
        print_error(f"Failed to get weak areas: {e}")
        raise typer.Exit(1) from None


@app.command("forecast")
def show_forecast(
    days: int = typer.Option(7, "--days", "-d", help="Number of days to forecast"),
):
    """📅 Show review forecast for upcoming days"""
    base_url = config.get("api.base_url")

    try:
        with LearningOSClient(base_url) as client:
            print_info(f"Generating forecast for next {days} days...")

            forecast = client.get_forecast(days=days)

            _display_forecast_chart(forecast, days)

    except LearningOSError as e:
        print_error(f"Failed to get forecast: {e}")
        raise typer.Exit(1) from None


@app.command("stats")
def detailed_stats():
    """📈 Show detailed learning statistics"""
    base_url = config.get("api.base_url")

    try:
        with LearningOSClient(base_url) as client:
            print_info("Fetching detailed statistics...")

            # Get all progress data
            overview = client.get_progress_overview()
            weak_areas = client.get_weak_areas(top=10)
            forecast = client.get_forecast(days=30)

            # Display comprehensive stats
            _display_detailed_stats(overview, weak_areas, forecast)

    except LearningOSError as e:
        print_error(f"Failed to get detailed statistics: {e}")
        raise typer.Exit(1) from None


def _show_progress_suggestions(progress_data: dict[str, Any]):
    """Show personalized suggestions based on progress"""
    suggestions = []

    accuracy = progress_data.get("accuracy_7d", 0)
    attempts = progress_data.get("attempts_7d", 0)
    streak = progress_data.get("streak_days", 0)

    if accuracy < 0.7:
        suggestions.append("🎯 Focus on review sessions to improve accuracy")

    if attempts < 7:
        suggestions.append("📚 Try to review more consistently each day")

    if streak == 0:
        suggestions.append("🔥 Start a review streak - consistency is key!")
    elif streak >= 7:
        suggestions.append(f"🎉 Great job on your {streak}-day streak! Keep it up!")

    if attempts == 0:
        suggestions.append("🚀 Start reviewing with: learning-os review queue")

    if suggestions:
        content = "\\n".join([f"• {s}" for s in suggestions])
        console.print(Panel(
            content,
            title="💡 Suggestions",
            border_style="yellow"
        ))


def _display_weak_areas_table(weak_areas: dict[str, Any], top: int):
    """Display weak areas in a formatted table"""
    table = Table(title=f"Top {top} Areas Needing Practice", box=box.ROUNDED)

    table.add_column("Area", style="cyan", width=20)
    table.add_column("Type", justify="center", style="magenta", width=12)
    table.add_column("Accuracy", justify="center", style="red", width=10)
    table.add_column("Attempts", justify="center", style="blue", width=10)
    table.add_column("Priority", justify="center", style="yellow", width=10)

    # Add tag-based weak areas
    for area in weak_areas.get("tags", [])[:top]:
        accuracy = area.get("accuracy", 0)
        attempts = area.get("attempts", 0)
        priority = "🔥 High" if accuracy < 0.5 else ("⚡ Medium" if accuracy < 0.7 else "📝 Low")

        table.add_row(
            area.get("tag", "Unknown"),
            "Tag",
            f"{accuracy:.1%}",
            str(attempts),
            priority
        )

    # Add type-based weak areas
    for area in weak_areas.get("types", [])[:top]:
        accuracy = area.get("accuracy", 0)
        attempts = area.get("attempts", 0)
        priority = "🔥 High" if accuracy < 0.5 else ("⚡ Medium" if accuracy < 0.7 else "📝 Low")

        table.add_row(
            area.get("type", "Unknown"),
            "Type",
            f"{accuracy:.1%}",
            str(attempts),
            priority
        )

    if not weak_areas.get("tags") and not weak_areas.get("types"):
        console.print(Panel(
            "🎉 [green]No weak areas detected![/green]\\n\\n"
            "You're doing great across all content areas.",
            title="Analysis Complete",
            border_style="green"
        ))
    else:
        console.print(table)

        # Show action suggestions
        console.print("\\n💡 [bold yellow]Recommendations:[/bold yellow]")
        console.print("• Use tags to focus practice: [cyan]learning-os review queue --tags <tag>[/cyan]")
        console.print("• Target specific types: [cyan]learning-os quiz start --type <type>[/cyan]")


def _display_forecast_chart(forecast: dict[str, Any], days: int):
    """Display forecast as a chart"""
    forecast_days = forecast.get("by_day", [])

    if not forecast_days:
        console.print(Panel(
            "📅 No reviews scheduled for the forecast period.",
            title="Forecast",
            border_style="blue"
        ))
        return

    # Create forecast table
    table = Table(title=f"Review Forecast - Next {days} Days", box=box.ROUNDED)
    table.add_column("Date", style="cyan", width=12)
    table.add_column("Due Count", justify="center", style="yellow", width=12)
    table.add_column("Workload", justify="left", style="green", width=30)

    max_count = max(day.get("due_count", 0) for day in forecast_days) or 1

    for day in forecast_days:
        date = day.get("date", "")
        due_count = day.get("due_count", 0)

        # Create a simple bar visualization
        bar_length = int((due_count / max_count) * 20) if due_count > 0 else 0
        bar = "█" * bar_length + "░" * (20 - bar_length)

        # Color code the workload
        if due_count == 0:
            workload_style = "[dim]"
        elif due_count <= 5:
            workload_style = "[green]"
        elif due_count <= 15:
            workload_style = "[yellow]"
        else:
            workload_style = "[red]"

        table.add_row(
            date,
            str(due_count),
            f"{workload_style}{bar}[/] ({due_count})"
        )

    console.print(table)

    # Show forecast summary
    total_due = sum(day.get("due_count", 0) for day in forecast_days)
    avg_per_day = total_due / len(forecast_days) if forecast_days else 0

    console.print("\\n📊 Forecast Summary:")
    console.print(f"• Total reviews: [yellow]{total_due}[/yellow]")
    console.print(f"• Average per day: [cyan]{avg_per_day:.1f}[/cyan]")

    # Peak days
    peak_day = max(forecast_days, key=lambda x: x.get("due_count", 0))
    if peak_day.get("due_count", 0) > avg_per_day * 1.5:
        console.print(f"• Peak day: [red]{peak_day.get('date')} ({peak_day.get('due_count')} reviews)[/red]")


def _display_detailed_stats(overview: dict[str, Any], weak_areas: dict[str, Any], forecast: dict[str, Any]):
    """Display comprehensive statistics dashboard"""

    # Main stats panel
    console.print(create_progress_panel(overview))

    # Performance trends (simplified)
    accuracy = overview.get("accuracy_7d", 0)
    attempts = overview.get("attempts_7d", 0)

    performance_content = f"""
📈 [bold blue]Performance Metrics[/bold blue]

• Weekly accuracy: [{'green' if accuracy >= 0.8 else 'yellow' if accuracy >= 0.6 else 'red'}]{accuracy:.1%}[/]
• Daily average: [cyan]{attempts / 7:.1f} reviews[/cyan]
• Response time: [yellow]{overview.get('avg_latency_ms_7d', 0)}ms[/yellow]
    """

    console.print(Panel(performance_content.strip(), title="Performance Analysis", border_style="blue"))

    # Quick forecast summary
    forecast_days = forecast.get("by_day", [])
    if forecast_days:
        next_7_days = sum(day.get("due_count", 0) for day in forecast_days[:7])
        console.print(f"\\n📅 Next 7 days: [yellow]{next_7_days}[/yellow] reviews scheduled")

    # Areas for improvement
    tag_weak_areas = len(weak_areas.get("tags", []))
    type_weak_areas = len(weak_areas.get("types", []))

    if tag_weak_areas > 0 or type_weak_areas > 0:
        console.print(f"🎯 Areas needing attention: [red]{tag_weak_areas}[/red] tags, [red]{type_weak_areas}[/red] types")
