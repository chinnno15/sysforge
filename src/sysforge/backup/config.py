"""Configuration models for user backup and restore."""

import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from platformdirs import user_config_dir
from pydantic import BaseModel, Field, field_validator


class CompressionFormat(str, Enum):
    """Supported compression formats."""
    ZSTD = "zstd"
    LZ4 = "lz4"
    GZIP = "gzip"


class ConflictResolution(str, Enum):
    """Conflict resolution strategies for restore operations."""
    PROMPT = "prompt"
    OVERWRITE = "overwrite"
    SKIP = "skip"
    BACKUP = "backup"


class CompressionConfig(BaseModel):
    """Compression settings."""
    format: CompressionFormat = CompressionFormat.ZSTD
    level: int = Field(default=3, ge=1, le=22)

    @field_validator('level')
    @classmethod
    def validate_level(cls, v: int, info: Any) -> int:
        """Validate compression level based on format."""
        # Get format from other fields
        format_type = info.data.get('format', CompressionFormat.ZSTD) if info.data else CompressionFormat.ZSTD

        if format_type == CompressionFormat.ZSTD and not (1 <= v <= 22):
            raise ValueError("ZSTD compression level must be between 1 and 22")
        elif format_type == CompressionFormat.GZIP and not (1 <= v <= 9):
            raise ValueError("GZIP compression level must be between 1 and 9")
        elif format_type == CompressionFormat.LZ4 and not (1 <= v <= 12):
            raise ValueError("LZ4 compression level must be between 1 and 12")

        return v


class TargetConfig(BaseModel):
    """Target configuration for backup operations."""
    base_path: str = "~"
    output_path: str = "~/.config/sysforge/backups/backup-{timestamp}.tar.zst"

    def get_base_path(self) -> Path:
        """Get expanded base path."""
        return Path(os.path.expanduser(self.base_path))

    def get_output_path(self, timestamp: Optional[datetime] = None) -> Path:
        """Get expanded output path with timestamp."""
        if timestamp is None:
            timestamp = datetime.now()

        formatted_path = self.output_path.format(
            timestamp=timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        )
        return Path(os.path.expanduser(formatted_path))


class GitConfig(BaseModel):
    """Git repository handling configuration."""
    include_repos: bool = True
    respect_gitignore: bool = True  # Respect .gitignore by default for sensible backup sizes
    include_git_dir: bool = True  # Always include .git directory for complete restoration
    backup_complete_git: bool = True  # New field to ensure complete git backup
    gitignore_override_patterns: List[str] = Field(default_factory=lambda: [
        "**/.env*",      # Environment files
        "**/*.env",      # Alternative env format
        "**/.env.*",     # Environment files with suffixes (.env.local, .env.prod, etc.)
        "**/secrets.*",  # Secret files
        "**/config.*",   # Config files that might be important
    ])


class RestoreConfig(BaseModel):
    """Restore operation configuration."""
    conflict_resolution: ConflictResolution = ConflictResolution.PROMPT
    preserve_permissions: bool = True
    create_backup_on_conflict: bool = True
    backup_suffix: str = ".backup-{timestamp}"

    def get_backup_suffix(self, timestamp: Optional[datetime] = None) -> str:
        """Get backup suffix with timestamp."""
        if timestamp is None:
            timestamp = datetime.now()

        return self.backup_suffix.format(
            timestamp=timestamp.strftime("%Y%m%d_%H%M%S")
        )


class BackupConfig(BaseModel):
    """Complete backup configuration."""
    compression: CompressionConfig = CompressionConfig()
    target: TargetConfig = TargetConfig()
    git: GitConfig = GitConfig()
    restore: RestoreConfig = RestoreConfig()

    # Whitelist of dot directories at root of home directory that should be included
    dot_directory_whitelist: List[str] = Field(default_factory=lambda: [
        ".ssh",           # SSH keys and config
        ".gnupg",         # GPG keys
        ".aws",           # AWS credentials (will be sub-filtered)
        ".kube",          # Kubernetes config (will be sub-filtered)
        ".config",        # User configurations (will be sub-filtered)
        ".emacs.d",       # Emacs configuration
    ])
    
    include_patterns: List[str] = Field(default_factory=lambda: [
        # Programming and code files
        "**/*.py", "**/*.js", "**/*.ts", "**/*.tsx", "**/*.jsx",
        "**/*.java", "**/*.cpp", "**/*.c", "**/*.h", "**/*.rs", "**/*.go",
        "**/*.md", "**/*.rst", "**/*.txt",
        "**/*.yaml", "**/*.yml", "**/*.json", "**/*.toml", "**/*.ini", "**/*.cfg",
        "**/src/**", "**/docs/**", "**/doc/**", "**/tests/**", "**/test/**",
        "**/*.sql", "**/*.sh", "**/*.bash", "**/*.zsh",
        "**/Dockerfile*", "**/docker-compose*", "**/Makefile*", "**/.env*",
        # Image files
        "**/*.png", "**/*.jpg", "**/*.jpeg", "**/*.gif", "**/*.bmp", "**/*.svg", "**/*.webp",
        "**/*.ico", "**/*.tiff", "**/*.tif",
        # Document files
        "**/*.pdf", "**/*.doc", "**/*.docx", "**/*.odt", "**/*.rtf",
        "**/*.xls", "**/*.xlsx", "**/*.ods", "**/*.csv",
        "**/*.ppt", "**/*.pptx", "**/*.odp",
        # Important directories that may contain user files
        "**/Pictures/**", "**/Screenshots/**", "**/Documents/**", "**/Desktop/**",
        # Important configuration files (not directories)
        "**/.bashrc", "**/.zshrc", "**/.profile", "**/.vimrc", "**/.gitconfig",
        "**/.gitignore", "**/.dockerignore",
        "**/.bash_profile", "**/.bash_aliases", "**/.bash_history",
        "**/.zsh_history", "**/.zprofile",
        "**/.tmux.conf", "**/.screenrc",
        "**/.inputrc", "**/.curlrc", "**/.wgetrc",
        "**/.selected_editor", "**/.lesshst", "**/.emacs",
        # Sub-filtered content from whitelisted dot directories
        "**/.config/**/*.conf", "**/.config/**/*.ini", "**/.config/**/*.yaml", 
        "**/.config/**/*.yml", "**/.config/**/*.json", "**/.config/**/*.toml",
        "**/.config/**/*.desktop", "**/.config/**/settings", "**/.config/**/config",
        "**/.config/nvim/**", "**/.config/git/**", "**/.config/gh/**", 
        "**/.config/htop/**", "**/.config/fish/**",
        "**/.ssh/**", "**/.gnupg/**", 
        "**/.aws/config", "**/.aws/credentials",  # Only config files, not cache
        "**/.kube/config",  # Only the config, not cache directories
        "**/.emacs.d/init.el", "**/.emacs.d/config/**"  # Emacs configs, not packages
    ])

    exclude_patterns: List[str] = Field(default_factory=lambda: [
        # Build artifacts and caches (applied outside git repos only)
        "**/node_modules/**", "**/__pycache__/**", "**/*.pyc", "**/*.pyo",
        "**/.venv/**", "**/venv/**", "**/target/**", "**/build/**", "**/dist/**",
        "**/.pytest_cache/**", "**/.mypy_cache/**", "**/.ruff_cache/**",
        "**/*.egg-info/**", "**/coverage.xml", "**/.coverage", "**/.tox/**", "**/htmlcov/**",
        # IDE and editor files
        "**/.vscode/**", "**/.idea/**", "**/*.swp", "**/*.swo", "**/*~",
        # OS files
        "**/.DS_Store", "**/Thumbs.db",
        # Temporary files and directories
        "**/*.tmp", "**/*.temp", "**/temp/**"
    ])

    always_exclude: List[str] = Field(default_factory=lambda: [
        # OS files
        "**/.DS_Store", "**/Thumbs.db", "**/*.tmp", "**/*.temp",
        "**/*.log", "**/core", "**/core.*",
        
        # Package managers and stores
        "**/snap/**",  # Snap packages
        "**/flatpak/**",  # Flatpak
        
        # Game and app directories
        "**/Games/**",  # Games directory
        
        # Virtual machines and containers
        "**/VirtualBox VMs/**",
        "**/vmware/**",
        
        # Database files
        "**/*.db",
        "**/*.sqlite",
        "**/*.sqlite3",
        "**/*.db-wal",
        "**/*.db-shm",
        
        # Temporary and build directories
        # Exclude common tmp directories but not system /tmp for tests
        "**/app-tmp/**", "**/application-tmp/**",
        "**/temp/**",
        "**/build/**",
        "**/dist/**",
        "**/target/**",
        "**/__pycache__/**",
        "**/node_modules/**",
        
        # Browser and application cache exclusions for performance
        "**/.config/*/Cache/**", "**/.config/*/CacheStorage/**", "**/.config/*/Code Cache/**",
        "**/.config/BraveSoftware/**", "**/.config/google-chrome/**/Cache/**",
        "**/.config/chromium/**/Cache/**", "**/.config/Code/Cache/**",
        
        # Large binary files that shouldn't be backed up
        "**/*.iso",
        "**/*.img",
        "**/*.vmdk",
        "**/*.vdi",
        "**/*.qcow2",
        
        # Trash and temporary files
        "**/lost+found/**",
        
        # System directories that shouldn't be backed up
        "**/proc/**",
        "**/sys/**",
        "**/dev/**",
        "**/run/**",
        "**/mnt/**",
        "**/media/**",
        
        # Additional caches (keep specific cache patterns that don't start with dots)
        "**/CachedData/**",
        "**/ShaderCache/**",
        "**/*_cache/**",
        "**/*.cache/**"
    ])

    max_file_size: str = "100MB"

    # Parallel processing configuration
    max_workers: int = Field(default_factory=lambda: max(1, (os.cpu_count() or 2) // 2))
    enable_parallel_processing: bool = True

    def get_max_file_size_bytes(self) -> int:
        """Convert max_file_size string to bytes."""
        size_str = self.max_file_size.upper()

        if size_str.endswith('KB'):
            return int(size_str[:-2]) * 1024
        elif size_str.endswith('MB'):
            return int(size_str[:-2]) * 1024 * 1024
        elif size_str.endswith('GB'):
            return int(size_str[:-2]) * 1024 * 1024 * 1024
        else:
            # Assume bytes
            return int(size_str)


class ConfigManager:
    """Manages configuration loading and merging."""

    CONFIG_DIR = Path(user_config_dir("sysforge", ensure_exists=True))
    USER_CONFIG_FILE = CONFIG_DIR / "user-backup.yaml"
    PROFILES_DIR = CONFIG_DIR / "profiles"
    BACKUPS_DIR = CONFIG_DIR / "backups"

    @classmethod
    def ensure_config_dirs(cls) -> None:
        """Ensure configuration directories exist."""
        cls.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cls.PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        cls.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_default_config(cls) -> BackupConfig:
        """Get the default configuration."""
        return BackupConfig()

    @classmethod
    def load_user_config(cls) -> Optional[Dict[str, Any]]:
        """Load user configuration from ~/.config/sysforge/user-backup.yaml."""
        if not cls.USER_CONFIG_FILE.exists():
            return None

        try:
            with open(cls.USER_CONFIG_FILE) as f:
                result = yaml.safe_load(f)
                return result if isinstance(result, dict) else None
        except Exception:
            return None

    @classmethod
    def load_profile_config(cls, profile_name: str) -> Optional[Dict[str, Any]]:
        """Load configuration from a named profile."""
        profile_file = cls.PROFILES_DIR / f"{profile_name}.yaml"
        if not profile_file.exists():
            return None

        try:
            with open(profile_file) as f:
                result = yaml.safe_load(f)
                return result if isinstance(result, dict) else None
        except Exception:
            return None

    @classmethod
    def load_config_file(cls, config_path: Path) -> Optional[Dict[str, Any]]:
        """Load configuration from a specific file."""
        if not config_path.exists():
            return None

        try:
            with open(config_path) as f:
                result = yaml.safe_load(f)
                return result if isinstance(result, dict) else None
        except Exception:
            return None

    @classmethod
    def merge_configs(cls, *configs: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge multiple configuration dictionaries."""
        result: Dict[str, Any] = {}

        for config in configs:
            if config is not None:
                cls._deep_merge(result, config)

        return result

    @classmethod
    def _deep_merge(cls, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """Recursively merge source into target."""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                cls._deep_merge(target[key], value)
            else:
                target[key] = value

    @classmethod
    def load_effective_config(
        cls,
        profile: Optional[str] = None,
        config_file: Optional[Path] = None,
        overrides: Optional[Dict[str, Any]] = None
    ) -> BackupConfig:
        """Load the effective configuration with proper hierarchy."""
        cls.ensure_config_dirs()

        # Start with default config
        default_config = cls.get_default_config().model_dump()

        # Load user config
        user_config = cls.load_user_config()

        # Load profile config
        profile_config = None
        if profile:
            profile_config = cls.load_profile_config(profile)

        # Load config file
        file_config = None
        if config_file:
            file_config = cls.load_config_file(config_file)

        # Merge configs: default -> user -> profile -> file -> overrides
        merged_config = cls.merge_configs(
            default_config,
            user_config,
            profile_config,
            file_config,
            overrides
        )

        return BackupConfig(**merged_config)

    @classmethod
    def save_user_config(cls, config: Dict[str, Any]) -> None:
        """Save user configuration to file."""
        cls.ensure_config_dirs()

        with open(cls.USER_CONFIG_FILE, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    @classmethod
    def save_profile_config(cls, profile_name: str, config: Dict[str, Any]) -> None:
        """Save profile configuration to file."""
        cls.ensure_config_dirs()

        profile_file = cls.PROFILES_DIR / f"{profile_name}.yaml"
        with open(profile_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    @classmethod
    def list_profiles(cls) -> List[str]:
        """List available configuration profiles."""
        cls.ensure_config_dirs()

        profiles = []
        for file_path in cls.PROFILES_DIR.glob("*.yaml"):
            profiles.append(file_path.stem)

        return sorted(profiles)

    @classmethod
    def list_backups(cls) -> List[Path]:
        """List available backup files."""
        cls.ensure_config_dirs()

        backups: List[Path] = []
        for pattern in ["*.tar.zst", "*.tar.lz4", "*.tar.gz", "*.tar"]:
            backups.extend(cls.BACKUPS_DIR.glob(pattern))

        return sorted(backups, key=lambda p: p.stat().st_mtime, reverse=True)
