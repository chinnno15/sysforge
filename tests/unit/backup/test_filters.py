"""Tests for file filtering logic."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import git

from sysforge.backup.config import BackupConfig
from sysforge.backup.filters import FileFilter


class TestFileFilter:
    """Test FileFilter class."""

    def test_file_filter_initialization(self) -> None:
        """Test FileFilter initialization."""
        config = BackupConfig()
        file_filter = FileFilter(config)

        assert file_filter.config == config
        assert file_filter.max_file_size_bytes == config.get_max_file_size_bytes()
        assert file_filter.git_detector is not None

    def test_matches_patterns_simple(self) -> None:
        """Test pattern matching with simple patterns."""
        config = BackupConfig(
            include_patterns=["*.py", "*.js"], exclude_patterns=["*.tmp", "*.log"]
        )
        file_filter = FileFilter(config)

        # Test include patterns
        assert (
            file_filter._matches_patterns(Path("test.py"), config.include_patterns)
            is True
        )
        assert (
            file_filter._matches_patterns(Path("script.js"), config.include_patterns)
            is True
        )
        assert (
            file_filter._matches_patterns(Path("document.txt"), config.include_patterns)
            is False
        )

        # Test exclude patterns
        assert (
            file_filter._matches_patterns(Path("temp.tmp"), config.exclude_patterns)
            is True
        )
        assert (
            file_filter._matches_patterns(Path("debug.log"), config.exclude_patterns)
            is True
        )
        assert (
            file_filter._matches_patterns(Path("source.py"), config.exclude_patterns)
            is False
        )

    def test_matches_patterns_glob(self) -> None:
        """Test pattern matching with glob patterns."""
        config = BackupConfig(
            include_patterns=["**/*.py", "src/**"],
            exclude_patterns=["**/node_modules/**", "**/__pycache__/**"],
        )
        file_filter = FileFilter(config)

        # Test recursive include patterns
        assert (
            file_filter._matches_patterns(
                Path("project/src/main.py"), config.include_patterns
            )
            is True
        )
        assert (
            file_filter._matches_patterns(
                Path("src/utils/helper.py"), config.include_patterns
            )
            is True
        )
        assert (
            file_filter._matches_patterns(
                Path("src/component.js"), config.include_patterns
            )
            is True
        )  # Matches src/**

        # Test recursive exclude patterns
        assert (
            file_filter._matches_patterns(
                Path("project/node_modules/package/index.js"), config.exclude_patterns
            )
            is True
        )
        assert (
            file_filter._matches_patterns(
                Path("src/__pycache__/module.pyc"), config.exclude_patterns
            )
            is True
        )

    def test_should_include_file_nonexistent(self) -> None:
        """Test should_include_file for nonexistent file."""
        config = BackupConfig()
        file_filter = FileFilter(config)

        nonexistent_file = Path("/nonexistent/file.py")
        should_include, reason = file_filter.should_include_file(nonexistent_file)

        assert should_include is False
        assert "does not exist" in reason

    def test_should_include_file_always_exclude(self) -> None:
        """Test should_include_file with always_exclude patterns."""
        config = BackupConfig(
            always_exclude=["**/.DS_Store", "**/*.tmp"],
            exclude_patterns=[],  # Empty exclude patterns to avoid conflicts
        )
        file_filter = FileFilter(config)

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files
            ds_store = Path(temp_dir) / ".DS_Store"
            ds_store.touch()

            tmp_file = Path(temp_dir) / "temp.tmp"
            tmp_file.touch()

            regular_file = Path(temp_dir) / "regular.py"
            regular_file.touch()

            # Test always exclude
            should_include, reason = file_filter.should_include_file(ds_store)
            assert should_include is False
            assert "always_exclude" in reason

            should_include, reason = file_filter.should_include_file(tmp_file)
            assert should_include is False
            assert "always_exclude" in reason

            # Mock git detector to return None (not in git repo)
            with patch.object(
                file_filter.git_detector, "get_repository_for_path", return_value=None
            ):
                # Regular file should be included (matches include patterns)
                should_include, reason = file_filter.should_include_file(regular_file)
                assert should_include is True
                assert "include pattern" in reason

    def test_should_include_file_size_limit(self) -> None:
        """Test should_include_file with file size limit."""
        config = BackupConfig(
            max_file_size="1KB",  # Very small limit
            exclude_patterns=[],  # Empty exclude patterns to avoid conflicts
        )
        file_filter = FileFilter(config)

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create small file that matches include patterns
            small_file = Path(temp_dir) / "small.py"
            small_file.write_text("small content")

            # Create large file that would match include patterns
            large_file = Path(temp_dir) / "large.py"
            large_file.write_text("x" * 2048)  # 2KB file

            # Mock git detector to return None (not in git repo)
            with patch.object(
                file_filter.git_detector, "get_repository_for_path", return_value=None
            ):
                # Test small file
                should_include, reason = file_filter.should_include_file(small_file)
                assert should_include is True
                assert "include pattern" in reason

                # Test large file
                should_include, reason = file_filter.should_include_file(large_file)
                assert should_include is False
                assert "size" in reason and "exceeds limit" in reason

    def test_should_include_git_file(self) -> None:
        """Test should_include_file for files in git repository."""
        # Use config without exclude patterns to avoid temp dir conflicts
        config = BackupConfig(exclude_patterns=[])
        file_filter = FileFilter(config)

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            repo = git.Repo.init(repo_path)

            # Create test file in repo
            test_file = repo_path / "test.py"
            test_file.write_text("print('hello')")

            # Mock git detector to return the repository
            with patch.object(
                file_filter.git_detector, "get_repository_for_path"
            ) as mock_get_repo:
                from sysforge.backup.git import GitRepository

                mock_git_repo = GitRepository(repo_path, repo)
                mock_get_repo.return_value = mock_git_repo

                should_include, reason = file_filter.should_include_file(test_file)
                assert should_include is True
                assert "git repository" in reason

    def test_should_include_git_dir_file(self) -> None:
        """Test should_include_file for .git directory files."""
        # Test with include_git_dir = True
        config = BackupConfig()
        config.git.include_git_dir = True
        file_filter = FileFilter(config)

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            repo = git.Repo.init(repo_path)
            git_config_file = Path(repo.git_dir) / "config"

            # Mock git detector
            with patch.object(
                file_filter.git_detector, "get_repository_for_path"
            ) as mock_get_repo:
                from sysforge.backup.git import GitRepository

                mock_git_repo = GitRepository(repo_path, repo)
                mock_get_repo.return_value = mock_git_repo

                should_include, reason = file_filter.should_include_file(
                    git_config_file
                )
                assert should_include is True
                assert "Git directory (included" in reason

            # Test with include_git_dir = False
            config.git.include_git_dir = False
            file_filter = FileFilter(config)

            with patch.object(
                file_filter.git_detector, "get_repository_for_path"
            ) as mock_get_repo:
                mock_git_repo = GitRepository(repo_path, repo)
                mock_get_repo.return_value = mock_git_repo

                should_include, reason = file_filter.should_include_file(
                    git_config_file
                )
                assert should_include is False
                assert "Git directory (excluded" in reason

    def test_should_include_regular_file_exclude_pattern(self) -> None:
        """Test should_include_file for regular files with exclude patterns."""
        config = BackupConfig(
            include_patterns=["**/*.py", "**/*.js"],
            exclude_patterns=["**/node_modules/**", "**/__pycache__/**"],
        )
        file_filter = FileFilter(config)

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create files matching exclude patterns
            node_modules_file = Path(temp_dir) / "node_modules" / "package" / "index.js"
            node_modules_file.parent.mkdir(parents=True)
            node_modules_file.touch()

            pycache_file = Path(temp_dir) / "__pycache__" / "module.pyc"
            pycache_file.parent.mkdir(parents=True)
            pycache_file.touch()

            # Mock git detector to return None (not in git repo)
            with patch.object(
                file_filter.git_detector, "get_repository_for_path", return_value=None
            ):
                # Test excluded files
                should_include, reason = file_filter.should_include_file(
                    node_modules_file
                )
                assert should_include is False
                assert "exclude pattern" in reason

                should_include, reason = file_filter.should_include_file(pycache_file)
                assert should_include is False
                assert "exclude pattern" in reason

    def test_should_include_regular_file_include_pattern(self) -> None:
        """Test should_include_file for regular files with include patterns."""
        config = BackupConfig(
            include_patterns=["**/*.py", "**/*.js"], exclude_patterns=["**/temp/**"]
        )
        file_filter = FileFilter(config)

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create files matching include patterns
            python_file = Path(temp_dir) / "src" / "main.py"
            python_file.parent.mkdir(parents=True)
            python_file.touch()

            js_file = Path(temp_dir) / "script.js"
            js_file.touch()

            # Create file not matching include patterns
            txt_file = Path(temp_dir) / "readme.txt"
            txt_file.touch()

            # Mock git detector to return None (not in git repo)
            with patch.object(
                file_filter.git_detector, "get_repository_for_path", return_value=None
            ):
                # Test included files
                should_include, reason = file_filter.should_include_file(python_file)
                assert should_include is True
                assert "include pattern" in reason

                should_include, reason = file_filter.should_include_file(js_file)
                assert should_include is True
                assert "include pattern" in reason

                # Test file not matching include patterns
                should_include, reason = file_filter.should_include_file(txt_file)
                assert should_include is False
                assert "Does not match any include pattern" in reason

    def test_should_include_directory_basic(self) -> None:
        """Test should_include_directory for basic directories."""
        config = BackupConfig(exclude_patterns=["**/temp/**", "**/node_modules/**"])
        file_filter = FileFilter(config)

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create regular directory
            regular_dir = Path(temp_dir) / "src"
            regular_dir.mkdir()

            # Create excluded directory
            temp_dir_path = Path(temp_dir) / "temp"
            temp_dir_path.mkdir()

            node_modules_dir = Path(temp_dir) / "node_modules"
            node_modules_dir.mkdir()

            # Mock git detector to return None (not in git repo)
            with patch.object(
                file_filter.git_detector, "get_repository_for_path", return_value=None
            ):
                # Test regular directory
                should_include, reason = file_filter.should_include_directory(
                    regular_dir
                )
                assert should_include is True
                assert "traversal allowed" in reason

                # Test excluded directories
                should_include, reason = file_filter.should_include_directory(
                    temp_dir_path
                )
                assert should_include is False
                assert "exclude pattern" in reason

                should_include, reason = file_filter.should_include_directory(
                    node_modules_dir
                )
                assert should_include is False
                assert "exclude pattern" in reason

    def test_should_include_directory_git_repo(self) -> None:
        """Test should_include_directory for directories in git repository."""
        config = BackupConfig(exclude_patterns=["**/temp/**"])
        file_filter = FileFilter(config)

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            repo = git.Repo.init(repo_path)

            # Create directory that would normally be excluded
            temp_dir_in_repo = repo_path / "temp"
            temp_dir_in_repo.mkdir()

            # Mock git detector
            with patch.object(
                file_filter.git_detector, "get_repository_for_path"
            ) as mock_get_repo:
                from sysforge.backup.git import GitRepository

                mock_git_repo = GitRepository(repo_path, repo)
                mock_get_repo.return_value = mock_git_repo

                # Directory in git repo that matches exclude pattern excluded
                # (new behavior for performance)
                should_include, reason = file_filter.should_include_directory(
                    temp_dir_in_repo
                )
                assert should_include is False
                assert "exclude pattern" in reason

    def test_get_filtered_files_integration(self) -> None:
        """Test get_filtered_files integration."""
        config = BackupConfig(
            include_patterns=["**/*.py", "**/*.txt"],
            exclude_patterns=["**/temp/**"],
            always_exclude=["**/*.log"],
        )
        file_filter = FileFilter(config)

        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)

            # Create directory structure
            src_dir = base_path / "src"
            src_dir.mkdir()

            temp_dir_path = base_path / "temp"
            temp_dir_path.mkdir()

            # Create files
            (src_dir / "main.py").touch()
            (src_dir / "utils.py").touch()
            (base_path / "readme.txt").touch()
            (temp_dir_path / "temp_file.py").touch()  # Should be excluded
            (base_path / "debug.log").touch()  # Should be always excluded
            (base_path / "ignore.bin").touch()  # Should not match include patterns

            # Mock git detector to find no repositories
            with patch.object(
                file_filter, "_discover_git_repositories_fast", return_value=[]
            ):
                with patch.object(
                    file_filter.git_detector,
                    "get_repository_for_path",
                    return_value=None,
                ):
                    # Mock the subprocess calls for find command
                    with patch("subprocess.run") as mock_run:
                        # Mock successful find results
                        mock_result = type(
                            "MockResult",
                            (),
                            {
                                "returncode": 0,
                                "stdout": (
                                    f"{src_dir / 'main.py'}\0{src_dir / 'utils.py'}\0"
                                    f"{base_path / 'readme.txt'}\0"
                                ),
                                "stderr": "",
                            },
                        )()
                        mock_run.return_value = mock_result

                        filtered_files = file_filter.get_filtered_files(base_path)

            # Convert to names for easier testing
            file_names = {f.name for f in filtered_files}

            # Should include
            assert "main.py" in file_names
            assert "utils.py" in file_names
            assert "readme.txt" in file_names

            # Should exclude
            assert "temp_file.py" not in file_names  # In temp directory
            assert "debug.log" not in file_names  # Always exclude
            assert "ignore.bin" not in file_names  # Doesn't match include patterns

    def test_get_filter_stats(self) -> None:
        """Test get_filter_stats method."""
        config = BackupConfig(
            include_patterns=["*.py", "*.js"],
            exclude_patterns=["*/temp/**", "*/node_modules/**"],
            always_exclude=["*.log", "*.tmp"],
        )
        file_filter = FileFilter(config)

        # Mock git detector stats
        with patch.object(
            file_filter.git_detector, "get_repository_stats"
        ) as mock_stats:
            mock_stats.return_value = {"total_repositories": 3, "scanned_paths": 10}

            stats = file_filter.get_filter_stats()

            assert stats["git_repositories"] == 3
            assert stats["max_file_size_bytes"] == config.get_max_file_size_bytes()
            assert stats["include_patterns_count"] == 2
            assert stats["exclude_patterns_count"] == 2
            assert stats["always_exclude_patterns_count"] == 2
