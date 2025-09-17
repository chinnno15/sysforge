"""Tests for git repository detection and handling."""

import tempfile
from pathlib import Path

import git

from sysforge.backup.git import (
    GitDetector,
    GitRepository,
    find_git_repositories,
    is_git_repository,
)


class TestGitRepository:
    """Test GitRepository class."""

    def test_git_repository_creation(self) -> None:
        """Test GitRepository creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            repo = git.Repo.init(repo_path)

            # Create GitRepository instance
            git_repo = GitRepository(repo_path, repo)

            assert git_repo.path == repo_path
            assert git_repo.repo == repo
            assert git_repo.git_dir == Path(repo.git_dir)

    def test_contains_path_inside_repo(self) -> None:
        """Test contains_path for path inside repository."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            repo = git.Repo.init(repo_path)
            git_repo = GitRepository(repo_path, repo)

            # Test file inside repo
            test_file = repo_path / "test_file.py"
            test_file.touch()

            assert git_repo.contains_path(test_file) is True

            # Test subdirectory inside repo
            sub_dir = repo_path / "subdir"
            sub_dir.mkdir()

            assert git_repo.contains_path(sub_dir) is True

    def test_contains_path_outside_repo(self) -> None:
        """Test contains_path for path outside repository."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            repo = git.Repo.init(repo_path)
            git_repo = GitRepository(repo_path, repo)

            # Test file outside repo
            outside_file = Path(temp_dir) / "outside_file.py"
            outside_file.touch()

            assert git_repo.contains_path(outside_file) is False

    def test_is_tracked_file_tracked(self) -> None:
        """Test is_tracked_file for tracked file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            repo = git.Repo.init(repo_path)

            # Create and track a file
            test_file = repo_path / "tracked_file.py"
            test_file.write_text("print('hello')")
            repo.index.add([str(test_file)])
            repo.index.commit("Initial commit")

            git_repo = GitRepository(repo_path, repo)

            assert git_repo.is_tracked_file(test_file) is True

    def test_is_tracked_file_untracked(self) -> None:
        """Test is_tracked_file for untracked file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            repo = git.Repo.init(repo_path)
            git_repo = GitRepository(repo_path, repo)

            # Create untracked file
            untracked_file = repo_path / "untracked_file.py"
            untracked_file.write_text("print('untracked')")

            assert git_repo.is_tracked_file(untracked_file) is False

    def test_get_untracked_files(self) -> None:
        """Test getting untracked files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            repo = git.Repo.init(repo_path)

            # Create tracked file
            tracked_file = repo_path / "tracked.py"
            tracked_file.write_text("tracked")
            repo.index.add([str(tracked_file)])
            repo.index.commit("Initial commit")

            # Create untracked file
            untracked_file = repo_path / "untracked.py"
            untracked_file.write_text("untracked")

            git_repo = GitRepository(repo_path, repo)
            untracked_files = git_repo.get_untracked_files()

            assert len(untracked_files) == 1
            assert untracked_files[0].name == "untracked.py"


class TestGitDetector:
    """Test GitDetector class."""

    def test_find_repositories_empty_directory(self) -> None:
        """Test finding repositories in empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            detector = GitDetector()
            repositories = detector.find_repositories(Path(temp_dir))
            assert len(repositories) == 0

    def test_find_repositories_single_repo(self) -> None:
        """Test finding single repository."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            git.Repo.init(repo_path)

            detector = GitDetector()
            repositories = detector.find_repositories(Path(temp_dir))

            assert len(repositories) == 1
            assert repositories[0].path == repo_path

    def test_find_repositories_multiple_repos(self) -> None:
        """Test finding multiple repositories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create multiple git repositories
            repo1_path = temp_path / "repo1"
            repo1_path.mkdir()
            git.Repo.init(repo1_path)

            repo2_path = temp_path / "repo2"
            repo2_path.mkdir()
            git.Repo.init(repo2_path)

            # Create non-git directory
            non_git_path = temp_path / "not_a_repo"
            non_git_path.mkdir()

            detector = GitDetector()
            repositories = detector.find_repositories(temp_path)

            assert len(repositories) == 2
            repo_paths = {repo.path for repo in repositories}
            assert repo1_path in repo_paths
            assert repo2_path in repo_paths

    def test_find_repositories_nested_directories(self) -> None:
        """Test finding repositories in nested directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create nested structure with git repo
            nested_path = temp_path / "level1" / "level2" / "repo"
            nested_path.mkdir(parents=True)
            git.Repo.init(nested_path)

            detector = GitDetector()
            repositories = detector.find_repositories(temp_path)

            assert len(repositories) == 1
            assert repositories[0].path == nested_path

    def test_find_repositories_ignores_subdirectories_of_repos(self) -> None:
        """Test that subdirectories of git repos are not scanned separately."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create git repository
            repo_path = temp_path / "main_repo"
            repo_path.mkdir()
            git.Repo.init(repo_path)

            # Create subdirectories (these should not be scanned)
            sub_dir1 = repo_path / "subdir1"
            sub_dir1.mkdir()

            sub_dir2 = repo_path / "subdir2"
            sub_dir2.mkdir()

            detector = GitDetector()
            repositories = detector.find_repositories(temp_path)

            # Should only find the main repository
            assert len(repositories) == 1
            assert repositories[0].path == repo_path

    def test_get_repository_for_path_inside_repo(self) -> None:
        """Test getting repository for path inside repo."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_path = temp_path / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            git.Repo.init(repo_path)

            detector = GitDetector()
            # First find the repository
            detector.find_repositories(temp_path)

            # Test path inside repo
            test_file = repo_path / "test_file.py"
            test_file.touch()

            found_repo = detector.get_repository_for_path(test_file)
            assert found_repo is not None
            assert found_repo.path == repo_path

    def test_get_repository_for_path_outside_repo(self) -> None:
        """Test getting repository for path outside repo."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_path = temp_path / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            git.Repo.init(repo_path)

            detector = GitDetector()

            # Test path outside repo
            outside_file = temp_path / "outside_file.py"
            outside_file.touch()

            found_repo = detector.get_repository_for_path(outside_file)
            assert found_repo is None

    def test_is_in_git_repository(self) -> None:
        """Test is_in_git_repository method."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_path = temp_path / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            git.Repo.init(repo_path)

            detector = GitDetector()

            # Test file inside repo
            inside_file = repo_path / "inside.py"
            inside_file.touch()
            assert detector.is_in_git_repository(inside_file) is True

            # Test file outside repo
            outside_file = temp_path / "outside.py"
            outside_file.touch()
            assert detector.is_in_git_repository(outside_file) is False

    def test_should_include_file_git_repo(self) -> None:
        """Test should_include_file for files in git repository."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_path = temp_path / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            repo = git.Repo.init(repo_path)

            detector = GitDetector()

            # Test regular file in git repo
            test_file = repo_path / "test.py"
            test_file.touch()
            assert detector.should_include_file(test_file) is True

            # Test .git directory file
            git_file = Path(repo.git_dir) / "config"
            assert detector.should_include_file(git_file, include_git_dirs=True) is True
            assert (
                detector.should_include_file(git_file, include_git_dirs=False) is False
            )

    def test_should_include_file_non_git(self) -> None:
        """Test should_include_file for files outside git repository."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            detector = GitDetector()

            # Test file outside git repo
            test_file = temp_path / "test.py"
            test_file.touch()
            assert detector.should_include_file(test_file) is True

    def test_get_repository_stats(self) -> None:
        """Test getting repository statistics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_path = temp_path / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            git.Repo.init(repo_path)

            detector = GitDetector()
            detector.find_repositories(temp_path)

            stats = detector.get_repository_stats()
            assert stats["total_repositories"] == 1
            assert stats["scanned_paths"] >= 1

    def test_clear_cache(self) -> None:
        """Test clearing repository cache."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_path = temp_path / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            git.Repo.init(repo_path)

            detector = GitDetector()
            detector.find_repositories(temp_path)

            # Verify cache has data
            assert len(detector._repositories) > 0
            assert len(detector._scanned_paths) > 0

            # Clear cache
            detector.clear_cache()

            # Verify cache is empty
            assert len(detector._repositories) == 0
            assert len(detector._scanned_paths) == 0


class TestGitUtilityFunctions:
    """Test utility functions."""

    def test_find_git_repositories(self) -> None:
        """Test find_git_repositories function."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_path = temp_path / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            git.Repo.init(repo_path)

            repositories = find_git_repositories(temp_path)

            assert len(repositories) == 1
            assert repositories[0].path == repo_path

    def test_is_git_repository_true(self) -> None:
        """Test is_git_repository for valid repository."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            git.Repo.init(repo_path)

            assert is_git_repository(repo_path) is True

    def test_is_git_repository_false(self) -> None:
        """Test is_git_repository for non-repository."""
        with tempfile.TemporaryDirectory() as temp_dir:
            non_repo_path = Path(temp_dir) / "not_a_repo"
            non_repo_path.mkdir()

            assert is_git_repository(non_repo_path) is False

    def test_is_git_repository_nonexistent_path(self) -> None:
        """Test is_git_repository for nonexistent path."""
        nonexistent_path = Path("/nonexistent/path")
        assert is_git_repository(nonexistent_path) is False
