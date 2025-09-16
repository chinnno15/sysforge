"""Integration tests for git backup functionality."""

import os
import tempfile
from pathlib import Path

import git

from sysforge.backup.cli import create_backup
from sysforge.backup.config import BackupConfig


class TestGitBackupIntegration:
    """Test git repository backup and restore functionality."""

    def setup_method(self) -> None:
        """Set up test environment."""
        # Use a directory that won't match exclude patterns
        self.temp_dir = Path(tempfile.mkdtemp(dir=os.path.expanduser("~")))
        self.backup_dir = self.temp_dir / "backups"
        self.backup_dir.mkdir()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def create_test_git_repo(self, repo_path: Path) -> git.Repo:
        """Create a test git repository with some history."""
        repo = git.Repo.init(repo_path)

        # Configure user for commits
        with repo.config_writer() as config:
            config.set_value("user", "name", "Test User")
            config.set_value("user", "email", "test@example.com")

        # Create some files and commits
        (repo_path / "README.md").write_text("# Test Repository\n")
        (repo_path / "src").mkdir()
        (repo_path / "src" / "main.py").write_text("print('Hello, World!')\n")

        repo.index.add(["README.md", "src/main.py"])
        repo.index.commit("Initial commit")

        # Create a second commit
        (repo_path / "CHANGELOG.md").write_text(
            "# Changelog\n\n## v1.0.0\n- Initial release\n"
        )
        repo.index.add(["CHANGELOG.md"])
        repo.index.commit("Add changelog")

        # Create a branch
        repo.create_head("feature-branch")

        return repo

    def test_full_git_backup_includes_all_git_data(self) -> None:
        """Test that git backup includes all git data including objects."""
        # Create test git repository
        repo_path = self.temp_dir / "test_repo"
        repo_path.mkdir()
        self.create_test_git_repo(repo_path)

        # Ensure we have git objects
        objects_dir = repo_path / ".git" / "objects"
        assert objects_dir.exists()
        object_files = list(objects_dir.rglob("*"))
        assert len(object_files) > 5  # Should have several object files

        # Create backup config
        config = BackupConfig()
        config.git.include_git_dir = True
        config.target.output_path = str(self.backup_dir / "test_backup.tar.zst")

        # Perform backup
        result = create_backup(config, repo_path, dry_run=True)

        # Verify git objects are included
        assert result["success"]
        assert result["total_files"] > 10  # Should include many git files

        # Check that .git directory files are included
        git_files = [f for f in result["files"] if ".git" in str(f)]
        assert len(git_files) > 5

        # Check for specific git objects
        object_files_in_backup = [
            f for f in result["files"] if ".git/objects" in str(f)
        ]
        assert len(object_files_in_backup) > 0, (
            "Git objects should be included in backup"
        )

    def test_git_backup_excludes_node_modules_but_includes_git(self) -> None:
        """Test that git backup excludes node_modules but includes all git data."""
        # Create test git repository with node_modules
        repo_path = self.temp_dir / "test_repo"
        repo_path.mkdir()
        self.create_test_git_repo(repo_path)

        # Create node_modules directory (should be excluded)
        node_modules = repo_path / "node_modules"
        node_modules.mkdir()
        (node_modules / "some_package").mkdir()
        (node_modules / "some_package" / "index.js").write_text("module.exports = {};")

        # Create backup config
        config = BackupConfig()
        config.git.include_git_dir = True
        config.target.output_path = str(self.backup_dir / "test_backup.tar.zst")

        # Perform backup
        result = create_backup(config, repo_path, dry_run=True)

        assert result["success"]

        # Verify node_modules is excluded
        node_modules_files = [f for f in result["files"] if "node_modules" in str(f)]
        assert len(node_modules_files) == 0, "node_modules should be excluded"

        # Verify git directory is included
        git_files = [f for f in result["files"] if ".git" in str(f)]
        assert len(git_files) > 5, "Git directory should be included"

        # Verify source files are included
        source_files = [
            f
            for f in result["files"]
            if f.name in ["README.md", "main.py", "CHANGELOG.md"]
        ]
        assert len(source_files) >= 3, "Source files should be included"

    def test_git_backup_includes_complete_git_data(self) -> None:
        """Test that git backup includes complete git data for later restore."""
        # Create test git repository
        original_repo_path = self.temp_dir / "original_repo"
        original_repo_path.mkdir()
        test_repo = self.create_test_git_repo(original_repo_path)

        # Get original commit info
        list(test_repo.iter_commits())
        [branch.name for branch in test_repo.branches]

        # Create backup config
        config = BackupConfig()
        config.git.include_git_dir = True
        backup_file = self.backup_dir / "test_backup.tar.zst"
        config.target.output_path = str(backup_file)

        # Perform actual backup (not dry run)
        result = create_backup(config, original_repo_path, dry_run=False)
        assert result["success"]
        assert backup_file.exists()

        # Verify backup includes all necessary git data
        backup_files = result["files"]

        # Check essential git files are included
        git_files = [str(f) for f in backup_files if ".git" in str(f)]
        assert len(git_files) > 10, "Should include many git files"

        # Check for key git components
        git_file_names = [Path(f).name for f in git_files]
        assert "HEAD" in git_file_names, "Should include HEAD file"
        assert "config" in git_file_names, "Should include git config"

        # Check for git objects (commits, trees, blobs)
        git_object_files = [f for f in backup_files if ".git/objects" in str(f)]
        assert len(git_object_files) > 0, "Should include git objects for full history"

        # Check for refs (branches)
        ref_files = [f for f in backup_files if ".git/refs" in str(f)]
        assert len(ref_files) > 0, "Should include git refs for branches"

        # Check source files are also included
        source_files = [
            f
            for f in backup_files
            if f.name in ["README.md", "main.py", "CHANGELOG.md"]
        ]
        assert len(source_files) >= 3, "Should include source files"

        assert backup_file.stat().st_size > 1000, (
            "Backup file should have reasonable size"
        )

    def test_multiple_git_repos_backup(self) -> None:
        """Test backing up multiple git repositories."""
        # Create multiple test git repositories
        workspace = self.temp_dir / "workspace"
        workspace.mkdir()

        # Create first repo
        repo1_path = workspace / "repo1"
        repo1_path.mkdir()
        self.create_test_git_repo(repo1_path)

        # Create second repo with different content
        repo2_path = workspace / "repo2"
        repo2_path.mkdir()
        repo2 = git.Repo.init(repo2_path)

        with repo2.config_writer() as config:
            config.set_value("user", "name", "Test User")
            config.set_value("user", "email", "test@example.com")

        (repo2_path / "app.py").write_text("#!/usr/bin/env python3\nprint('App')\n")
        repo2.index.add(["app.py"])
        repo2.index.commit("Add app.py")

        # Create backup config
        config = BackupConfig()
        config.git.include_git_dir = True
        config.target.output_path = str(self.backup_dir / "workspace_backup.tar.zst")

        # Perform backup
        result = create_backup(config, workspace, dry_run=True)

        assert result["success"]

        # Verify both repos are included
        repo1_files = [f for f in result["files"] if "repo1" in str(f)]
        repo2_files = [f for f in result["files"] if "repo2" in str(f)]

        assert len(repo1_files) > 0, "First repository should be included"
        assert len(repo2_files) > 0, "Second repository should be included"

        # Check for git objects in both repos
        repo1_git_objects = [
            f for f in result["files"] if "repo1/.git/objects" in str(f)
        ]
        repo2_git_objects = [
            f for f in result["files"] if "repo2/.git/objects" in str(f)
        ]

        assert len(repo1_git_objects) > 0, "First repo git objects should be included"
        assert len(repo2_git_objects) > 0, "Second repo git objects should be included"

    def test_performance_with_large_git_history(self) -> None:
        """Test backup performance with larger git history."""
        # Create repo with more commits for performance testing
        repo_path = self.temp_dir / "large_repo"
        repo_path.mkdir()
        repo = git.Repo.init(repo_path)

        with repo.config_writer() as config:
            config.set_value("user", "name", "Test User")
            config.set_value("user", "email", "test@example.com")

        # Create initial commit
        (repo_path / "file1.txt").write_text("Initial content\n")
        repo.index.add(["file1.txt"])
        repo.index.commit("Initial commit")

        # Create multiple commits
        for i in range(10):
            content = f"Content version {i + 1}\n"
            (repo_path / f"file{i + 2}.txt").write_text(content)
            repo.index.add([f"file{i + 2}.txt"])
            repo.index.commit(f"Add file{i + 2}.txt")

        # Create backup config
        config = BackupConfig()
        config.git.include_git_dir = True
        config.target.output_path = str(self.backup_dir / "large_repo_backup.tar.zst")

        # Perform backup and measure basic success
        import time

        start_time = time.time()
        result = create_backup(config, repo_path, dry_run=True)
        end_time = time.time()

        assert result["success"]
        assert result["total_files"] > 15  # Should have many files

        # Ensure backup completes in reasonable time (less than 10 seconds for test)
        backup_time = end_time - start_time
        assert backup_time < 10.0, f"Backup took too long: {backup_time:.2f} seconds"

        # Verify git objects are included
        git_object_files = [f for f in result["files"] if ".git/objects" in str(f)]
        assert len(git_object_files) > 10, (
            "Should include git objects from multiple commits"
        )
