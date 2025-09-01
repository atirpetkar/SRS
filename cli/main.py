"""Learning OS CLI - Main Entry Point"""

import typer
from typing import Optional
from rich.console import Console
from rich.panel import Panel

# Import command modules
from .commands import review, quiz, progress, items, config
from .utils.formatting import print_success, print_error, print_info
from .utils.config_manager import config as config_manager
from .client.endpoints import LearningOSClient

console = Console()

# Create main Typer app
app = typer.Typer(
    name="learning-os",
    help="🎓 Learning OS - Spaced Repetition System CLI",
    rich_markup_mode="rich",
)

# Add command subapps
app.add_typer(review.app, name="review")
app.add_typer(quiz.app, name="quiz")
app.add_typer(progress.app, name="progress")
app.add_typer(items.app, name="items")
app.add_typer(config.app, name="config")


@app.command()
def status():
    """📊 Check system status and connectivity"""
    base_url = config_manager.get("api.base_url")
    print_info(f"Checking connection to: {base_url}")
    
    try:
        with LearningOSClient(base_url) as client:
            health = client.health_check()
            
            console.print(Panel(
                f"🚀 [green]Connected Successfully![/green]\n\n"
                f"• Version: [cyan]{health.get('version', 'unknown')}[/cyan]\n"
                f"• Environment: [yellow]{health.get('environment', 'unknown')}[/yellow]\n"
                f"• API URL: [blue]{base_url}[/blue]",
                title="System Status",
                border_style="green"
            ))
            
    except Exception as e:
        print_error(f"Failed to connect: {e}")
        console.print(Panel(
            f"🚫 [red]Connection Failed[/red]\n\n"
            f"Make sure the Learning OS API is running at:\n"
            f"[blue]{base_url}[/blue]\n\n"
            f"You can update the API URL with:\n"
            f"[cyan]learning-os config set api.base_url <url>[/cyan]",
            title="Connection Error",
            border_style="red"
        ))
        raise typer.Exit(1)


@app.command()
def version():
    """📎 Show CLI version information"""
    from . import __version__
    
    console.print(Panel(
        f"🎓 [bold cyan]Learning OS CLI[/bold cyan]\n\n"
        f"• Version: [green]{__version__}[/green]\n"
        f"• Type: [yellow]Command Line Interface[/yellow]\n"
        f"• Repository: [blue]Learning OS SRS[/blue]",
        title="Version Info",
        border_style="cyan"
    ))


@app.command()
def quickstart():
    """🚀 Quick start guide and setup"""
    console.print(Panel(
        f"🎓 [bold cyan]Learning OS Quick Start[/bold cyan]\n\n"
        f"[bold]1. Check Status[/bold]\n"
        f"   [dim]learning-os status[/dim]\n\n"
        f"[bold]2. View Items[/bold]\n"
        f"   [dim]learning-os items list[/dim]\n\n"
        f"[bold]3. Check Review Queue[/bold]\n"
        f"   [dim]learning-os review queue[/dim]\n\n"
        f"[bold]4. Start Learning[/bold]\n"
        f"   [dim]learning-os quiz start --mode drill[/dim]\n\n"
        f"[bold]5. View Progress[/bold]\n"
        f"   [dim]learning-os progress overview[/dim]\n\n"
        f"[bold yellow]Tip:[/bold yellow] Use [cyan]--help[/cyan] with any command for more options!",
        title="Quick Start Guide",
        border_style="green"
    ))


@app.callback()
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", help="Show version and exit"
    ),
):
    """
    🎓 Learning OS CLI - Interactive Spaced Repetition System
    
    A command-line interface for managing your learning through spaced repetition.
    Review items, take quizzes, track progress, and manage your knowledge base.
    """
    if version:
        from . import __version__
        console.print(f"Learning OS CLI v{__version__}")
        raise typer.Exit()


if __name__ == "__main__":
    app()
