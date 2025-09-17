"""Git repository detection and handling."""

import os
from pathlib import Path
from typing import Any, Optional

import git
from git import InvalidGitRepositoryError, NoSuchPathError


class GitRepository:
    """Represents a Git repository."""

    def __init__(self, repo_path: Path, repo: git.Repo):
        self.path = repo_path
        self.repo = repo
        self.git_dir = Path(repo.git_dir)

    def contains_path(self, path: Path) -> bool:
        """Check if a path is within this repository."""
        try:
            repo_root = Path(self.repo.working_dir)
            return path.resolve().is_relative_to(repo_root.resolve())
        except (ValueError, OSError):
            return False

    def is_tracked_file(self, file_path: Path) -> bool:
        """Check if a file is tracked by git."""
        try:
            # Resolve paths to handle symlinks (e.g., macOS /var -> /private/var)
            resolved_file_path = file_path.resolve()
            resolved_working_dir = Path(self.repo.working_dir).resolve()
            relative_path = resolved_file_path.relative_to(resolved_working_dir)
            # Check if file is in git index
            return str(relative_path) in self.repo.git.ls_files().split("\n")
        except (ValueError, git.GitCommandError):
            return False

    def get_untracked_files(self) -> list[Path]:
        """Get list of untracked files."""
        try:
            repo_root = Path(self.repo.working_dir).resolve()
            untracked = self.repo.untracked_files
            return [repo_root / file for file in untracked]
        except git.GitCommandError:
            return []

    def get_ignored_files(self) -> list[Path]:
        """Get list of ignored files."""
        try:
            repo_root = Path(self.repo.working_dir).resolve()
            # Get all files that are ignored by git
            ignored_output = self.repo.git.ls_files(
                "--others", "--ignored", "--exclude-standard"
            )
            if not ignored_output:
                return []

            ignored_files = ignored_output.split("\n")
            return [repo_root / file for file in ignored_files if file]
        except git.GitCommandError:
            return []

    def is_ignored(self, file_path: Path) -> bool:
        """Check if a file or directory is ignored by git."""
        try:
            # Resolve paths to handle symlinks (e.g., macOS /var -> /private/var)
            resolved_file_path = file_path.resolve()
            resolved_repo_root = Path(self.repo.working_dir).resolve()
            relative_path = resolved_file_path.relative_to(resolved_repo_root)

            # Use git check-ignore to check if path is ignored
            try:
                self.repo.git.check_ignore(str(relative_path))
                return True  # If check-ignore succeeds, the path is ignored
            except git.GitCommandError:
                return False  # If check-ignore fails, the path is not ignored
        except (ValueError, git.GitCommandError):
            return False

    def get_all_repo_files(self, include_git_dir: bool = True) -> list[Path]:
        """Get ALL files in repository including .git directory and ignored files."""
        repo_root = Path(self.repo.working_dir)
        all_files = []

        # Add .git directory files if requested
        if include_git_dir:
            all_files.extend(self._get_git_directory_files(repo_root))

        # Add all repository files
        all_files.extend(self._get_tracked_files(repo_root))
        all_files.extend(self._get_untracked_files(repo_root))
        all_files.extend(self._get_ignored_files(repo_root))

        return self._deduplicate_files(all_files)

    def _get_git_directory_files(self, repo_root: Path) -> list[Path]:
        """Get all files in the .git directory."""
        git_dir = repo_root / ".git"
        if not git_dir.exists():
            return []

        return [file_path for file_path in git_dir.rglob("*") if file_path.is_file()]

    def _get_tracked_files(self, repo_root: Path) -> list[Path]:
        """Get all tracked files from git."""
        try:
            tracked_output = self.repo.git.ls_files()
            if not tracked_output:
                return []
            return [repo_root / file for file in tracked_output.split("\n") if file]
        except git.GitCommandError:
            return []

    def _get_untracked_files(self, repo_root: Path) -> list[Path]:
        """Get all untracked files from git."""
        try:
            untracked_output = self.repo.git.ls_files("--others")
            if not untracked_output:
                return []
            return [repo_root / file for file in untracked_output.split("\n") if file]
        except git.GitCommandError:
            return []

    def _get_ignored_files(self, repo_root: Path) -> list[Path]:
        """Get all ignored files from git."""
        try:
            ignored_output = self.repo.git.ls_files(
                "--others", "--ignored", "--exclude-standard"
            )
            if not ignored_output:
                return []
            return [repo_root / file for file in ignored_output.split("\n") if file]
        except git.GitCommandError:
            return []

    def _deduplicate_files(self, all_files: list[Path]) -> list[Path]:
        """Remove duplicates and ensure all files exist."""
        unique_files = []
        seen = set()
        for file_path in all_files:
            if file_path not in seen and file_path.exists() and file_path.is_file():
                unique_files.append(file_path)
                seen.add(file_path)
        return unique_files

    def get_override_files(self, patterns: list[str]) -> list[Path]:
        """Get files matching override patterns, including ignored files."""
        repo_root = Path(self.repo.working_dir)

        # Get all candidate files from git and filesystem
        all_candidate_files = self._get_all_candidate_files(repo_root, patterns)

        # Filter files by patterns
        override_files = self._filter_files_by_patterns(
            all_candidate_files, repo_root, patterns
        )

        return list(set(override_files))

    def _get_all_candidate_files(
        self, repo_root: Path, patterns: list[str]
    ) -> list[Path]:
        """Get all files that could match override patterns."""
        all_files = []

        # Get files from git
        all_files.extend(self._get_tracked_files(repo_root))
        all_files.extend(self._get_untracked_files(repo_root))
        all_files.extend(self._get_ignored_files(repo_root))

        # Get files from filesystem using glob patterns
        all_files.extend(self._get_glob_matches(repo_root, patterns))

        return all_files

    def _get_glob_matches(self, repo_root: Path, patterns: list[str]) -> list[Path]:
        """Get files matching glob patterns from filesystem."""
        glob_files = []
        for pattern in patterns:
            glob_pattern = pattern.replace("**/", "")
            try:
                matching_files = list(repo_root.rglob(glob_pattern))
                glob_files.extend(matching_files)
            except Exception as e:
                # Skip invalid glob patterns
                print(f"Warning: skipping invalid glob pattern '{glob_pattern}': {e}")
                continue
        return glob_files

    def _filter_files_by_patterns(
        self, files: list[Path], repo_root: Path, patterns: list[str]
    ) -> list[Path]:
        """Filter files that match the given patterns."""
        import fnmatch

        override_files = []
        for file_path in files:
            if not (file_path.exists() and file_path.is_file()):
                continue

            matches = self._file_matches_patterns(
                file_path, repo_root, patterns, fnmatch
            )
            if matches:
                override_files.append(file_path)

        return override_files

    def _file_matches_patterns(
        self, file_path: Path, repo_root: Path, patterns: list[str], fnmatch
    ) -> bool:
        """Check if a file matches any of the given patterns."""
        try:
            relative_path = str(file_path.relative_to(repo_root))
            for pattern in patterns:
                glob_pattern = pattern.replace("**/", "")
                if (
                    fnmatch.fnmatch(relative_path, glob_pattern)
                    or fnmatch.fnmatch(file_path.name, glob_pattern)
                    or fnmatch.fnmatch(relative_path, pattern)
                ):
                    return True
        except ValueError:
            pass
        return False


class GitDetector:
    """Detects and manages Git repositories in a directory tree."""

    def __init__(self) -> None:
        self._repositories: dict[Path, GitRepository] = {}
        self._scanned_paths: set[Path] = set()

    def find_repositories(
        self, base_path: Path, file_filter: Optional[Any] = None
    ) -> list[GitRepository]:
        """Find all Git repositories under the given path."""
        repositories: list[GitRepository] = []
        scanned_dirs = 0

        # Walk the directory tree
        try:
            for root, dirs, _files in os.walk(base_path):
                root_path = Path(root)
                scanned_dirs += 1

                if scanned_dirs % 1000 == 0:
                    repo_count = len(repositories)
                    print(f"Git scan: {scanned_dirs} dirs, {repo_count} repos")
                    print(f"Current git scan directory: {root_path}")

                # Skip if we've already scanned this path
                if root_path in self._scanned_paths:
                    continue

                # If we have a file filter, check if we should traverse this directory
                if file_filter and hasattr(file_filter, "should_include_directory"):
                    should_traverse, reason = file_filter.should_include_directory(
                        root_path
                    )
                    if not should_traverse:
                        print(f"Skipping dir during git scan: {root_path} ({reason})")
                        dirs.clear()
                        continue

                # Check if current directory is a git repository
                if (root_path / ".git").exists():
                    print(f"Found .git directory at: {root_path}")
                    try:
                        repo = git.Repo(root_path)
                        git_repo = GitRepository(root_path, repo)
                        repositories.append(git_repo)
                        self._repositories[root_path] = git_repo
                        print(f"Successfully loaded git repo: {root_path}")

                        # Mark all subdirectories as scanned to avoid duplicates
                        repo_root = Path(repo.working_dir)
                        self._scanned_paths.add(repo_root)

                        # Remove subdirectories from dirs to prevent descending
                        # into them (they're part of this git repository)
                        dirs.clear()

                    except (InvalidGitRepositoryError, NoSuchPathError) as e:
                        print(f"Invalid git repository at {root_path}: {e}")
                        # Not a valid git repository, continue scanning
                        pass

                # Filter directories for next iteration
                if file_filter and hasattr(file_filter, "should_include_directory"):
                    dirs_to_remove = []
                    for dir_name in dirs:
                        dir_path = root_path / dir_name
                        should_traverse, reason = file_filter.should_include_directory(
                            dir_path
                        )
                        if not should_traverse:
                            dirs_to_remove.append(dir_name)

                    for dir_name in dirs_to_remove:
                        dirs.remove(dir_name)

        except (OSError, PermissionError) as e:
            print(f"Permission error during git scan: {e}")
            # Skip directories we can't access
            pass

        repo_count = len(repositories)
        print(
            f"Git discovery complete: {repo_count} repos, {scanned_dirs} dirs scanned"
        )
        return repositories

    def get_repository_for_path(self, path: Path) -> Optional[GitRepository]:
        """Get the Git repository that contains the given path."""
        path = path.resolve()

        # Check cached repositories first
        for _repo_path, repo in self._repositories.items():
            if repo.contains_path(path):
                return repo

        # Try to find repository by walking up the directory tree
        current = path if path.is_dir() else path.parent

        while current != current.parent:
            try:
                if (current / ".git").exists():
                    repo_obj = git.Repo(current)
                    git_repo = GitRepository(current, repo_obj)
                    self._repositories[current] = git_repo
                    return git_repo
            except (InvalidGitRepositoryError, NoSuchPathError):
                pass

            current = current.parent

        return None

    def is_in_git_repository(self, path: Path) -> bool:
        """Check if a path is within any Git repository."""
        return self.get_repository_for_path(path) is not None

    def should_include_file(
        self, file_path: Path, include_git_dirs: bool = True
    ) -> bool:
        """Determine if a file should be included in backup based on git status.

        For files in git repositories:
        - Include all tracked files
        - Include all untracked files (they might be work in progress)
        - Optionally include .git directory contents
        """
        repo = self.get_repository_for_path(file_path)
        if not repo:
            # Not in a git repository, use regular filtering
            return True

        # Check if this is the .git directory itself
        if file_path.is_relative_to(repo.git_dir):
            return include_git_dirs

        # For files in git repositories, include everything except what git ignores
        # (unless explicitly configured otherwise)
        return True

    def get_repository_stats(self) -> dict[str, int]:
        """Get statistics about detected repositories."""
        return {
            "total_repositories": len(self._repositories),
            "scanned_paths": len(self._scanned_paths),
        }

    def clear_cache(self) -> None:
        """Clear the repository cache."""
        self._repositories.clear()
        self._scanned_paths.clear()


def find_git_repositories(base_path: Path) -> list[GitRepository]:
    """Convenience function to find all git repositories under a path."""
    detector = GitDetector()
    return detector.find_repositories(base_path)


def is_git_repository(path: Path) -> bool:
    """Check if a path is a git repository."""
    try:
        git.Repo(path)
        return True
    except (InvalidGitRepositoryError, NoSuchPathError):
        return False
