"""End-to-end integration tests for backup and restore functionality."""

import json
import tempfile
from pathlib import Path

import git
from rich.console import Console

from sysforge.backup.config import BackupConfig, ConfigManager
from sysforge.backup.core import create_backup
from sysforge.backup.restore import restore_backup


class TestEndToEndBackupRestore:
    """Test complete backup and restore workflow."""

    def setup_method(self):
        """Set up test fixtures."""
        import os

        devnull = open(os.devnull, "w")
        self.console = Console(file=devnull, quiet=True)

    def create_test_workspace(self, base_path: Path):
        """Create a test workspace with various file types."""
        # Create directory structure
        (base_path / "src").mkdir()
        (base_path / "docs").mkdir()
        (base_path / "build").mkdir()
        (base_path / "node_modules").mkdir()
        (base_path / "__pycache__").mkdir()

        # Create source files
        (base_path / "src" / "main.py").write_text(
            "def main():\n    print('Hello World')"
        )
        (base_path / "src" / "utils.py").write_text("def helper():\n    pass")
        (base_path / "src" / "script.js").write_text("console.log('Hello');")

        # Create documentation
        (base_path / "docs" / "README.md").write_text("# Project Documentation")
        (base_path / "docs" / "API.md").write_text("## API Reference")

        # Create files that should be excluded (for non-git directories)
        (base_path / "build" / "output.bin").write_text("compiled output")
        (base_path / "node_modules" / "package.json").write_text('{"name": "test"}')
        (base_path / "__pycache__" / "main.pyc").write_bytes(b"compiled python")

        # Create always-excluded files
        (base_path / ".DS_Store").write_bytes(b"mac metadata")
        (base_path / "debug.log").write_text("debug information")
        (base_path / "temp.tmp").write_text("temporary data")

        return base_path

    def create_git_workspace(self, base_path: Path):
        """Create a git repository workspace."""
        # Initialize git repository
        repo = git.Repo.init(base_path)

        # Create and commit initial files
        (base_path / "main.py").write_text("print('Hello Git')")
        (base_path / "requirements.txt").write_text("requests==2.25.1")

        # Create normally excluded files (but should be included in git repos)
        (base_path / "node_modules").mkdir(exist_ok=True)
        (base_path / "node_modules" / "important.js").write_text("// Important script")
        (base_path / "__pycache__").mkdir(exist_ok=True)
        (base_path / "__pycache__" / "cache.pyc").write_bytes(b"python cache")

        # Create .gitignore
        (base_path / ".gitignore").write_text("*.log\n*.tmp\n")

        # Create ignored files (should still be included in backup)
        (base_path / "ignored.log").write_text("ignored by git")
        (base_path / "ignored.tmp").write_text("temporary ignored file")

        # Create always-excluded files (should still be excluded)
        (base_path / ".DS_Store").write_bytes(b"mac metadata")

        # Add and commit files
        repo.index.add(
            [
                "main.py",
                "requirements.txt",
                ".gitignore",
                "node_modules/important.js",
                "__pycache__/cache.pyc",
            ]
        )
        repo.index.commit("Initial commit")

        return base_path, repo

    def test_basic_backup_and_restore(self) -> None:
        """Test basic backup and restore workflow."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test workspace
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            self.create_test_workspace(workspace)

            # Create backup directory
            backup_dir = Path(temp_dir) / "backups"
            backup_dir.mkdir()

            # Configure backup - make sure all test files are included
            config = BackupConfig(
                include_patterns=["**/*"],  # Include all files for test
                exclude_patterns=[
                    "**/node_modules/**",
                    "**/__pycache__/**",
                    "**/build/**",
                ],  # Keep standard exclusions
                always_exclude=[
                    "**/.DS_Store",
                    "**/*.log",
                    "**/*.tmp",
                ],  # Keep basic always_exclude for test
            )
            config.target.base_path = str(workspace)
            config.target.output_path = str(backup_dir / "test-backup.tar.zst")

            # Create backup
            backup_result = create_backup(config=config, console=self.console)

            # Verify backup was created
            backup_path = Path(backup_result["output_path"])
            assert backup_path.exists()
            assert backup_path.stat().st_size > 0

            # Verify correct files were included
            assert backup_result["processed_files"] > 0

            # Create restore directory
            restore_dir = Path(temp_dir) / "restored"
            restore_dir.mkdir()

            # Restore backup
            restore_result = restore_backup(
                archive_path=backup_path,
                config=config,
                target_dir=restore_dir,
                console=self.console,
            )

            # Verify restore succeeded
            assert restore_result["restored"] > 0
            assert restore_result["errors"] == 0

            # Verify restored files
            assert (restore_dir / "src" / "main.py").exists()
            assert (restore_dir / "src" / "utils.py").exists()
            assert (restore_dir / "docs" / "README.md").exists()

            # Verify excluded files were not restored
            assert not (restore_dir / "build" / "output.bin").exists()
            assert not (restore_dir / "node_modules" / "package.json").exists()
            assert not (restore_dir / "__pycache__" / "main.pyc").exists()

            # Verify always-excluded files were not restored
            assert not (restore_dir / ".DS_Store").exists()
            assert not (restore_dir / "debug.log").exists()
            assert not (restore_dir / "temp.tmp").exists()

    def test_git_aware_backup_and_restore(self) -> None:
        """Test git-aware backup and restore."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create git workspace
            workspace = Path(temp_dir) / "git_workspace"
            workspace.mkdir()
            git_workspace, repo = self.create_git_workspace(workspace)

            # Create backup directory
            backup_dir = Path(temp_dir) / "backups"
            backup_dir.mkdir()

            # Configure backup
            config = BackupConfig(
                exclude_patterns=[],  # Don't exclude anything for git test - git repos should include everything
                always_exclude=["**/.DS_Store"],  # But still exclude OS files
            )
            config.target.base_path = str(git_workspace)
            config.target.output_path = str(backup_dir / "git-backup.tar.zst")
            config.git.include_repos = True
            config.git.include_git_dir = True
            config.git.respect_gitignore = (
                False  # Include everything, even gitignored files
            )

            # Create backup
            backup_result = create_backup(config=config, console=self.console)

            # Verify backup was created
            backup_path = Path(backup_result["output_path"])
            assert backup_path.exists()

            # Create restore directory
            restore_dir = Path(temp_dir) / "restored_git"
            restore_dir.mkdir()

            # Restore backup
            restore_result = restore_backup(
                archive_path=backup_path,
                config=config,
                target_dir=restore_dir,
                console=self.console,
            )

            # Verify restore succeeded
            assert restore_result["restored"] > 0
            assert restore_result["errors"] == 0

            # Verify git repository files were restored
            assert (restore_dir / "main.py").exists()
            assert (restore_dir / "requirements.txt").exists()
            assert (restore_dir / ".gitignore").exists()

            # Note: node_modules and __pycache__ are excluded even in git repos for performance
            # But git files themselves are included

            # Verify ignored files were included (git repo ignores gitignore)
            assert (restore_dir / "ignored.log").exists()
            assert (restore_dir / "ignored.tmp").exists()

            # Verify .git directory was restored
            assert (restore_dir / ".git").exists()
            assert (restore_dir / ".git" / "config").exists()

            # Verify always-excluded files were still excluded
            assert not (restore_dir / ".DS_Store").exists()

            # Verify restored git repository is functional
            restored_repo = git.Repo(restore_dir)
            assert not restored_repo.bare
            commits = list(restored_repo.iter_commits())
            assert len(commits) >= 1
            assert "Initial commit" in commits[0].message

    def test_mixed_git_and_regular_directories(self) -> None:
        """Test backup with both git repositories and regular directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "mixed_workspace"
            workspace.mkdir()

            # Create regular directory
            regular_dir = workspace / "regular_project"
            regular_dir.mkdir()
            self.create_test_workspace(regular_dir)

            # Create git directory
            git_dir = workspace / "git_project"
            git_dir.mkdir()
            self.create_git_workspace(git_dir)

            # Create backup directory
            backup_dir = Path(temp_dir) / "backups"
            backup_dir.mkdir()

            # Configure backup - keep normal exclude patterns for regular dirs
            config = BackupConfig()
            config.target.base_path = str(workspace)
            config.target.output_path = str(backup_dir / "mixed-backup.tar.zst")

            # Create backup
            backup_result = create_backup(config=config, console=self.console)

            # Verify backup was created
            backup_path = Path(backup_result["output_path"])
            assert backup_path.exists()

            # Create restore directory
            restore_dir = Path(temp_dir) / "restored_mixed"
            restore_dir.mkdir()

            # Restore backup
            restore_result = restore_backup(
                archive_path=backup_path,
                config=config,
                target_dir=restore_dir,
                console=self.console,
            )

            # Verify restore succeeded
            assert restore_result["restored"] > 0

            # Verify regular directory filtering worked
            assert (restore_dir / "regular_project" / "src" / "main.py").exists()
            assert not (
                restore_dir / "regular_project" / "node_modules" / "package.json"
            ).exists()

            # Verify git directory included source files
            assert (restore_dir / "git_project" / "main.py").exists()
            # Note: node_modules is excluded even in git repos for performance
            assert (restore_dir / "git_project" / ".git" / "config").exists()

    def test_partial_restore(self) -> None:
        """Test partial restore with pattern filtering."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test workspace
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            self.create_test_workspace(workspace)

            # Create backup
            backup_dir = Path(temp_dir) / "backups"
            backup_dir.mkdir()

            config = BackupConfig()
            config.target.base_path = str(workspace)
            config.target.output_path = str(backup_dir / "test-backup.tar.zst")

            backup_result = create_backup(config=config, console=self.console)

            backup_path = Path(backup_result["output_path"])

            # Restore only Python files
            restore_dir = Path(temp_dir) / "restored_python"
            restore_dir.mkdir()

            restore_result = restore_backup(
                archive_path=backup_path,
                config=config,
                target_dir=restore_dir,
                pattern_filter="**/*.py",
                console=self.console,
            )

            # Verify only Python files were restored
            assert (restore_dir / "src" / "main.py").exists()
            assert (restore_dir / "src" / "utils.py").exists()
            assert not (restore_dir / "src" / "script.js").exists()
            assert not (restore_dir / "docs" / "README.md").exists()

    def test_config_hierarchy_integration(self) -> None:
        """Test configuration hierarchy in real backup operation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Set up config directory
            config_dir = Path(temp_dir) / "config"
            config_dir.mkdir()

            # Create user config
            temp_dir_path = Path(temp_dir)
            user_config = {
                "compression": {"level": 6},
                "target": {"base_path": str(temp_dir_path / "workspace")},
                "include_patterns": ["**/*.py", "**/*.md"],
            }

            user_config_file = config_dir / "user-backup.yaml"
            with open(user_config_file, "w") as f:
                import yaml

                yaml.dump(user_config, f)

            # Create workspace
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            self.create_test_workspace(workspace)

            # Mock config manager paths
            with (
                patch.object(ConfigManager, "USER_CONFIG_FILE", user_config_file),
                patch.object(ConfigManager, "CONFIG_DIR", config_dir),
                patch.object(ConfigManager, "BACKUPS_DIR", config_dir / "backups"),
            ):
                # Load configuration with overrides
                config = ConfigManager.load_effective_config(
                    overrides={"compression": {"format": "gzip"}}
                )

                # Verify configuration hierarchy
                assert config.compression.level == 6  # From user config
                assert config.compression.format == "gzip"  # From override
                assert config.target.base_path == str(workspace)  # From user config

                # Create backup with merged config
                backup_result = create_backup(config=config, console=self.console)

                # Verify backup used correct settings
                assert backup_result["compression_level"] == 6
                assert backup_result["compression_format"] == "gzip"

    def test_backup_metadata_preservation(self) -> None:
        """Test that backup metadata is preserved and accessible."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test workspace
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            self.create_test_workspace(workspace)

            # Create backup
            backup_dir = Path(temp_dir) / "backups"
            backup_dir.mkdir()

            config = BackupConfig()
            config.target.base_path = str(workspace)
            config.target.output_path = str(backup_dir / "metadata-test.tar.zst")

            backup_result = create_backup(config=config, console=self.console)

            # Extract and verify metadata
            backup_path = Path(backup_result["output_path"])

            from sysforge.backup.compression import Decompressor

            members = Decompressor.list_archive(backup_path)

            # Find metadata file
            metadata_member = None
            for member in members:
                if member.name == ".backup_metadata.json":
                    metadata_member = member
                    break

            assert metadata_member is not None, "Metadata file not found in archive"

            # Extract and parse metadata
            with Decompressor.open_archive(backup_path) as tar:
                metadata_content = (
                    tar.extractfile(metadata_member).read().decode("utf-8")
                )
                metadata = json.loads(metadata_content)

            # Verify metadata structure
            assert "backup_info" in metadata
            assert "config" in metadata
            assert "git_repositories" in metadata
            assert "filter_stats" in metadata

            # Verify backup info
            backup_info = metadata["backup_info"]
            assert "created_at" in backup_info
            assert "target_path" in backup_info
            assert "total_files" in backup_info
            assert backup_info["compression_format"] == config.compression.format


# Import patch here to avoid conflicts
from unittest.mock import patch
