"""Configuration management for Sysforge."""

from pathlib import Path
from typing import Any, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_prefix="SYSFORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Display settings
    default_top_processes: int = Field(10, description="Default number of top processes to show")
    default_sort_by: str = Field("cpu", description="Default sort criteria for processes")

    # Performance settings
    cpu_interval: float = Field(1.0, description="CPU sampling interval in seconds")

    # Output settings
    use_colors: bool = Field(True, description="Use colored output")
    show_timestamps: bool = Field(False, description="Show timestamps in output")

    # Path settings
    config_dir: Optional[Path] = Field(None, description="Configuration directory")
    log_dir: Optional[Path] = Field(None, description="Log directory")

    def __init__(self, **values: Any) -> None:
        """Initialize settings with defaults."""
        super().__init__(**values)

        if self.config_dir is None:
            self.config_dir = Path.home() / ".config" / "sysforge"

        if self.log_dir is None:
            self.log_dir = Path.home() / ".local" / "share" / "sysforge" / "logs"


# Global settings instance
settings = Settings()
