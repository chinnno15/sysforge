"""Tests for gitignore support in backup filtering."""

import tempfile
from pathlib import Path

import git

from sysforge.backup.config import BackupConfig
from sysforge.backup.filters import FileFilter
from sysforge.backup.git import GitRepository


class TestGitIgnoreSupport:
    """Test gitignore functionality in backup filtering."""

    def create_test_repo_with_gitignore(self, repo_path: Path) -> git.Repo:
        """Create a test git repository with .gitignore file."""
        repo = git.Repo.init(repo_path)

        # Configure user for commits
        with repo.config_writer() as config:
            config.set_value("user", "name", "Test User")
            config.set_value("user", "email", "test@example.com")

        # Create .gitignore file
        gitignore_content = """
# Node modules
node_modules/
debug.txt

# Build directories
build/
dist/

# Python cache
__pycache__/
*.pyc

# IDE files
.vscode/
.idea/
"""
        (repo_path / ".gitignore").write_text(gitignore_content.strip())

        # Create some files and directories
        (repo_path / "README.md").write_text("# Test Repository")

        # Create ignored directory
        (repo_path / "node_modules").mkdir()
        (repo_path / "node_modules" / "package.json").write_text("{}")

        # Create ignored files (avoid .log extension as it's in always_exclude)
        (repo_path / "debug.txt").write_text("debug content")
        (repo_path / "__pycache__").mkdir()
        (repo_path / "__pycache__" / "module.pyc").write_text("compiled")

        # Create non-ignored files
        (repo_path / "src").mkdir()
        (repo_path / "src" / "main.py").write_text("print('hello')")

        # Commit gitignore and some files
        repo.index.add([".gitignore", "README.md", "src/main.py"])
        repo.index.commit("Initial commit")

        return repo

    def test_gitignore_respected_when_enabled(self) -> None:
        """Test that .gitignore is respected when respect_gitignore=True."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Create test repository
            test_repo = self.create_test_repo_with_gitignore(repo_path)

            # Configure backup to respect gitignore
            config = BackupConfig(
                exclude_patterns=[], always_exclude=[]
            )  # Remove patterns to test only gitignore
            config.git.respect_gitignore = True
            file_filter = FileFilter(config)

            # Mock git detector to return our repository
            git_repo = GitRepository(repo_path, test_repo)
            file_filter.git_detector._repositories[repo_path] = git_repo

            # Test that ignored files are excluded
            ignored_file = repo_path / "debug.txt"
            should_include, reason = file_filter.should_include_file(ignored_file)
            assert should_include is False
            assert "ignored by .gitignore" in reason

            # Test that ignored directories are excluded
            ignored_dir = repo_path / "node_modules"
            should_include, reason = file_filter.should_include_directory(ignored_dir)
            assert should_include is False
            assert "ignored by .gitignore" in reason

            # Test that non-ignored files are included
            regular_file = repo_path / "README.md"
            should_include, reason = file_filter.should_include_file(regular_file)
            assert should_include is True
            assert "git repository" in reason

    def test_gitignore_ignored_when_disabled(self) -> None:
        """Test that .gitignore is ignored when respect_gitignore=False."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Create test repository
            test_repo = self.create_test_repo_with_gitignore(repo_path)

            # Configure backup to NOT respect gitignore
            config = BackupConfig(exclude_patterns=[], always_exclude=[])
            config.git.respect_gitignore = False
            file_filter = FileFilter(config)

            # Mock git detector to return our repository
            git_repo = GitRepository(repo_path, test_repo)
            file_filter.git_detector._repositories[repo_path] = git_repo

            # Test that ignored files are still included when gitignore is disabled
            ignored_file = repo_path / "debug.txt"
            should_include, reason = file_filter.should_include_file(ignored_file)
            assert should_include is True
            assert "git repository" in reason

            # Test that ignored directories are still traversed when gitignore is disabled
            ignored_dir = repo_path / "node_modules"
            should_include, reason = file_filter.should_include_directory(ignored_dir)
            assert should_include is True
            assert "git repository" in reason

    def test_gitignore_with_exclude_patterns(self) -> None:
        """Test that gitignore works in combination with exclude patterns."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Create test repository
            test_repo = self.create_test_repo_with_gitignore(repo_path)

            # Create a file that matches exclude pattern but not gitignore
            (repo_path / "temp_file.tmp").write_text("temporary")

            # Configure backup with both gitignore and exclude patterns
            config = BackupConfig(exclude_patterns=["**/*.tmp"], always_exclude=[])
            config.git.respect_gitignore = True
            file_filter = FileFilter(config)

            # Mock git detector to return our repository
            git_repo = GitRepository(repo_path, test_repo)
            file_filter.git_detector._repositories[repo_path] = git_repo

            # Test that file excluded by gitignore is excluded
            gitignore_file = repo_path / "debug.txt"
            should_include, reason = file_filter.should_include_file(gitignore_file)
            assert should_include is False
            assert "ignored by .gitignore" in reason

            # Test that file excluded by exclude pattern is excluded
            exclude_pattern_file = repo_path / "temp_file.tmp"
            should_include, reason = file_filter.should_include_file(
                exclude_pattern_file
            )
            assert should_include is False
            assert "exclude pattern" in reason

    def test_git_is_ignored_method(self) -> None:
        """Test the GitRepository.is_ignored method directly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Create test repository
            test_repo = self.create_test_repo_with_gitignore(repo_path)
            git_repo = GitRepository(repo_path, test_repo)

            # Test that ignored files are detected
            assert git_repo.is_ignored(repo_path / "debug.txt") is True
            assert git_repo.is_ignored(repo_path / "node_modules") is True
            assert git_repo.is_ignored(repo_path / "__pycache__") is True

            # Test that non-ignored files are not detected as ignored
            assert git_repo.is_ignored(repo_path / "README.md") is False
            assert git_repo.is_ignored(repo_path / "src") is False
            assert git_repo.is_ignored(repo_path / "src" / "main.py") is False

    def test_gitignore_integration_with_get_filtered_files(self) -> None:
        """Test gitignore integration with the main get_filtered_files method."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Create test repository
            self.create_test_repo_with_gitignore(repo_path)

            # Configure backup to respect gitignore
            config = BackupConfig()
            config.git.respect_gitignore = True
            config.include_patterns = ["**/*"]  # Include everything by default
            config.exclude_patterns = []  # Remove default exclude patterns for cleaner test
            file_filter = FileFilter(config)

            # Get filtered files
            files = file_filter.get_filtered_files(repo_path)

            # Convert to relative paths for easier testing
            relative_files = [f.relative_to(repo_path) for f in files]
            relative_file_strs = [str(f) for f in relative_files]

            # Test that non-ignored files are included
            assert any("README.md" in f for f in relative_file_strs)
            assert any("src/main.py" in f for f in relative_file_strs)
            assert any(
                ".git" in f for f in relative_file_strs
            )  # Git directory should be included

            # Test that ignored files/directories are excluded
            assert not any("debug.txt" in f for f in relative_file_strs)
            assert not any("node_modules" in f for f in relative_file_strs)
            assert not any("__pycache__" in f for f in relative_file_strs)

    def test_gitignore_override_patterns_default(self) -> None:
        """Test that default gitignore override patterns work (e.g., .env files)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Create test repository
            repo = git.Repo.init(repo_path)

            # Configure user for commits
            with repo.config_writer() as config:
                config.set_value("user", "name", "Test User")
                config.set_value("user", "email", "test@example.com")

            # Create .gitignore that ignores .env files
            gitignore_content = """
.env
.env.*
secrets.*
node_modules/
"""
            (repo_path / ".gitignore").write_text(gitignore_content.strip())

            # Create files - some gitignored, some not
            (repo_path / ".env").write_text(
                "SECRET=123"
            )  # Gitignored but should be backed up
            (repo_path / ".env.local").write_text(
                "LOCAL=456"
            )  # Gitignored but should be backed up
            (repo_path / "secrets.json").write_text(
                '{"key": "value"}'
            )  # Should be backed up
            (repo_path / "node_modules").mkdir()
            (repo_path / "node_modules" / "package.json").write_text(
                "{}"
            )  # Should remain excluded
            (repo_path / "app.js").write_text(
                "console.log('app')"
            )  # Should be included

            # Commit gitignore
            repo.index.add([".gitignore", "app.js"])
            repo.index.commit("Initial commit")

            # Configure backup with default gitignore override patterns
            backup_config: BackupConfig = BackupConfig(
                exclude_patterns=[], always_exclude=[]
            )
            backup_config.git.respect_gitignore = True
            # Default gitignore_override_patterns should include .env patterns
            file_filter = FileFilter(backup_config)

            # Mock git detector to return our repository
            git_repo = GitRepository(repo_path, repo)
            file_filter.git_detector._repositories[repo_path] = git_repo

            # Test .env files are backed up despite being gitignored
            env_file = repo_path / ".env"
            should_include, reason = file_filter.should_include_file(env_file)
            assert should_include is True
            assert "git repository" in reason

            env_local_file = repo_path / ".env.local"
            should_include, reason = file_filter.should_include_file(env_local_file)
            assert should_include is True
            assert "git repository" in reason

            secrets_file = repo_path / "secrets.json"
            should_include, reason = file_filter.should_include_file(secrets_file)
            assert should_include is True
            assert "git repository" in reason

            # Test node_modules is still excluded (not in override patterns)
            node_modules_dir = repo_path / "node_modules"
            should_include, reason = file_filter.should_include_directory(
                node_modules_dir
            )
            assert should_include is False
            assert "ignored by .gitignore" in reason

            # Test regular files are included
            app_file = repo_path / "app.js"
            should_include, reason = file_filter.should_include_file(app_file)
            assert should_include is True
            assert "git repository" in reason

    def test_custom_gitignore_override_patterns(self) -> None:
        """Test custom gitignore override patterns."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Create test repository with gitignore
            test_repo = self.create_test_repo_with_gitignore(repo_path)

            # Configure backup with custom override patterns
            config = BackupConfig(exclude_patterns=[], always_exclude=[])
            config.git.respect_gitignore = True
            config.git.gitignore_override_patterns = [
                "**/debug.txt",
                "**/node_modules/important.js",
            ]
            file_filter = FileFilter(config)

            # Create files that match override patterns
            (repo_path / "node_modules" / "important.js").write_text("important code")

            # Mock git detector to return our repository
            git_repo = GitRepository(repo_path, test_repo)
            file_filter.git_detector._repositories[repo_path] = git_repo

            # Test that debug.txt is now included (matches override pattern)
            debug_file = repo_path / "debug.txt"
            should_include, reason = file_filter.should_include_file(debug_file)
            assert should_include is True
            assert "git repository" in reason

            # Test that important.js is included despite being in node_modules
            important_file = repo_path / "node_modules" / "important.js"
            should_include, reason = file_filter.should_include_file(important_file)
            assert should_include is True
            assert "git repository" in reason

            # Test that other node_modules files are still excluded
            package_file = repo_path / "node_modules" / "package.json"
            should_include, reason = file_filter.should_include_file(package_file)
            assert should_include is False
            assert "ignored by .gitignore" in reason

    def test_gitignore_override_integration(self) -> None:
        """Test gitignore override patterns with full file scanning."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Create test repository
            repo = git.Repo.init(repo_path)

            # Configure user for commits
            with repo.config_writer() as config:
                config.set_value("user", "name", "Test User")
                config.set_value("user", "email", "test@example.com")

            # Create comprehensive .gitignore
            gitignore_content = """
.env
.env.*
node_modules/
build/
*.log
"""
            (repo_path / ".gitignore").write_text(gitignore_content.strip())

            # Create various files
            (repo_path / ".env").write_text("SECRET=123")
            (repo_path / ".env.prod").write_text("PROD=456")
            (repo_path / "app.log").write_text("log data")  # Should be excluded
            (repo_path / "src.js").write_text("source code")
            (repo_path / "node_modules").mkdir()
            (repo_path / "node_modules" / "lib.js").write_text("library")

            # Commit files
            repo.index.add([".gitignore", "src.js"])
            repo.index.commit("Initial commit")

            # Configure backup with default settings (includes .env override)
            backup_config: BackupConfig = BackupConfig()
            backup_config.git.respect_gitignore = True
            backup_config.include_patterns = ["**/*"]  # Include all by default
            backup_config.exclude_patterns = []  # Remove default excludes for cleaner test
            file_filter = FileFilter(backup_config)

            # Get filtered files
            files = file_filter.get_filtered_files(repo_path)

            # Convert to relative paths for easier testing
            relative_files = [f.relative_to(repo_path) for f in files]
            relative_file_strs = [str(f) for f in relative_files]

            # Test that .env files are included (override gitignore)
            assert any(".env" == f for f in relative_file_strs), (
                ".env should be included via override"
            )
            assert any(".env.prod" == f for f in relative_file_strs), (
                ".env.prod should be included via override"
            )

            # Test that regular source files are included
            assert any("src.js" in f for f in relative_file_strs), (
                "src.js should be included"
            )
            assert any(".git" in f for f in relative_file_strs), (
                "Git directory should be included"
            )

            # Test that other ignored files are still excluded
            assert not any("app.log" in f for f in relative_file_strs), (
                "app.log should be excluded"
            )
            assert not any("node_modules" in f for f in relative_file_strs), (
                "node_modules should be excluded"
            )
