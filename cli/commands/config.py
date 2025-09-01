"""Configuration Commands - CLI settings management"""

import typer
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from ..utils.config_manager import config
from ..utils.formatting import print_success, print_error, print_info

console = Console()
app = typer.Typer(name="config", help="CLI configuration management")


@app.command("set")
def set_config(
    key: str = typer.Argument(..., help="Configuration key (e.g., 'api.base_url')"),
    value: str = typer.Argument(..., help="Configuration value"),
):
    """⚙️ Set a configuration value"""
    try:
        # Validate common keys
        if key == "api.base_url" and not value.startswith(("http://", "https://")):
            print_error("API base URL must start with http:// or https://")
            raise typer.Exit(1)
        
        if key.endswith(".timeout") and not value.isdigit():
            print_error("Timeout values must be numeric (seconds)")
            raise typer.Exit(1)
        
        config.set(key, value)
        print_success(f"Set {key} = {value}")
        
        # Show helpful tips for common keys
        if key == "api.base_url":
            print_info("Test connection with: learning-os status")
        elif key.startswith("display."):
            print_info("Display changes will take effect on next command")
            
    except Exception as e:
        print_error(f"Failed to set configuration: {e}")
        raise typer.Exit(1)


@app.command("get")
def get_config(
    key: Optional[str] = typer.Argument(None, help="Configuration key (optional - shows all if omitted)"),
):
    """📋 Get configuration value(s)"""
    try:
        if key:
            value = config.get(key)
            if value is None:
                console.print(f"[yellow]Key '{key}' not found[/yellow]")
                console.print("Use [cyan]learning-os config show[/cyan] to see all available keys")
            else:
                console.print(f"[cyan]{key}[/cyan] = [yellow]{value}[/yellow]")
        else:
            show_all_config()
            
    except Exception as e:
        print_error(f"Failed to get configuration: {e}")
        raise typer.Exit(1)


@app.command("show")
def show_all_config():
    """📊 Show all configuration settings"""
    try:
        console.print(Panel(
            "[bold cyan]Learning OS CLI Configuration[/bold cyan]\n\n"
            "[dim]Configuration is stored in ~/.learning-os/config.yaml[/dim]",
            title="Configuration",
            border_style="blue"
        ))
        
        config_data = config.load_config()
        _display_config_section(config_data, "")
        
    except Exception as e:
        print_error(f"Failed to show configuration: {e}")
        raise typer.Exit(1)


@app.command("reset")
def reset_config():
    """🔄 Reset configuration to defaults"""
    if not Confirm.ask("⚠️ This will reset ALL configuration to defaults. Continue?"):
        console.print("Configuration reset cancelled.")
        return
    
    try:
        config.reset()
        print_success("Configuration reset to defaults")
        console.print("💡 Use [cyan]learning-os config show[/cyan] to see current settings")
        
    except Exception as e:
        print_error(f"Failed to reset configuration: {e}")
        raise typer.Exit(1)


@app.command("edit")
def edit_config():
    """✏️ Open configuration file in default editor"""
    import os
    import subprocess
    
    config_file = config.config_file
    
    if not config_file.exists():
        config.load_config()  # This will create the file with defaults
    
    try:
        # Try different editors
        editors = [
            os.environ.get("EDITOR"),
            "code",  # VS Code
            "vim",
            "nano",
            "notepad"  # Windows
        ]
        
        for editor in editors:
            if editor:
                try:
                    subprocess.run([editor, str(config_file)], check=True)
                    print_success(f"Opened configuration file with {editor}")
                    return
                except (subprocess.CalledProcessError, FileNotFoundError):
                    continue
        
        # If no editor worked, just show the path
        console.print(f"Could not find a suitable editor.")
        console.print(f"Please edit manually: [cyan]{config_file}[/cyan]")
        
    except Exception as e:
        print_error(f"Failed to open editor: {e}")
        console.print(f"Configuration file location: [cyan]{config_file}[/cyan]")


@app.command("path")
def show_config_path():
    """📁 Show configuration file path"""
    console.print(f"Configuration file: [cyan]{config.config_file}[/cyan]")
    console.print(f"Configuration directory: [blue]{config.config_dir}[/blue]")
    
    if config.config_file.exists():
        size = config.config_file.stat().st_size
        console.print(f"File size: [yellow]{size} bytes[/yellow]")
    else:
        console.print("[dim]Configuration file will be created on first use[/dim]")


def _display_config_section(data, prefix: str, indent: int = 0):
    """Recursively display configuration sections"""
    indent_str = "  " * indent
    
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        
        if isinstance(value, dict):
            console.print(f"{indent_str}[bold blue]{key}:[/bold blue]")
            _display_config_section(value, full_key, indent + 1)
        else:
            # Color-code values based on type/content
            if isinstance(value, bool):
                color = "green" if value else "red"
                display_value = f"[{color}]{value}[/{color}]"
            elif isinstance(value, (int, float)):
                display_value = f"[cyan]{value}[/cyan]"
            elif isinstance(value, str) and value.startswith("http"):
                display_value = f"[blue]{value}[/blue]"
            else:
                display_value = f"[yellow]{value}[/yellow]"
            
            console.print(f"{indent_str}[cyan]{key}[/cyan]: {display_value}")
            console.print(f"{indent_str}[dim]  → set with: learning-os config set {full_key} <value>[/dim]")
