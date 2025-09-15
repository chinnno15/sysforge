"""Tests for parallel backup performance features."""

import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from rich.console import Console

from sysforge.backup.config import BackupConfig
from sysforge.backup.core import BackupOperation, PerformanceMetrics, measure_time
from sysforge.backup.filters import FileFilter
from sysforge.backup.git import GitRepository


class TestPerformanceMetrics:
    """Test performance metrics tracking."""

    def test_performance_metrics_initialization(self):
        """Test PerformanceMetrics initialization."""
        metrics = PerformanceMetrics()

        assert metrics.repo_discovery_time == 0.0
        assert metrics.repo_processing_time == 0.0
        assert metrics.non_repo_processing_time == 0.0
        assert metrics.total_scan_time == 0.0
        assert metrics.total_repos_processed == 0
        assert metrics.parallel_workers_used == 0
        assert metrics.total_files_found == 0
        assert metrics.total_files_processed == 0
        assert metrics.enable_parallel is True

    def test_measure_time_context_manager(self):
        """Test the measure_time context manager."""
        with measure_time() as timer:
            time.sleep(0.001)  # Small sleep to ensure measurable time

        assert timer.elapsed > 0
        assert timer.elapsed < 1.0  # Should be much less than a second


class TestParallelFileFilter:
    """Test parallel file filtering functionality."""

    def test_parallel_configuration(self):
        """Test parallel processing configuration."""
        config = BackupConfig(
            max_workers=4,
            enable_parallel_processing=True
        )
        file_filter = FileFilter(config)

        assert file_filter.config.max_workers == 4
        assert file_filter.config.enable_parallel_processing is True

    def test_parallel_vs_sequential_git_discovery(self):
        """Test that parallel and sequential git discovery can be selected."""
        config = BackupConfig(enable_parallel_processing=True, max_workers=2)
        file_filter = FileFilter(config)

        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)

            # Mock the actual discovery methods
            with patch.object(file_filter, '_discover_git_repositories_parallel', return_value=[]) as mock_parallel:
                with patch.object(file_filter, '_discover_git_repositories_sequential', return_value=[]) as mock_sequential:
                    # Should use parallel
                    file_filter._discover_git_repositories_fast(base_path)
                    mock_parallel.assert_called_once_with(base_path)
                    mock_sequential.assert_not_called()

    def test_sequential_git_discovery_when_disabled(self):
        """Test that sequential discovery is used when parallel is disabled."""
        config = BackupConfig(enable_parallel_processing=False)
        file_filter = FileFilter(config)

        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)

            # Mock the actual discovery methods
            with patch.object(file_filter, '_discover_git_repositories_parallel', return_value=[]) as mock_parallel:
                with patch.object(file_filter, '_discover_git_repositories_sequential', return_value=[]) as mock_sequential:
                    # Should use sequential
                    file_filter._discover_git_repositories_fast(base_path)
                    mock_sequential.assert_called_once_with(base_path)
                    mock_parallel.assert_not_called()

    def test_parallel_repository_processing(self):
        """Test parallel repository file processing."""
        config = BackupConfig(
            enable_parallel_processing=True,
            max_workers=2,
            git={"include_repos": True, "respect_gitignore": True}
        )
        file_filter = FileFilter(config)

        # Create mock repositories
        mock_repo1 = Mock(spec=GitRepository)
        mock_repo1.path = Path("/fake/repo1")
        mock_repo2 = Mock(spec=GitRepository)
        mock_repo2.path = Path("/fake/repo2")

        repos = [mock_repo1, mock_repo2]

        # Mock the single repository processing
        with patch.object(file_filter, '_process_single_repository') as mock_process:
            mock_process.return_value = [Path("/fake/file1.py"), Path("/fake/file2.py")]

            with patch.object(file_filter, '_filter_git_files') as mock_filter:
                mock_filter.return_value = [Path("/fake/file1.py"), Path("/fake/file2.py")]

                result = file_filter._get_repository_files_parallel(repos, verbose=False, console=None)

                # Should have been called for each repository
                assert mock_process.call_count == 2
                assert len(result) == 2

    def test_parallel_non_repo_file_processing(self):
        """Test parallel non-repository file processing."""
        config = BackupConfig(enable_parallel_processing=True, max_workers=2)
        file_filter = FileFilter(config)

        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)

            # Mock repository exclusions
            repo_exclusions = {"/fake/repo1", "/fake/repo2"}

            # Mock the chunk processing
            with patch.object(file_filter, '_get_directory_chunks') as mock_chunks:
                mock_chunks.return_value = [base_path / "chunk1", base_path / "chunk2"]

                with patch.object(file_filter, '_find_files_in_chunk') as mock_find:
                    mock_find.return_value = [Path("/fake/file.py")]

                    result = file_filter._get_non_repository_files_parallel(
                        base_path, [], verbose=False, console=None
                    )

                    # Should have been called for each chunk
                    assert mock_find.call_count == 2
                    assert len(result) == 2

    def test_home_directory_chunking(self):
        """Test home directory chunking for parallel processing."""
        config = BackupConfig(dot_directory_whitelist=[".ssh", ".config"])
        file_filter = FileFilter(config)

        repo_exclusions = set()

        # Mock Path.home() and directory existence
        with patch('pathlib.Path.home') as mock_home:
            fake_home = Path("/fake/home")
            mock_home.return_value = fake_home

            with patch.object(Path, 'exists') as mock_exists:
                mock_exists.return_value = True

                chunks = file_filter._get_home_directory_chunks(repo_exclusions)

                # Should include home directory and whitelisted directories
                assert fake_home in chunks
                assert fake_home / ".ssh" in chunks
                assert fake_home / ".config" in chunks

    def test_directory_chunking(self):
        """Test general directory chunking for parallel processing."""
        config = BackupConfig()
        file_filter = FileFilter(config)

        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)

            # Create subdirectories
            (base_path / "dir1").mkdir()
            (base_path / "dir2").mkdir()
            (base_path / "file.txt").touch()

            repo_exclusions = set()

            chunks = file_filter._get_directory_chunks(base_path, repo_exclusions)

            # Should include the subdirectories
            assert base_path / "dir1" in chunks
            assert base_path / "dir2" in chunks

    def test_single_repository_processing(self):
        """Test processing a single repository with git commands."""
        config = BackupConfig()
        config.git.respect_gitignore = True
        config.git.include_git_dir = True
        file_filter = FileFilter(config)

        # Mock GitRepository with proper attributes
        mock_repo = Mock()
        mock_git_repo = Mock()
        mock_git_repo.working_dir = "/fake/repo"
        mock_git = Mock()
        mock_git.ls_files.return_value = "file1.py\nfile2.py"
        mock_git_repo.git = mock_git
        mock_repo.repo = mock_git_repo
        mock_repo.get_override_files.return_value = [Path("/fake/repo/.env")]

        with patch('pathlib.Path.rglob') as mock_rglob:
            mock_rglob.return_value = [Path("/fake/repo/.git/config")]

            with patch('pathlib.Path.is_file') as mock_is_file:
                mock_is_file.return_value = True

                result = file_filter._process_single_repository(mock_repo)

                # Should include tracked files, override files, and .git directory
                assert len(result) >= 2  # At least the tracked files

    def test_non_repo_file_filtering(self):
        """Test filtering logic for non-repository files."""
        config = BackupConfig(
            include_patterns=["*.py", "*.txt"],
            exclude_patterns=["*/temp/**"],
            always_exclude=["*.log"],
            max_file_size="1MB"
        )
        file_filter = FileFilter(config)

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files
            good_file = Path(temp_dir) / "test.py"
            good_file.touch()

            log_file = Path(temp_dir) / "debug.log"
            log_file.touch()

            # Mock file size check
            with patch.object(file_filter, '_check_file_size') as mock_size:
                mock_size.return_value = True

                # Should include .py file
                assert file_filter._should_include_non_repo_file(good_file) is True

                # Should exclude .log file (always_exclude)
                assert file_filter._should_include_non_repo_file(log_file) is False


class TestBackupOperationPerformance:
    """Test backup operation performance monitoring."""

    def test_backup_operation_performance_metrics(self):
        """Test that BackupOperation initializes performance metrics."""
        config = BackupConfig(max_workers=4, enable_parallel_processing=True)
        console = Console()

        backup_op = BackupOperation(config, console)

        assert backup_op.performance_metrics is not None
        assert backup_op.performance_metrics.parallel_workers_used == 4
        assert backup_op.performance_metrics.enable_parallel is True

    def test_backup_info_includes_performance_metrics(self):
        """Test that backup info includes performance metrics."""
        config = BackupConfig()
        backup_op = BackupOperation(config)

        # Set some fake metrics
        backup_op.performance_metrics.total_scan_time = 1.5
        backup_op.performance_metrics.total_files_found = 100

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir)
            output_path = Path(temp_dir) / "backup.tar.zst"

            info = backup_op._get_backup_info(target_path, output_path)

            assert "performance_metrics" in info
            metrics = info["performance_metrics"]
            assert metrics["total_scan_time"] == 1.5
            assert metrics["total_files_found"] == 100
            assert metrics["files_per_second"] == 100 / 1.5

    def test_create_backup_with_performance_monitoring(self):
        """Test that create_backup method tracks performance."""
        config = BackupConfig(
            target={"base_path": ".", "output_path": "./test_backup.tar.zst"},
            enable_parallel_processing=True,
            max_workers=2
        )

        backup_op = BackupOperation(config)

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir)
            output_path = Path(temp_dir) / "backup.tar.zst"

            # Create a test file
            (target_path / "test.py").touch()

            # Mock the file filter to return known results quickly
            with patch.object(backup_op.file_filter, 'get_filtered_files') as mock_filter:
                mock_filter.return_value = [target_path / "test.py"]

                result = backup_op.create_backup(
                    target_path=target_path,
                    output_path=output_path,
                    dry_run=True
                )

                # Should have performance metrics
                assert "performance_metrics" in result
                assert result["performance_metrics"]["total_scan_time"] >= 0
                assert result["performance_metrics"]["total_files_found"] == 1