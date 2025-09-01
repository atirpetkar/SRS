"""Configuration Management for CLI Settings"""

import os
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

console = Console()


class ConfigManager:
    """Manage CLI configuration settings"""

    def __init__(self):
        self.config_dir = Path.home() / ".learning-os"
        self.config_file = self.config_dir / "config.yaml"
        self.ensure_config_dir()

    def ensure_config_dir(self):
        """Ensure config directory exists"""
        self.config_dir.mkdir(exist_ok=True)

    def load_config(self) -> dict[str, Any]:
        """Load configuration from file"""
        if not self.config_file.exists():
            return self.get_default_config()

        try:
            with open(self.config_file) as f:
                config = yaml.safe_load(f) or {}
            # Merge with defaults to ensure all keys exist
            default_config = self.get_default_config()
            default_config.update(config)
            return default_config
        except Exception as e:
            console.print(f"[red]Error loading config: {e}[/red]")
            return self.get_default_config()

    def save_config(self, config: dict[str, Any]):
        """Save configuration to file"""
        try:
            with open(self.config_file, "w") as f:
                yaml.dump(config, f, default_flow_style=False)
        except Exception as e:
            console.print(f"[red]Error saving config: {e}[/red]")
            raise

    def get_default_config(self) -> dict[str, Any]:
        """Get default configuration"""
        return {
            "api": {
                "base_url": os.getenv("LEARNING_OS_API_URL", "http://localhost:8000"),
                "timeout": 30,
            },
            "display": {
                "items_per_page": 20,
                "show_colors": True,
                "show_progress_bars": True,
            },
            "review": {"default_mix_new": 0.2, "auto_submit_timing": True},
            "quiz": {"default_length": 10, "show_correct_answers": True},
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation (e.g., 'api.base_url')"""
        config = self.load_config()
        keys = key.split(".")

        for k in keys:
            if isinstance(config, dict) and k in config:
                config = config[k]
            else:
                return default

        return config

    def set(self, key: str, value: Any):
        """Set configuration value using dot notation"""
        config = self.load_config()
        keys = key.split(".")

        # Navigate to the parent dict
        current = config
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        # Set the value
        current[keys[-1]] = value

        # Save the updated config
        self.save_config(config)

    def reset(self):
        """Reset configuration to defaults"""
        default_config = self.get_default_config()
        self.save_config(default_config)
        console.print("[green]Configuration reset to defaults[/green]")

    def show_all(self):
        """Display all configuration settings"""
        config = self.load_config()
        console.print(yaml.dump(config, default_flow_style=False))


# Global config manager instance
config = ConfigManager()
