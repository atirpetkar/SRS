"""Review Commands - Queue management and review submission"""

import typer
import time
from typing import Optional
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel

from ..client.endpoints import LearningOSClient, LearningOSError
from ..utils.formatting import (
    create_review_queue_table, 
    display_item_content,
    print_success, 
    print_error, 
    print_info
)
from ..utils.config_manager import config

console = Console()
app = typer.Typer(name="review", help="Review queue and submission commands")


@app.command("queue")
def show_queue(
    limit: int = typer.Option(20, "--limit", "-l", help="Number of items to show"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Filter by tags"),
    mix_new: float = typer.Option(0.2, "--mix-new", "-m", help="Proportion of new items (0.0-1.0)"),
):
    """📋 Show items in review queue"""
    base_url = config.get("api.base_url")
    
    try:
        with LearningOSClient(base_url) as client:
            print_info(f"Fetching review queue (limit: {limit}, mix new: {mix_new:.1%})")
            
            queue_data = client.get_review_queue(
                limit=limit, 
                mix_new=mix_new,
                tags=tags
            )
            
            if not queue_data.get("due") and not queue_data.get("new"):
                console.print(Panel(
                    "🎉 [green]No items to review right now![/green]\n\n"
                    "Come back later or add some new content.",
                    title="Empty Queue",
                    border_style="green"
                ))
                return
            
            # Display the queue table
            table = create_review_queue_table(queue_data)
            console.print(table)
            
            # Show summary stats
            due_count = len(queue_data.get("due", []))
            new_count = len(queue_data.get("new", []))
            
            console.print(f"\n📊 Queue Summary: [yellow]{due_count}[/yellow] due, "
                         f"[cyan]{new_count}[/cyan] new items")
            
            # Offer to start a review session
            if (due_count > 0 or new_count > 0) and Confirm.ask("\n🚀 Start reviewing now?"):
                start_review_session(client, queue_data, limit)
                
    except LearningOSError as e:
        print_error(f"Failed to get review queue: {e}")
        raise typer.Exit(1)


@app.command("submit")
def submit_review(
    item_id: str = typer.Argument(..., help="Item ID to review"),
    rating: int = typer.Option(..., "--rating", "-r", help="Rating 1-4 (Again/Hard/Good/Easy)"),
    correct: Optional[bool] = typer.Option(None, "--correct/--incorrect", help="Mark as correct/incorrect"),
):
    """✅ Submit a review for an item"""
    base_url = config.get("api.base_url")
    
    if rating < 1 or rating > 4:
        print_error("Rating must be between 1 and 4")
        raise typer.Exit(1)
    
    rating_names = {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}
    
    try:
        with LearningOSClient(base_url) as client:
            print_info(f"Submitting review: {rating_names[rating]} ({rating})")
            
            result = client.submit_review(
                item_id=item_id,
                rating=rating,
                correct=correct,
                mode="review"
            )
            
            print_success(f"Review submitted! Next due: {result.get('updated_state', {}).get('due_at', 'unknown')}")
            
    except LearningOSError as e:
        print_error(f"Failed to submit review: {e}")
        raise typer.Exit(1)


@app.command("session")
def interactive_session(
    limit: int = typer.Option(10, "--limit", "-l", help="Number of items to review"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Filter by tags"),
    mix_new: float = typer.Option(0.2, "--mix-new", "-m", help="Proportion of new items"),
):
    """🎯 Start an interactive review session"""
    base_url = config.get("api.base_url")
    
    try:
        with LearningOSClient(base_url) as client:
            print_info("Starting interactive review session...")
            
            queue_data = client.get_review_queue(
                limit=limit,
                mix_new=mix_new, 
                tags=tags
            )
            
            start_review_session(client, queue_data, limit)
            
    except LearningOSError as e:
        print_error(f"Failed to start session: {e}")
        raise typer.Exit(1)


def start_review_session(client: LearningOSClient, queue_data: dict, limit: int):
    """Start an interactive review session"""
    all_items = queue_data.get("due", []) + queue_data.get("new", [])
    
    if not all_items:
        console.print("No items to review!")
        return
    
    console.print(Panel(
        f"🎯 [bold cyan]Starting Review Session[/bold cyan]\n\n"
        f"Items to review: [yellow]{len(all_items)}[/yellow]\n"
        f"Type [cyan]'quit'[/cyan] to exit early",
        title="Review Session",
        border_style="cyan"
    ))
    
    reviewed_count = 0
    start_time = time.time()
    
    for i, item in enumerate(all_items[:limit]):
        if reviewed_count >= limit:
            break
            
        console.print(f"\n[bold blue]Item {i+1}/{min(len(all_items), limit)}[/bold blue]")
        console.rule(style="blue")
        
        # Display the item content
        display_item_content(item)
        
        # Get user rating
        while True:
            response = Prompt.ask(
                "\n🎯 Rate this item",
                choices=["1", "2", "3", "4", "quit", "skip"],
                default="3"
            )
            
            if response == "quit":
                console.print(f"\n📊 Session ended early. Reviewed {reviewed_count} items.")
                return
            elif response == "skip":
                console.print("[yellow]⏭️  Skipped[/yellow]")
                break
            else:
                rating = int(response)
                rating_names = {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}
                
                try:
                    # Record timing
                    review_time = int((time.time() - start_time) * 1000)
                    
                    result = client.submit_review(
                        item_id=item["id"],
                        rating=rating,
                        latency_ms=review_time,
                        mode="review"
                    )
                    
                    due_at = result.get("updated_state", {}).get("due_at", "unknown")
                    console.print(f"[green]✅ {rating_names[rating]}! Next due: {due_at}[/green]")
                    reviewed_count += 1
                    start_time = time.time()  # Reset timer for next item
                    break
                    
                except LearningOSError as e:
                    print_error(f"Failed to submit: {e}")
                    if not Confirm.ask("Continue with next item?"):
                        return
                    break
    
    # Session complete
    total_time = time.time() - start_time
    console.print(Panel(
        f"🎉 [green]Session Complete![/green]\n\n"
        f"Items reviewed: [cyan]{reviewed_count}[/cyan]\n"
        f"Time taken: [yellow]{total_time:.1f}s[/yellow]",
        title="Session Summary",
        border_style="green"
    ))
