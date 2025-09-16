"""Git repository detection and handling."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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
            relative_path = file_path.relative_to(Path(self.repo.working_dir))
            # Check if file is in git index
            return str(relative_path) in self.repo.git.ls_files().split('\n')
        except (ValueError, git.GitCommandError):
            return False

    def get_untracked_files(self) -> List[Path]:
        """Get list of untracked files."""
        try:
            repo_root = Path(self.repo.working_dir)
            untracked = self.repo.untracked_files
            return [repo_root / file for file in untracked]
        except git.GitCommandError:
            return []

    def get_ignored_files(self) -> List[Path]:
        """Get list of ignored files."""
        try:
            repo_root = Path(self.repo.working_dir)
            # Get all files that are ignored by git
            ignored_output = self.repo.git.ls_files('--others', '--ignored', '--exclude-standard')
            if not ignored_output:
                return []

            ignored_files = ignored_output.split('\n')
            return [repo_root / file for file in ignored_files if file]
        except git.GitCommandError:
            return []

    def is_ignored(self, file_path: Path) -> bool:
        """Check if a file or directory is ignored by git."""
        try:
            repo_root = Path(self.repo.working_dir)
            relative_path = file_path.relative_to(repo_root)
            
            # Use git check-ignore to check if path is ignored
            try:
                self.repo.git.check_ignore(str(relative_path))
                return True  # If check-ignore succeeds, the path is ignored
            except git.GitCommandError:
                return False  # If check-ignore fails, the path is not ignored
        except (ValueError, git.GitCommandError):
            return False

    def get_all_repo_files(self, include_git_dir: bool = True) -> List[Path]:
        """Get ALL files in repository including .git directory and ignored files."""
        repo_root = Path(self.repo.working_dir)
        all_files = []
        
        # Always include the entire .git directory if requested
        if include_git_dir:
            git_dir = repo_root / '.git'
            if git_dir.exists():
                # Recursively get all files in .git directory
                for file_path in git_dir.rglob('*'):
                    if file_path.is_file():
                        all_files.append(file_path)
        
        # Get all tracked files
        try:
            tracked_output = self.repo.git.ls_files()
            if tracked_output:
                tracked = tracked_output.split('\n')
                for file in tracked:
                    if file:
                        all_files.append(repo_root / file)
        except git.GitCommandError:
            pass
        
        # Get all untracked files (including ignored)
        try:
            untracked_output = self.repo.git.ls_files('--others')
            if untracked_output:
                untracked = untracked_output.split('\n')
                for file in untracked:
                    if file:
                        all_files.append(repo_root / file)
        except git.GitCommandError:
            pass
        
        # Get all ignored files explicitly
        try:
            ignored_output = self.repo.git.ls_files('--others', '--ignored', '--exclude-standard')
            if ignored_output:
                ignored = ignored_output.split('\n')
                for file in ignored:
                    if file:
                        all_files.append(repo_root / file)
        except git.GitCommandError:
            pass
        
        # Remove duplicates and ensure all files exist
        unique_files = []
        seen = set()
        for file_path in all_files:
            if file_path not in seen and file_path.exists() and file_path.is_file():
                unique_files.append(file_path)
                seen.add(file_path)
        
        return unique_files

    def get_override_files(self, patterns: List[str]) -> List[Path]:
        """Get files matching override patterns, including ignored files."""
        repo_root = Path(self.repo.working_dir)
        override_files = []
        
        # Import fnmatch for pattern matching
        import fnmatch
        
        # Get all files that exist in the repository (tracked, untracked, and ignored)
        all_candidate_files = []
        
        # Get all files from git repository
        try:
            # Get tracked files
            tracked_output = self.repo.git.ls_files()
            if tracked_output:
                files = tracked_output.split('\n')
                for file in files:
                    if file:
                        all_candidate_files.append(repo_root / file)
        except git.GitCommandError:
            pass
            
        try:
            # Get untracked files
            untracked_output = self.repo.git.ls_files('--others')
            if untracked_output:
                files = untracked_output.split('\n')
                for file in files:
                    if file:
                        all_candidate_files.append(repo_root / file)
        except git.GitCommandError:
            pass
            
        try:
            # Get ignored files
            ignored_output = self.repo.git.ls_files('--others', '--ignored', '--exclude-standard')
            if ignored_output:
                files = ignored_output.split('\n')
                for file in files:
                    if file:
                        all_candidate_files.append(repo_root / file)
        except git.GitCommandError:
            pass
        
        # Also search filesystem using glob patterns directly
        for pattern in patterns:
            # Remove leading **/ from pattern for rglob
            glob_pattern = pattern.replace('**/', '')
            try:
                matching_files = list(repo_root.rglob(glob_pattern))
                all_candidate_files.extend(matching_files)
            except Exception:
                # Ignore glob errors
                pass
        
        # Filter all candidate files by patterns
        for file_path in all_candidate_files:
            if file_path.exists() and file_path.is_file():
                try:
                    relative_path = str(file_path.relative_to(repo_root))
                    for pattern in patterns:
                        # Convert glob pattern to fnmatch pattern for relative path
                        glob_pattern = pattern.replace('**/', '')
                        if (fnmatch.fnmatch(relative_path, glob_pattern) or 
                            fnmatch.fnmatch(file_path.name, glob_pattern) or
                            fnmatch.fnmatch(relative_path, pattern)):
                            override_files.append(file_path)
                            break
                except ValueError:
                    # Skip files that can't be made relative to repo_root
                    continue
        
        # Remove duplicates
        return list(set(override_files))


class GitDetector:
    """Detects and manages Git repositories in a directory tree."""

    def __init__(self) -> None:
        self._repositories: Dict[Path, GitRepository] = {}
        self._scanned_paths: Set[Path] = set()

    def find_repositories(self, base_path: Path, file_filter: Optional[Any] = None) -> List[GitRepository]:
        """Find all Git repositories under the given path."""
        repositories: List[GitRepository] = []
        scanned_dirs = 0

        # Walk the directory tree
        try:
            for root, dirs, files in os.walk(base_path):
                root_path = Path(root)
                scanned_dirs += 1
                
                if scanned_dirs % 1000 == 0:
                    print(f"Git scan: processed {scanned_dirs} directories, found {len(repositories)} repositories")
                    print(f"Current git scan directory: {root_path}")

                # Skip if we've already scanned this path
                if root_path in self._scanned_paths:
                    continue

                # If we have a file filter, use it to check if we should traverse this directory
                if file_filter and hasattr(file_filter, 'should_include_directory'):
                    should_traverse, reason = file_filter.should_include_directory(root_path)
                    if not should_traverse:
                        print(f"Skipping directory during git scan: {root_path} ({reason})")
                        dirs.clear()
                        continue

                # Check if current directory is a git repository
                if (root_path / '.git').exists():
                    print(f"Found .git directory at: {root_path}")
                    try:
                        repo = git.Repo(root_path)
                        git_repo = GitRepository(root_path, repo)
                        repositories.append(git_repo)
                        self._repositories[root_path] = git_repo
                        print(f"Successfully loaded git repo: {root_path}")

                        # Mark all subdirectories as scanned to avoid duplicate detection
                        repo_root = Path(repo.working_dir)
                        self._scanned_paths.add(repo_root)

                        # Remove subdirectories from dirs to prevent os.walk from descending
                        # into them (they're part of this git repository)
                        dirs.clear()

                    except (InvalidGitRepositoryError, NoSuchPathError) as e:
                        print(f"Invalid git repository at {root_path}: {e}")
                        # Not a valid git repository, continue scanning
                        pass

                # Filter directories for next iteration
                if file_filter and hasattr(file_filter, 'should_include_directory'):
                    dirs_to_remove = []
                    for dir_name in dirs:
                        dir_path = root_path / dir_name
                        should_traverse, reason = file_filter.should_include_directory(dir_path)
                        if not should_traverse:
                            dirs_to_remove.append(dir_name)
                    
                    for dir_name in dirs_to_remove:
                        dirs.remove(dir_name)

        except (OSError, PermissionError) as e:
            print(f"Permission error during git scan: {e}")
            # Skip directories we can't access
            pass

        print(f"Git repository discovery complete: found {len(repositories)} repositories after scanning {scanned_dirs} directories")
        return repositories

    def get_repository_for_path(self, path: Path) -> Optional[GitRepository]:
        """Get the Git repository that contains the given path."""
        path = path.resolve()

        # Check cached repositories first
        for repo_path, repo in self._repositories.items():
            if repo.contains_path(path):
                return repo

        # Try to find repository by walking up the directory tree
        current = path if path.is_dir() else path.parent

        while current != current.parent:
            try:
                if (current / '.git').exists():
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

    def should_include_file(self, file_path: Path, include_git_dirs: bool = True) -> bool:
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

    def get_repository_stats(self) -> Dict[str, int]:
        """Get statistics about detected repositories."""
        return {
            "total_repositories": len(self._repositories),
            "scanned_paths": len(self._scanned_paths)
        }

    def clear_cache(self) -> None:
        """Clear the repository cache."""
        self._repositories.clear()
        self._scanned_paths.clear()


def find_git_repositories(base_path: Path) -> List[GitRepository]:
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
