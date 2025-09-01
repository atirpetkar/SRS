"""Quiz Commands - Start, submit, and manage quiz sessions"""

import typer
import time
import json
from typing import Optional, Dict, Any, List
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.progress import Progress, TaskID
from rich.table import Table
from rich import box

from ..client.endpoints import LearningOSClient, LearningOSError
from ..utils.formatting import (
    display_item_content, 
    print_success, 
    print_error, 
    print_info,
    print_warning
)
from ..utils.config_manager import config

console = Console()
app = typer.Typer(name="quiz", help="Quiz session management commands")


@app.command("start")
def start_quiz(
    mode: str = typer.Option("drill", "--mode", "-m", help="Quiz mode: review, drill, mock"),
    length: int = typer.Option(10, "--length", "-l", help="Number of questions"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Filter by tags"),
    type: Optional[str] = typer.Option(None, "--type", help="Filter by item type"),
    time_limit: Optional[int] = typer.Option(None, "--time-limit", help="Time limit in minutes"),
    interactive: bool = typer.Option(True, "--interactive/--non-interactive", help="Interactive mode"),
):
    """🎯 Start a new quiz session"""
    base_url = config.get("api.base_url")
    
    # Validate mode
    valid_modes = ["review", "drill", "mock"]
    if mode not in valid_modes:
        print_error(f"Invalid mode '{mode}'. Valid modes: {', '.join(valid_modes)}")
        raise typer.Exit(1)
    
    try:
        with LearningOSClient(base_url) as client:
            print_info(f"Starting {mode} quiz (length: {length}, tags: {tags}, type: {type})")
            
            # Start the quiz
            quiz_data = client.start_quiz(
                mode=mode,
                tags=tags,
                type=type,
                length=length,
                time_limit_s=time_limit * 60 if time_limit else None
            )
            
            quiz_id = quiz_data.get("quiz_id")
            items = quiz_data.get("items", [])
            
            if not items:
                console.print(Panel(
                    "❌ [red]No items found for quiz![/red]\n\n"
                    f"Try adjusting your filters:\n"
                    f"• Tags: {tags or 'none'}\n"
                    f"• Type: {type or 'any'}\n"
                    f"• Mode: {mode}",
                    title="Quiz Creation Failed",
                    border_style="red"
                ))
                raise typer.Exit(1)
            
            print_success(f"Quiz started! ID: {quiz_id}")
            console.print(f"📝 [cyan]{len(items)}[/cyan] items loaded")
            
            if interactive:
                _run_interactive_quiz(client, quiz_id, items, time_limit)
            else:
                console.print(f"\n🎯 Quiz ID: [yellow]{quiz_id}[/yellow]")
                console.print("Use [cyan]learning-os quiz submit[/cyan] to answer items individually")
                console.print("Use [cyan]learning-os quiz finish[/cyan] when complete")
                
    except LearningOSError as e:
        print_error(f"Failed to start quiz: {e}")
        raise typer.Exit(1)


@app.command("submit")
def submit_answer(
    quiz_id: str = typer.Argument(..., help="Quiz session ID"),
    item_id: str = typer.Argument(..., help="Item ID"),
    answer: str = typer.Argument(..., help="Your answer"),
):
    """✅ Submit an answer for a quiz item"""
    base_url = config.get("api.base_url")
    
    try:
        with LearningOSClient(base_url) as client:
            print_info(f"Submitting answer for item {item_id}")
            
            result = client.submit_quiz_answer(
                quiz_id=quiz_id,
                item_id=item_id,
                response=answer
            )
            
            correct = result.get("correct", False)
            partial = result.get("partial", False)
            rationale = result.get("rationale", "")
            
            if correct:
                print_success("✅ Correct!")
            elif partial:
                print_warning("🟡 Partially correct")
            else:
                print_error("❌ Incorrect")
            
            if rationale:
                console.print(f"💡 [dim]{rationale}[/dim]")
                
    except LearningOSError as e:
        print_error(f"Failed to submit answer: {e}")
        raise typer.Exit(1)


@app.command("finish")
def finish_quiz(
    quiz_id: str = typer.Argument(..., help="Quiz session ID"),
):
    """🏁 Finish a quiz session and show results"""
    base_url = config.get("api.base_url")
    
    try:
        with LearningOSClient(base_url) as client:
            print_info(f"Finishing quiz session {quiz_id}")
            
            result = client.finish_quiz(quiz_id)
            
            _display_quiz_results(result)
            
    except LearningOSError as e:
        print_error(f"Failed to finish quiz: {e}")
        raise typer.Exit(1)


@app.command("practice")
def practice_session(
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Focus on specific tags"),
    type: Optional[str] = typer.Option(None, "--type", help="Focus on specific item type"), 
    difficulty: str = typer.Option("mixed", "--difficulty", "-d", help="Difficulty level: easy, medium, hard, mixed"),
    length: int = typer.Option(15, "--length", "-l", help="Number of questions"),
):
    """🚀 Quick practice session with smart item selection"""
    base_url = config.get("api.base_url")
    
    try:
        with LearningOSClient(base_url) as client:
            console.print(Panel(
                f"🎯 [bold cyan]Practice Session[/bold cyan]\n\n"
                f"• Questions: [yellow]{length}[/yellow]\n"
                f"• Tags: [green]{tags or 'all'}[/green]\n"
                f"• Type: [blue]{type or 'mixed'}[/blue]\n"
                f"• Difficulty: [magenta]{difficulty}[/magenta]",
                title="Starting Practice",
                border_style="cyan"
            ))
            
            # Start a drill quiz
            quiz_data = client.start_quiz(
                mode="drill",
                tags=tags,
                type=type,
                length=length
            )
            
            quiz_id = quiz_data.get("quiz_id")
            items = quiz_data.get("items", [])
            
            if not items:
                print_error("No items available for practice with those filters")
                raise typer.Exit(1)
            
            _run_interactive_quiz(client, quiz_id, items, time_limit=None)
            
    except LearningOSError as e:
        print_error(f"Failed to start practice session: {e}")
        raise typer.Exit(1)


def _run_interactive_quiz(client: LearningOSClient, quiz_id: str, items: List[Dict[str, Any]], time_limit: Optional[int]):
    """Run an interactive quiz session"""
    
    console.print(Panel(
        f"🎯 [bold cyan]Interactive Quiz Session[/bold cyan]\n\n"
        f"Questions: [yellow]{len(items)}[/yellow]\n"
        f"Time limit: [magenta]{f'{time_limit} min' if time_limit else 'None'}[/magenta]\n\n"
        f"Commands: [dim]'skip' to skip, 'quit' to exit early[/dim]",
        title="Quiz Started",
        border_style="cyan"
    ))
    
    start_time = time.time()
    correct_count = 0
    answered_count = 0
    skipped_count = 0
    
    for i, item in enumerate(items):
        console.print(f"\n[bold blue]Question {i+1}/{len(items)}[/bold blue]")
        console.rule(style="blue")
        
        # Check time limit
        if time_limit:
            elapsed_min = (time.time() - start_time) / 60
            remaining_min = time_limit - elapsed_min
            
            if remaining_min <= 0:
                console.print("[red]⏰ Time's up![/red]")
                break
            elif remaining_min <= 2:
                console.print(f"[yellow]⏰ {remaining_min:.1f} minutes remaining[/yellow]")
        
        # Display the question
        display_item_content(item)
        
        # Get answer based on item type
        item_type = item.get("type", "")
        answer = _get_user_answer(item, item_type)
        
        if answer is None:  # User chose to quit
            console.print(f"\n📊 Quiz ended early. Answered {answered_count} questions.")
            break
        elif answer == "SKIP":
            skipped_count += 1
            console.print("[yellow]⏭️ Skipped[/yellow]")
            continue
        
        # Submit the answer
        try:
            result = client.submit_quiz_answer(
                quiz_id=quiz_id,
                item_id=item["id"],
                response=answer
            )
            
            answered_count += 1
            correct = result.get("correct", False)
            partial = result.get("partial", False)
            rationale = result.get("rationale", "")
            
            if correct:
                print_success("✅ Correct!")
                correct_count += 1
            elif partial:
                print_warning("🟡 Partially correct")
                correct_count += 0.5
            else:
                print_error("❌ Incorrect")
            
            if rationale:
                console.print(f"💡 [dim]{rationale}[/dim]")
                
        except LearningOSError as e:
            print_error(f"Failed to submit answer: {e}")
            if not Confirm.ask("Continue with next question?"):
                break
    
    # Finish the quiz
    try:
        result = client.finish_quiz(quiz_id)
        _display_quiz_results(result, answered_count, correct_count, skipped_count, start_time)
    except LearningOSError as e:
        print_error(f"Failed to finish quiz properly: {e}")


def _get_user_answer(item: Dict[str, Any], item_type: str) -> Optional[str]:
    """Get user answer based on item type"""
    
    if item_type == "mcq":
        return _get_mcq_answer(item)
    elif item_type == "cloze":
        return _get_cloze_answer(item)
    elif item_type == "short_answer":
        return _get_short_answer(item)
    elif item_type == "flashcard":
        return _get_flashcard_answer(item)
    else:
        # Generic text answer
        return Prompt.ask("Your answer", default="", show_default=False)


def _get_mcq_answer(item: Dict[str, Any]) -> Optional[str]:
    """Get MCQ answer with letter selection"""
    payload = item.get("payload", {})
    options = payload.get("options", [])
    multiple_select = payload.get("multiple_select", False)
    
    if not options:
        return Prompt.ask("Your answer")
    
    # Show options with letters
    option_letters = []
    for i, option in enumerate(options):
        letter = chr(65 + i)  # A, B, C, D...
        option_letters.append(letter)
        console.print(f"  {letter}) {option.get('text', '')}")
    
    if multiple_select:
        response = Prompt.ask(
            f"\n🔤 Select multiple answers (e.g., 'A,C')",
            default=""
        )
        if response.lower() in ["quit", "skip"]:
            return response.upper() if response.lower() == "skip" else None
        return response.upper()
    else:
        response = Prompt.ask(
            f"\n🔤 Select your answer ({'/'.join(option_letters)})",
            choices=option_letters + ["quit", "skip"],
            default=""
        )
        if response.lower() == "quit":
            return None
        elif response.lower() == "skip":
            return "SKIP"
        return response.upper()


def _get_cloze_answer(item: Dict[str, Any]) -> Optional[str]:
    """Get cloze answer"""
    response = Prompt.ask(
        "🔤 Fill in the blanks (separate multiple answers with commas)",
        default=""
    )
    
    if response.lower() == "quit":
        return None
    elif response.lower() == "skip":
        return "SKIP"
    
    return response


def _get_short_answer(item: Dict[str, Any]) -> Optional[str]:
    """Get short answer"""
    response = Prompt.ask("✍️ Your answer", default="")
    
    if response.lower() == "quit":
        return None
    elif response.lower() == "skip":
        return "SKIP"
    
    return response


def _get_flashcard_answer(item: Dict[str, Any]) -> Optional[str]:
    """Get flashcard answer (self-rating)"""
    payload = item.get("payload", {})
    back = payload.get("back", "")
    
    # Show the back after user thinks about it
    if Confirm.ask("\n🤔 Ready to see the answer?"):
        console.print(Panel(back, title="Answer", border_style="green"))
    
    response = Prompt.ask(
        "Rate your knowledge (1=Again, 2=Hard, 3=Good, 4=Easy)",
        choices=["1", "2", "3", "4", "quit", "skip"],
        default="3"
    )
    
    if response == "quit":
        return None
    elif response == "skip":
        return "SKIP"
    
    return response


def _display_quiz_results(result: Dict[str, Any], answered: int = None, correct: float = None, skipped: int = None, start_time: float = None):
    """Display comprehensive quiz results"""
    
    score = result.get("score", 0)
    breakdown = result.get("breakdown", {})
    
    # Calculate session stats if provided
    session_stats = ""
    if answered is not None and start_time is not None:
        elapsed_time = time.time() - start_time
        accuracy = (correct / answered * 100) if answered > 0 else 0
        
        session_stats = f"""
📊 [bold blue]Session Statistics[/bold blue]

• Questions answered: [cyan]{answered}[/cyan]
• Questions skipped: [yellow]{skipped or 0}[/yellow]
• Accuracy: [{'green' if accuracy >= 80 else 'yellow' if accuracy >= 60 else 'red'}]{accuracy:.1f}%[/]
• Time taken: [magenta]{elapsed_time/60:.1f} minutes[/magenta]
• Avg per question: [blue]{elapsed_time/answered:.1f}s[/blue] (answered only)
"""
    
    # Overall results
    results_content = f"""
🎯 [bold green]Quiz Complete![/bold green]

• Final Score: [yellow]{score:.1%}[/yellow]
• Breakdown: {breakdown}
{session_stats}
🎉 Great job on completing the quiz!
    """
    
    console.print(Panel(
        results_content.strip(),
        title="Quiz Results",
        border_style="green"
    ))
