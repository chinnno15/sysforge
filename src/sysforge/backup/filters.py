"""File filtering logic for backup operations."""

import subprocess
import os
import shlex
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Set

from .config import BackupConfig
from .git import GitDetector, GitRepository

import git


class FileFilter:
    """High-performance file filtering using native find command."""

    def __init__(self, config: BackupConfig):
        self.config = config
        self.git_detector = GitDetector()
        self.max_file_size_bytes = config.get_max_file_size_bytes()
        self.verbose = False
        self.console = None

    def _build_find_exclude_args(self) -> List[str]:
        """Build simplified find command exclusion arguments for performance."""
        args = []
        
        # Only add the most critical exclusions to keep find command fast
        home_dir = str(Path.home())
        critical_exclusions = [
            # Performance killers - browser caches
            '*/.cache/*', '*/.local/share/Trash/*', 
            '*/snap/*', '*/node_modules/*', '*/__pycache__/*',
            # Build and cache directories that can be huge
            '*/.mypy_cache/*', '*/.pytest_cache/*', '*/.ruff_cache/*',
            # Large data directories that are likely not user code/documents
            f'{home_dir}/data/*', f'{home_dir}/*/data/*', f'{home_dir}/*/*/data/*',
            f'{home_dir}/influxdb/*', f'{home_dir}/*_data/*', f'{home_dir}/*/wal/*',
            # Dot directory exclusions (except whitelisted)
            f'{home_dir}/.local/*', f'{home_dir}/.cache/*',
            f'{home_dir}/.cursor/*', f'{home_dir}/.docker/*'
        ]
        
        # Add critical exclusions
        for pattern in critical_exclusions:
            args.extend(['-not', '-path', pattern])
        
        # Add dot directory whitelist logic (only most common problematic ones)
        home_dir = str(Path.home())
        for dot_dir in ['.local', '.cache', '.cursor', '.docker', '.pyenv', '.npm']:
            if dot_dir not in self.config.dot_directory_whitelist:
                args.extend(['-not', '-path', f'{home_dir}/{dot_dir}/*'])
                
        return args
    
    def _build_find_include_args(self) -> List[str]:
        """Build simplified find command inclusion arguments for performance."""
        # Use common file types including shell scripts and config files
        common_extensions = [
            '*.py', '*.js', '*.ts', '*.md', '*.txt', '*.json', '*.yaml', '*.yml',
            '*.png', '*.jpg', '*.jpeg', '*.pdf', '*.doc', '*.docx',
            # Shell and script files  
            '*.sh', '*.bash', '*.zsh', '*.fish',
            # Config and dot files
            '*.conf', '*.config', '*.ini', '*.cfg'
        ]
        
        # Important specific files (dot files in home directory)
        important_files = [
            '.gitconfig', '.bashrc', '.zshrc', '.profile', '.vimrc',
            '.bash_profile', '.bash_aliases', '.tmux.conf', '.screenrc'
        ]
        
        # Important directories to include
        important_dirs = ['*src*', '*doc*', '*Pictures*', '*Documents*', '*Desktop*']
        
        args = ['(']
        first = True
        
        # Add common file extensions
        for ext in common_extensions:
            if not first:
                args.append('-o')
            args.extend(['-name', ext])
            first = False
        
        # Add important specific files
        for filename in important_files:
            if not first:
                args.append('-o')
            args.extend(['-name', filename])
            first = False
        
        # Add important directories
        for dir_pattern in important_dirs:
            if not first:
                args.append('-o')
            args.extend(['-path', dir_pattern])
            first = False
                
        args.append(')')
        return args

    def _is_home_root_dot_directory(self, dir_path: Path) -> bool:
        """Check if the directory is a dot directory at the root of the user home directory."""
        try:
            home_dir = Path.home()
            # Check if this directory is directly under home directory and starts with a dot
            if (dir_path.parent == home_dir and 
                dir_path.name.startswith('.') and 
                dir_path.is_dir()):
                return True
            return False
        except (OSError, RuntimeError):
            # In case we can't determine home directory
            return False

    def should_include_file(self, file_path: Path) -> tuple[bool, str]:
        """Determine if a file should be included in the backup.
        
        Returns:
            tuple: (should_include, reason)
        """
        # Check if file exists and is accessible
        try:
            if not file_path.exists():
                return False, "File does not exist"

            if not os.access(file_path, os.R_OK):
                return False, "File is not readable"
        except (OSError, PermissionError):
            return False, "Permission denied"

        # Check always exclude patterns first
        if self._matches_patterns(file_path, self.config.always_exclude):
            return False, "Matches always_exclude pattern"

        # Check file size limit
        if file_path.is_file():
            try:
                file_size = file_path.stat().st_size
                if file_size > self.max_file_size_bytes:
                    return False, f"File size ({file_size} bytes) exceeds limit"
            except OSError:
                return False, "Cannot determine file size"

        # Check if file is in a git repository
        git_repo = self.git_detector.get_repository_for_path(file_path)

        if git_repo:
            return self._should_include_git_file(file_path, git_repo)
        else:
            return self._should_include_regular_file(file_path)

    def _should_include_git_file(self, file_path: Path, git_repo: GitRepository) -> tuple[bool, str]:
        """Determine if a file in a git repository should be included."""
        # Check if this is the .git directory
        if file_path.is_relative_to(git_repo.git_dir):
            if self.config.git.include_git_dir:
                return True, "Git directory (included by config)"
            else:
                return False, "Git directory (excluded by config)"

        # Check if file is ignored by git (if respect_gitignore is enabled)
        if self.config.git.respect_gitignore and git_repo.is_ignored(file_path):
            # Check if file matches gitignore override patterns (backup even if gitignored)
            if self._matches_patterns(file_path, self.config.git.gitignore_override_patterns):
                # File is gitignored but matches override pattern - include it
                pass  # Continue to other checks
            else:
                return False, "File ignored by .gitignore"

        # For files in git repositories, we include them but still respect exclude patterns
        # for performance reasons (to avoid scanning large node_modules, etc.)
        if self._matches_patterns(file_path, self.config.exclude_patterns):
            return False, "File in git repository but matches exclude pattern"

        return True, "File in git repository"

    def _should_include_regular_file(self, file_path: Path) -> tuple[bool, str]:
        """Determine if a regular file (not in git) should be included."""
        # Check exclude patterns first
        if self._matches_patterns(file_path, self.config.exclude_patterns):
            return False, "Matches exclude pattern"

        # If no include patterns are specified, include by default
        if not self.config.include_patterns:
            return True, "No include patterns specified"

        # Check include patterns
        if self._matches_patterns(file_path, self.config.include_patterns):
            return True, "Matches include pattern"

        return False, "Does not match any include pattern"

    def should_include_directory(self, dir_path: Path) -> tuple[bool, str]:
        """Determine if a directory should be traversed.
        
        This is used to skip entire directory trees early for performance.
        """
        # Check if directory exists and is accessible
        try:
            if not dir_path.exists():
                return False, "Directory does not exist"

            if not os.access(dir_path, os.R_OK):
                return False, "Directory is not readable"
        except (OSError, PermissionError):
            return False, "Permission denied"

        # Check always exclude patterns
        if self._matches_patterns(dir_path, self.config.always_exclude):
            return False, "Matches always_exclude pattern"

        # Apply dot directory whitelist logic for root-level dot directories in home directory
        if self._is_home_root_dot_directory(dir_path):
            dot_dir_name = dir_path.name
            if dot_dir_name in self.config.dot_directory_whitelist:
                # This dot directory is whitelisted - continue with normal filtering
                pass
            else:
                return False, f"Root dot directory '{dot_dir_name}' not in whitelist"

        # Check if directory is in a git repository
        git_repo = self.git_detector.get_repository_for_path(dir_path)

        if git_repo:
            # For directories in git repos, include unless it's .git and not configured
            if dir_path.is_relative_to(git_repo.git_dir):
                if self.config.git.include_git_dir:
                    return True, "Git directory (included by config)"
                else:
                    return False, "Git directory (excluded by config)"
            
            # Check if directory is ignored by git (if respect_gitignore is enabled)
            if self.config.git.respect_gitignore and git_repo.is_ignored(dir_path):
                # Check if directory matches gitignore override patterns
                if self._matches_patterns(dir_path, self.config.git.gitignore_override_patterns):
                    # Directory is gitignored but matches override pattern - include it
                    pass  # Continue to other checks
                else:
                    return False, "Directory ignored by .gitignore"
            
            # Apply exclude patterns to directories in git repos for performance
            if self._matches_patterns(dir_path, self.config.exclude_patterns):
                return False, "Directory in git repository but matches exclude pattern"
                
            return True, "Directory in git repository"

        # For regular directories, check exclude patterns
        if self._matches_patterns(dir_path, self.config.exclude_patterns):
            return False, "Matches exclude pattern"

        # Include directory for traversal (individual files will be filtered)
        return True, "Directory traversal allowed"

    def get_filtered_files(self, base_path: Path, verbose: bool = False, console=None) -> List[Path]:
        """High-performance file discovery using native find command.
        
        This method uses find for 10-100x faster file discovery than os.walk.
        """
        self.verbose = verbose
        self.console = console
        
        if verbose and console:
            console.print(f"[dim]Using high-performance find-based file discovery...[/dim]")
            console.print(f"[dim]Scanning files in {base_path}...[/dim]")

        # First, discover all git repositories using find
        if verbose and console:
            console.print(f"[dim]Discovering git repositories in {base_path}...[/dim]")
        git_repos = self._discover_git_repositories_fast(base_path)
        
        if verbose and console:
            if git_repos:
                console.print(f"[dim]Found {len(git_repos)} git repositories:[/dim]")
                for repo in git_repos[:5]:  # Show first 5
                    console.print(f"[dim]  - {repo.path}[/dim]")
                if len(git_repos) > 5:
                    console.print(f"[dim]  ... and {len(git_repos) - 5} more[/dim]")
            else:
                console.print(f"[dim]No git repositories found[/dim]")

        # Get non-repository files using optimized parallel processing
        if self.config.enable_parallel_processing:
            file_paths = self._get_non_repository_files_parallel(base_path, git_repos, verbose, console)
        else:
            file_paths = self._get_non_repository_files_sequential(base_path, git_repos, verbose, console)
        
        # Apply file size filtering AND individual file filtering
        filtered_files = []
        for file_path in file_paths:
            # First check file size
            if not self._check_file_size(file_path):
                if verbose and console:
                    console.print(f"[dim]Excluded: {file_path} (size exceeds limit)[/dim]")
                continue
            
            # Then check if file should be included using our filtering rules
            should_include, reason = self.should_include_file(file_path)
            if should_include:
                filtered_files.append(file_path)
            elif verbose and console:
                console.print(f"[dim]Excluded: {file_path} ({reason})[/dim]")
        
        # Add complete git repository files (including .git directories and ignored files)
        if git_repos and self.config.git.include_repos:
            if self.config.enable_parallel_processing:
                git_files_filtered = self._get_repository_files_parallel(git_repos, verbose, console)
            else:
                git_files_filtered = self._get_repository_files_sequential(git_repos, verbose, console)

            # Add git files to main list and remove duplicates
            all_files = list(set(filtered_files + git_files_filtered))

            if verbose and console:
                console.print(f"[dim]Added {len(git_files_filtered)} files from {len(git_repos)} git repositories[/dim]")
                if self.config.git.respect_gitignore:
                    console.print(f"[dim]  - Respects gitignore but includes .git directories[/dim]")
                    console.print(f"[dim]  - Includes gitignored files matching override patterns (.env, etc.)[/dim]")
                else:
                    console.print(f"[dim]  - Includes complete .git directories for full restoration[/dim]")
                    console.print(f"[dim]  - Includes ALL repository files (ignores .gitignore)[/dim]")

            filtered_files = all_files
        
        if verbose and console:
            console.print(f"[dim]Find-based scan complete:[/dim]")
            console.print(f"[dim]  - Found {len(file_paths)} matching files from find[/dim]")
            console.print(f"[dim]  - Total {len(filtered_files)} files after git repos and filtering[/dim]")
            console.print(f"[dim]  - Scan completed in seconds vs minutes with os.walk[/dim]")
            
        return sorted(filtered_files)

    def _build_find_command(self, base_path: Path) -> List[str]:
        """Build optimized find command with all filtering rules."""
        # If scanning home directory, focus on important subdirectories only
        if base_path == Path.home():
            return self._build_focused_home_scan_command()
        else:
            cmd = ['find', str(base_path), '-type', 'f']
            
            # Add exclusion arguments
            exclude_args = self._build_find_exclude_args()
            cmd.extend(exclude_args)
            
            # Add inclusion arguments
            include_args = self._build_find_include_args()
            if include_args:
                cmd.extend(include_args)
            
            return cmd
    
    def _build_focused_home_scan_command(self) -> List[str]:
        """Build focused scan command for home directory to avoid scanning huge data dirs."""
        home_dir = Path.home()
        
        # Build two separate find commands:
        # 1. Home directory root with maxdepth 1 (for .gitconfig, *.sh files)  
        # 2. Specific subdirectories for deeper scanning
        
        # First: scan home directory root only (maxdepth 1)
        home_root_cmd = ['find', str(home_dir), '-maxdepth', '1', '-type', 'f']
        
        # Second: get subdirectories to scan deeply
        subdirs = []
        for dot_dir in self.config.dot_directory_whitelist:
            dot_path = home_dir / dot_dir
            if dot_path.exists():
                subdirs.append(str(dot_path))
        
        important_dirs = ['Documents', 'Pictures', 'Desktop', 'Downloads', 'Work', 'Projects', 'Code', 'dev', 'src']
        for dir_name in important_dirs:
            dir_path = home_dir / dir_name
            if dir_path.exists():
                subdirs.append(str(dir_path))
        
        # Build combined command: home root + subdirectories
        if subdirs:
            cmd = ['find', str(home_dir)] + ['-maxdepth', '1', '-type', 'f', '-o'] + subdirs + ['-type', 'f']
        else:
            cmd = home_root_cmd
        
        # Add simplified exclusions
        simple_exclusions = ['*/.cache/*', '*/__pycache__/*', '*/node_modules/*']
        for pattern in simple_exclusions:
            cmd.extend(['-not', '-path', pattern])
        
        # Add include patterns
        include_args = self._build_find_include_args()
        if include_args:
            cmd.extend(include_args)
        
        return cmd
    
    def _scan_home_directory_focused(self, verbose: bool, console) -> List[Path]:
        """Specialized home directory scanning that includes root files and subdirectories."""
        home_dir = Path.home()
        all_files = []
        
        # First: scan home directory root with maxdepth 1 for .gitconfig, *.sh files, etc.
        if verbose and console:
            console.print(f"[dim]Scanning home directory root for config files and scripts...[/dim]")
            
        root_cmd = ['find', str(home_dir), '-maxdepth', '1', '-type', 'f']
        include_args = self._build_find_include_args()
        if include_args:
            root_cmd.extend(include_args)
        
        try:
            result = subprocess.run(root_cmd + ['-print0'], capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                files = result.stdout.rstrip('\0').split('\0')
                root_files = [Path(f) for f in files if f]
                all_files.extend(root_files)
                if verbose and console:
                    console.print(f"[dim]Found {len(root_files)} files in home directory root[/dim]")
        except Exception as e:
            if verbose and console:
                console.print(f"[dim]Error scanning home root: {e}[/dim]")
        
        # Second: scan important subdirectories
        subdirs = []
        for dot_dir in self.config.dot_directory_whitelist:
            dot_path = home_dir / dot_dir
            if dot_path.exists():
                subdirs.append(str(dot_path))
        
        important_dirs = ['Documents', 'Pictures', 'Desktop', 'Downloads', 'Work', 'Projects', 'Code', 'dev', 'src']
        for dir_name in important_dirs:
            dir_path = home_dir / dir_name
            if dir_path.exists():
                subdirs.append(str(dir_path))
        
        if verbose and console:
            console.print(f"[dim]Scanning {len(subdirs)} important subdirectories...[/dim]")
            
        for subdir in subdirs:
            try:
                subdir_cmd = ['find', subdir, '-type', 'f']
                # Add exclusions
                simple_exclusions = ['*/.cache/*', '*/__pycache__/*', '*/node_modules/*']
                for pattern in simple_exclusions:
                    subdir_cmd.extend(['-not', '-path', pattern])
                # Add inclusions
                if include_args:
                    subdir_cmd.extend(include_args)
                
                result = subprocess.run(subdir_cmd + ['-print0'], capture_output=True, text=True, timeout=30)
                if result.returncode == 0 and result.stdout.strip():
                    files = result.stdout.rstrip('\0').split('\0')
                    subdir_files = [Path(f) for f in files if f]
                    all_files.extend(subdir_files)
            except Exception as e:
                if verbose and console:
                    console.print(f"[dim]Error scanning {subdir}: {e}[/dim]")
                continue
        
        return all_files
    
    def _check_file_size(self, file_path: Path) -> bool:
        """Check if file size is within limits."""
        try:
            if file_path.stat().st_size > self.max_file_size_bytes:
                return False
            return True
        except (OSError, FileNotFoundError):
            return False
    
    def _discover_git_repositories_fast(self, base_path: Path) -> List[GitRepository]:
        """High-performance git repository discovery using find."""
        if self.config.enable_parallel_processing:
            return self._discover_git_repositories_parallel(base_path)
        else:
            return self._discover_git_repositories_sequential(base_path)

    def _discover_git_repositories_parallel(self, base_path: Path) -> List[GitRepository]:
        """Discover repositories using parallel directory scanning."""
        repositories = []

        try:
            # Use focused search for home directory
            if base_path == Path.home():
                search_paths = self._get_focused_search_paths()
            else:
                search_paths = [str(base_path)]

            # Split search paths into chunks for parallel processing
            path_chunks = [search_paths[i:i+3] for i in range(0, len(search_paths), 3)]

            with ThreadPoolExecutor(max_workers=min(self.config.max_workers, len(path_chunks))) as executor:
                futures = [
                    executor.submit(self._find_repos_in_paths, chunk)
                    for chunk in path_chunks
                ]

                for future in as_completed(futures):
                    try:
                        repos = future.result()
                        repositories.extend(repos)
                    except Exception as e:
                        if self.verbose and self.console:
                            self.console.print(f"[red]Error in parallel git discovery: {e}[/red]")

        except Exception as e:
            if self.verbose and self.console:
                self.console.print(f"[red]Parallel git discovery failed: {e}[/red]")
            # Fallback to sequential
            return self._discover_git_repositories_sequential(base_path)

        return repositories

    def _discover_git_repositories_sequential(self, base_path: Path) -> List[GitRepository]:
        """Original sequential git repository discovery using find."""
        repositories = []

        try:
            # Use focused search for home directory
            if base_path == Path.home():
                search_paths = self._get_focused_search_paths()
            else:
                search_paths = [str(base_path)]

            # Use find to quickly locate all .git directories in focused paths
            cmd = ['find'] + search_paths + ['-type', 'd', '-name', '.git']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0 and result.stdout.strip():
                git_dirs = [Path(line.strip()) for line in result.stdout.split('\n') if line.strip()]

                for git_dir in git_dirs:
                    repo_path = git_dir.parent
                    try:
                        repo = git.Repo(repo_path)
                        git_repo = GitRepository(repo_path, repo)
                        repositories.append(git_repo)
                    except (git.exc.InvalidGitRepositoryError, git.exc.GitCommandError):
                        # Skip invalid git repositories
                        continue

        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            # If focused search fails, return empty list rather than falling back
            pass

        return repositories

    def _find_repos_in_paths(self, search_paths: List[str]) -> List[GitRepository]:
        """Find git repositories in a list of search paths."""
        repositories = []

        try:
            # Use find to quickly locate all .git directories in focused paths
            cmd = ['find'] + search_paths + ['-type', 'd', '-name', '.git']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0 and result.stdout.strip():
                git_dirs = [Path(line.strip()) for line in result.stdout.split('\n') if line.strip()]

                for git_dir in git_dirs:
                    repo_path = git_dir.parent
                    try:
                        repo = git.Repo(repo_path)
                        git_repo = GitRepository(repo_path, repo)
                        repositories.append(git_repo)
                    except (git.exc.InvalidGitRepositoryError, git.exc.GitCommandError):
                        # Skip invalid git repositories
                        continue

        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

        return repositories

    def _get_repository_files_parallel(self, repos: List[GitRepository], verbose: bool, console) -> List[Path]:
        """Process repositories in parallel using git's native filtering."""
        if not repos:
            return []

        with ThreadPoolExecutor(max_workers=min(self.config.max_workers, len(repos))) as executor:
            futures = {
                executor.submit(self._process_single_repository, repo): repo
                for repo in repos
            }

            all_files = []
            for future in as_completed(futures):
                try:
                    repo_files = future.result()
                    all_files.extend(repo_files)
                except Exception as e:
                    repo = futures[future]
                    if verbose and console:
                        console.print(f"[red]Error processing repo {repo.path}: {e}[/red]")

        # Apply size filtering and always_exclude filtering to git files
        return self._filter_git_files(all_files, verbose, console)

    def _get_repository_files_sequential(self, repos: List[GitRepository], verbose: bool, console) -> List[Path]:
        """Process repositories sequentially (original implementation)."""
        git_files = []
        for repo in repos:
            if self.config.git.respect_gitignore:
                # When respecting gitignore, only add override pattern files and .git directory
                if verbose and console:
                    console.print(f"[dim]Adding git repository with gitignore respect: {repo.path}[/dim]")

                # Always include .git directory if configured
                if self.config.git.include_git_dir:
                    git_dir = repo.path / '.git'
                    if git_dir.exists():
                        for file_path in git_dir.rglob('*'):
                            if file_path.is_file():
                                git_files.append(file_path)

                # Add override pattern files (like .env)
                if self.config.git.gitignore_override_patterns:
                    override_files = repo.get_override_files(self.config.git.gitignore_override_patterns)
                    git_files.extend(override_files)
            else:
                # When NOT respecting gitignore, add ALL repository files
                if verbose and console:
                    console.print(f"[dim]Adding complete git repository: {repo.path}[/dim]")

                # Get all repository files including .git directory
                repo_files = repo.get_all_repo_files(include_git_dir=self.config.git.include_git_dir)
                git_files.extend(repo_files)

        return self._filter_git_files(git_files, verbose, console)

    def _process_single_repository(self, repo: GitRepository) -> List[Path]:
        """Process a single repository using git's bulk operations."""
        repo_root = Path(repo.repo.working_dir)
        filtered_files = []

        if self.config.git.respect_gitignore:
            # Use git ls-files for tracked files (respects gitignore)
            try:
                tracked_output = repo.repo.git.ls_files()
                if tracked_output:
                    tracked = tracked_output.split('\n')
                    filtered_files.extend([repo_root / f for f in tracked if f])
            except git.GitCommandError:
                pass

            # Add override pattern files in parallel
            if self.config.git.gitignore_override_patterns:
                override_files = repo.get_override_files(self.config.git.gitignore_override_patterns)
                filtered_files.extend(override_files)

            # Include .git directory if configured
            if self.config.git.include_git_dir:
                git_dir_files = list((repo_root / '.git').rglob('*'))
                filtered_files.extend([f for f in git_dir_files if f.is_file()])
        else:
            # Get ALL repository files
            filtered_files = repo.get_all_repo_files(include_git_dir=self.config.git.include_git_dir)

        return filtered_files

    def _filter_git_files(self, git_files: List[Path], verbose: bool, console) -> List[Path]:
        """Apply size and exclusion filtering to git files."""
        git_files_filtered = []
        for file_path in git_files:
            # Check file size
            if not self._check_file_size(file_path):
                if verbose and console:
                    console.print(f"[dim]Excluded git file: {file_path} (size exceeds limit)[/dim]")
                continue

            # Always respect always_exclude patterns even for git files
            if self._matches_patterns(file_path, self.config.always_exclude):
                if verbose and console:
                    console.print(f"[dim]Excluded git file: {file_path} (always exclude pattern)[/dim]")
                continue

            git_files_filtered.append(file_path)

        return git_files_filtered

    def _get_non_repository_files_parallel(self, base_path: Path, repos: List[GitRepository], verbose: bool, console) -> List[Path]:
        """Get non-repository files using parallel find operations."""
        repo_paths = {str(repo.path) for repo in repos}

        if base_path == Path.home():
            # Split home directory into chunks for parallel processing
            search_chunks = self._get_home_directory_chunks(repo_paths)
        else:
            # Split directory tree into chunks
            search_chunks = self._get_directory_chunks(base_path, repo_paths)

        if verbose and console:
            console.print(f"[dim]Processing {len(search_chunks)} directory chunks in parallel...[/dim]")

        with ThreadPoolExecutor(max_workers=min(self.config.max_workers, len(search_chunks))) as executor:
            futures = [
                executor.submit(self._find_files_in_chunk, chunk, repo_paths)
                for chunk in search_chunks
            ]

            all_files = []
            for future in as_completed(futures):
                try:
                    chunk_files = future.result()
                    all_files.extend(chunk_files)
                except Exception as e:
                    if verbose and console:
                        console.print(f"[red]Error in parallel find: {e}[/red]")

        return all_files

    def _get_non_repository_files_sequential(self, base_path: Path, repos: List[GitRepository], verbose: bool, console) -> List[Path]:
        """Get non-repository files using sequential processing (original implementation)."""
        # Use specialized home directory scanning if needed
        if base_path == Path.home():
            file_paths = self._scan_home_directory_focused(verbose, console)
        else:
            # Build find command for high-performance file discovery
            find_cmd = self._build_find_command(base_path)

            if verbose and console:
                console.print(f"[dim]Executing find command...[/dim]")

            try:
                # Execute find command with null-terminated output for handling special characters
                if verbose and console:
                    console.print(f"[dim]Running: {' '.join(find_cmd[:10])}... ({len(find_cmd)} args)[/dim]")

                result = subprocess.run(
                    find_cmd + ['-print0'],
                    cwd=str(base_path),
                    capture_output=True,
                    text=True,
                    timeout=60  # Reduced to 1 minute timeout
                )

                if result.returncode != 0:
                    if verbose and console:
                        console.print(f"[red]Find command failed: {result.stderr}[/red]")
                    # Fallback to basic file discovery
                    return self._fallback_file_discovery(base_path, verbose, console)

                # Parse null-terminated output
                file_paths = []
                if result.stdout.strip():
                    files = result.stdout.rstrip('\0').split('\0')
                    file_paths = [Path(f) for f in files if f]
            except subprocess.TimeoutExpired:
                if verbose and console:
                    console.print(f"[red]Find command timed out, falling back to basic discovery[/red]")
                return self._fallback_file_discovery(base_path, verbose, console)
            except Exception as e:
                if verbose and console:
                    console.print(f"[red]Find command error: {e}, falling back to basic discovery[/red]")
                return self._fallback_file_discovery(base_path, verbose, console)

        return file_paths

    def _get_home_directory_chunks(self, repo_exclusions: Set[str]) -> List[Path]:
        """Split home directory into chunks for parallel processing."""
        home_dir = Path.home()
        chunks = []

        # Add home directory root as first chunk (for .gitconfig, *.sh files, etc.)
        chunks.append(home_dir)

        # Add whitelisted dot directories as chunks
        for dot_dir in self.config.dot_directory_whitelist:
            dot_path = home_dir / dot_dir
            if dot_path.exists() and str(dot_path) not in repo_exclusions:
                chunks.append(dot_path)

        # Add important directories as chunks
        important_dirs = ['Documents', 'Pictures', 'Desktop', 'Downloads', 'Work', 'Projects', 'Code', 'dev', 'src']
        for dir_name in important_dirs:
            dir_path = home_dir / dir_name
            if dir_path.exists() and str(dir_path) not in repo_exclusions:
                chunks.append(dir_path)

        return chunks

    def _get_directory_chunks(self, base_path: Path, repo_exclusions: Set[str]) -> List[Path]:
        """Split a directory tree into chunks for parallel processing."""
        chunks = []

        try:
            # Get top-level directories that aren't repositories
            for item in base_path.iterdir():
                if item.is_dir() and str(item) not in repo_exclusions:
                    chunks.append(item)

            # If no subdirectories, process the base path itself
            if not chunks:
                chunks.append(base_path)

        except (OSError, PermissionError):
            # If we can't read the directory, just process it as a single chunk
            chunks.append(base_path)

        return chunks

    def _find_files_in_chunk(self, search_path: Path, repo_exclusions: Set[str]) -> List[Path]:
        """Find files in a specific directory chunk."""
        if search_path == Path.home():
            # Special handling for home directory root - use maxdepth 1
            find_cmd = ['find', str(search_path), '-maxdepth', '1', '-type', 'f']
        else:
            find_cmd = ['find', str(search_path), '-type', 'f']

        # Exclude repository directories
        for repo_path in repo_exclusions:
            find_cmd.extend(['-not', '-path', f'{repo_path}/*'])

        # Add standard exclusions and inclusions
        find_cmd.extend(self._build_find_exclude_args())
        include_args = self._build_find_include_args()
        if include_args:
            find_cmd.extend(include_args)

        try:
            result = subprocess.run(find_cmd + ['-print0'], capture_output=True, text=True, timeout=60)
            if result.returncode == 0 and result.stdout.strip():
                files = [Path(f) for f in result.stdout.rstrip('\0').split('\0') if f]
                return [f for f in files if self._should_include_non_repo_file(f)]
        except Exception:
            pass

        return []

    def _should_include_non_repo_file(self, file_path: Path) -> bool:
        """Check if a non-repository file should be included."""
        # Check file size
        if not self._check_file_size(file_path):
            return False

        # Check always exclude patterns
        if self._matches_patterns(file_path, self.config.always_exclude):
            return False

        # Check exclude patterns
        if self._matches_patterns(file_path, self.config.exclude_patterns):
            return False

        # If no include patterns are specified, include by default
        if not self.config.include_patterns:
            return True

        # Check include patterns
        return self._matches_patterns(file_path, self.config.include_patterns)

    def _get_focused_search_paths(self) -> List[str]:
        """Get focused search paths for home directory scanning."""
        home_dir = Path.home()
        search_paths = []
        
        # IMPORTANT: Add home directory root first to catch .gitconfig, *.sh files, etc.
        search_paths.append(str(home_dir))
        
        # Add whitelisted dot directories  
        for dot_dir in self.config.dot_directory_whitelist:
            dot_path = home_dir / dot_dir
            if dot_path.exists():
                search_paths.append(str(dot_path))
        
        # Add important directories
        important_dirs = ['Documents', 'Pictures', 'Desktop', 'Downloads', 'Work', 'Projects', 'Code', 'dev', 'src']
        for dir_name in important_dirs:
            dir_path = home_dir / dir_name
            if dir_path.exists():
                search_paths.append(str(dir_path))
        
        return search_paths
    
    def _fallback_file_discovery(self, base_path: Path, verbose: bool, console) -> List[Path]:
        """Fallback to basic file discovery if find fails."""
        if verbose and console:
            console.print(f"[yellow]Using fallback file discovery method...[/yellow]")
        
        # Very basic implementation - include common file types
        included_files = []
        try:
            for ext in ['.py', '.js', '.ts', '.md', '.txt', '.json', '.yaml', '.yml', '.png', '.jpg', '.pdf']:
                cmd = ['find', str(base_path), '-name', f'*{ext}', '-type', 'f']
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode == 0 and result.stdout.strip():
                    files = [Path(line.strip()) for line in result.stdout.split('\n') if line.strip()]
                    included_files.extend(files)
        except Exception:
            # Last resort - return empty list
            pass
        
        return list(set(included_files))  # Remove duplicates

    def _matches_patterns(self, path: Path, patterns: List[str]) -> bool:
        """Pattern matching using glob-style patterns with ** support."""
        import fnmatch
        path_str = str(path)
        
        # Try to convert path to relative path for matching (remove drive/mount prefix)
        path_parts = path.parts
        relative_path_variations = []
        
        # Add full path
        relative_path_variations.append(path_str)
        
        # Add path without leading slash/drive
        if len(path_parts) > 1:
            relative_path_variations.append('/'.join(path_parts[1:]))
        
        # Add just the filename  
        relative_path_variations.append(path.name)
        
        for pattern in patterns:
            # Handle ** patterns
            if '**' in pattern:
                for relative_path in relative_path_variations:
                    # Use Python's pathlib-compatible glob matching
                    # Check for combined pattern first: **/something/**
                    if pattern.startswith('**/') and pattern.endswith('/**'):
                        # Pattern like **/node_modules/** - extract the middle part
                        middle = pattern[3:-3]  # Remove **/ and /**
                        if (f'/{middle}/' in relative_path or 
                            relative_path.startswith(f'{middle}/') or
                            relative_path.endswith(f'/{middle}') or
                            relative_path == middle):
                            return True
                    elif pattern.startswith('**/'):
                        # Pattern like **/debug.txt or **/node_modules/important.js
                        suffix = pattern[3:]  # Remove **/
                        if (relative_path.endswith(suffix) or 
                            fnmatch.fnmatch(relative_path, suffix) or
                            ('/' + suffix) in relative_path):
                            return True
                    elif pattern.endswith('/**'):
                        # Pattern like node_modules/** - starts with specific directory
                        prefix = pattern[:-3]  # Remove /**
                        if (relative_path.startswith(prefix + '/') or 
                            ('/' + prefix + '/') in relative_path or
                            relative_path == prefix):
                            return True
                    else:
                        # Pattern like node_modules/**/file.txt
                        if fnmatch.fnmatch(relative_path, pattern.replace('**/', '*/')):
                            return True
            else:
                # Simple glob matching
                for relative_path in relative_path_variations:
                    if fnmatch.fnmatch(relative_path, pattern):
                        return True
        return False

    def get_filter_stats(self) -> dict:
        """Get statistics about the filtering process."""
        git_stats = self.git_detector.get_repository_stats()

        return {
            "git_repositories": git_stats["total_repositories"],
            "max_file_size_bytes": self.max_file_size_bytes,
            "include_patterns_count": len(self.config.include_patterns),
            "exclude_patterns_count": len(self.config.exclude_patterns),
            "always_exclude_patterns_count": len(self.config.always_exclude),
        }
