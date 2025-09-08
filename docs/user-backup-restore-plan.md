# User Backup & Restore Development Plan

## Overview
Develop a comprehensive user directory backup and restore system with git-aware functionality, flexible configuration management, and intuitive CLI interface.

## Phase 1: Technical Foundation

### Compression Format Choice
- **Primary: ZSTD** (fastest with excellent compression ratio)
- **Alternative: LZ4** (fastest compression, lower ratio) 
- **Fallback: gzip** (universal compatibility)

### Required Libraries
- `python-zstandard` - ZSTD compression support
- `GitPython` - Git repository detection and operations
- `click-completion` or `argcomplete` - Tab completion support
- `appdirs` or `platformdirs` - Cross-platform config directory support

## Phase 2: Configuration Management System

### Configuration Hierarchy
```
1. Default configuration (embedded in application)
2. User configuration (~/.config/sysforge/user-backup.yaml)
3. Override configuration (--config flag or per-project)
4. Command-line arguments (highest priority)
```

### XDG Base Directory Structure
```
~/.config/sysforge/
├── user-backup.yaml      # User overrides
├── profiles/             # Named backup profiles
│   ├── work.yaml
│   └── personal.yaml
└── backups/              # Default backup location
    ├── work-2024-01-15.tar.zst
    └── personal-2024-01-14.tar.zst
```

### Default Configuration (Embedded)
```yaml
# Default configuration - embedded in application
compression:
  format: "zstd"
  level: 3
  
target:
  base_path: "~"
  output_path: "~/.config/sysforge/backups/backup-{timestamp}.tar.zst"
  
git:
  include_repos: true
  respect_gitignore: false
  include_git_dir: true
  
include_patterns:
  - "**/*.py"
  - "**/*.js"
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.jsx"
  - "**/*.java"
  - "**/*.cpp"
  - "**/*.c"
  - "**/*.h"
  - "**/*.rs"
  - "**/*.go"
  - "**/*.md"
  - "**/*.rst"
  - "**/*.txt"
  - "**/*.yaml"
  - "**/*.yml"
  - "**/*.json"
  - "**/*.toml"
  - "**/*.ini"
  - "**/*.cfg"
  - "**/src/**"
  - "**/docs/**"
  - "**/doc/**"
  - "**/tests/**"
  - "**/test/**"
  - "**/*.sql"
  - "**/*.sh"
  - "**/*.bash"
  - "**/*.zsh"
  - "**/Dockerfile*"
  - "**/docker-compose*"
  - "**/Makefile*"
  - "**/.env*"

exclude_patterns:
  # Build artifacts and caches (applied outside git repos only)
  - "**/node_modules/**"
  - "**/__pycache__/**"
  - "**/*.pyc"
  - "**/*.pyo"
  - "**/.venv/**"
  - "**/venv/**"
  - "**/target/**"           # Rust builds
  - "**/build/**"            # General builds
  - "**/dist/**"             # Distribution files
  - "**/.pytest_cache/**"
  - "**/.mypy_cache/**"
  - "**/.ruff_cache/**"
  - "**/*.egg-info/**"
  - "**/coverage.xml"
  - "**/.coverage"
  - "**/.tox/**"
  - "**/htmlcov/**"
  
  # IDE and editor files
  - "**/.vscode/**"
  - "**/.idea/**"
  - "**/*.swp"
  - "**/*.swo"
  - "**/*~"
  
  # OS files
  - "**/.DS_Store"
  - "**/Thumbs.db"
  
  # Temporary files
  - "**/*.tmp"
  - "**/*.temp"
  - "**/tmp/**"

always_exclude:
  # These are excluded even in git repositories
  - "**/.DS_Store"
  - "**/Thumbs.db"
  - "**/*.tmp"
  - "**/*.temp"
  - "**/*.log"
  - "**/core"
  - "**/core.*"

max_file_size: "100MB"

restore:
  conflict_resolution: "prompt"
  preserve_permissions: true
  create_backup_on_conflict: true
  backup_suffix: ".backup-{timestamp}"
```

### User Configuration Override Example
```yaml
# ~/.config/sysforge/user-backup.yaml
target:
  base_path: "~/Work"
  output_path: "~/Backups/work-{timestamp}.tar.zst"

compression:
  level: 6  # Higher compression

include_patterns:
  # Add custom patterns
  - "**/*.vue"
  - "**/*.scss"

exclude_patterns:
  # Add custom exclusions
  - "**/large-datasets/**"
  - "**/*.iso"
```

## Phase 3: CLI Interface Design

### Main Commands
```bash
# Backup command
sysforge user-backup [OPTIONS] [TARGET_PATH]

Options:
  --config, -c PATH       Custom configuration file
  --profile, -p NAME      Use named profile from ~/.config/sysforge/profiles/
  --output, -o PATH       Override output path  
  --format TEXT           Override compression format (zstd|lz4|gzip)
  --level INTEGER         Override compression level
  --dry-run              Show what would be backed up
  --print-config         Print effective configuration and exit
  --verbose, -v          Verbose output
  --quiet, -q            Minimal output
  --exclude-git          Don't include git repositories
  --include PATTERN      Add include pattern
  --exclude PATTERN      Add exclude pattern

# Restore command  
sysforge restore [OPTIONS] [BACKUP_FILE]

Options:
  --target, -t PATH       Target directory (default: original location)
  --config, -c PATH       Custom configuration file
  --conflict TEXT         Conflict resolution: prompt|overwrite|skip|backup
  --dry-run              Show what would be restored
  --print-config         Print effective configuration and exit
  --verbose, -v          Verbose output
  --quiet, -q            Minimal output
  --partial PATTERN      Restore only files matching pattern

# Configuration management
sysforge config [SUBCOMMAND]

Subcommands:
  init                   Create user configuration directory
  show                   Show effective configuration
  edit                   Open user config in $EDITOR
  validate               Validate configuration files
  reset                  Reset to default configuration
```

### Tab Completion Features
- **Backup files**: Complete backup file paths from default backup directory
- **Configuration profiles**: Complete profile names from ~/.config/sysforge/profiles/
- **Path completion**: Complete file and directory paths
- **Pattern completion**: Suggest common glob patterns
- **Format completion**: Complete compression format options
- **Conflict resolution**: Complete conflict resolution strategies

## Phase 4: Git-Aware Logic

### Git Repository Detection Algorithm
1. **Scan for .git directories** - Walk directory tree identifying git repositories
2. **Handle nested repositories** - Support git repositories within other git repositories
3. **Respect git boundaries** - Each git repository is treated as a unit
4. **Include all git content** - Ignore standard exclude patterns within git repositories

### File Processing Priority
```
For each file/directory:
1. Check if path matches always_exclude patterns → Skip
2. Check if path is inside git repository:
   a. If yes → Include (subject only to always_exclude and max_file_size)
   b. If no → Apply standard include/exclude pattern matching
3. Check file size against max_file_size → Skip if too large
4. Include in backup
```

### Git Repository Handling
- **Include .git directory** - Preserve complete git history and metadata  
- **Ignore .gitignore rules** - Backup all tracked and untracked files
- **Handle git submodules** - Detect and include submodule contents
- **Preserve git attributes** - Maintain git-specific file attributes

## Phase 5: Restore Functionality

### Restore Features
- **Archive inspection** - List contents without extracting
- **Selective restore** - Restore specific files/directories using patterns
- **Conflict detection** - Check for existing files at target location
- **Multiple resolution strategies**:
  - `prompt`: Interactive user choice for each conflict
  - `overwrite`: Replace existing files without prompting
  - `skip`: Keep existing files, skip conflicting ones
  - `backup`: Move existing files to .backup-{timestamp} before restoring
- **Metadata preservation** - Restore file permissions, timestamps, ownership
- **Progress reporting** - Real-time extraction progress
- **Verification** - Verify restored files against archive checksums

### Conflict Resolution Interface
```
Conflict detected: /home/user/project/src/main.py
  Existing: 2024-01-15 14:30:00 (1.2KB)
  Archive:  2024-01-14 16:45:00 (1.1KB)
  
Choose action:
  [o] Overwrite - Replace existing file
  [s] Skip - Keep existing file  
  [b] Backup - Move existing to .backup and restore
  [d] Diff - Show differences between files
  [a] All - Apply choice to all remaining conflicts
  [q] Quit - Stop restoration
  
Choice [o/s/b/d/a/q]:
```

## Phase 6: Testing Strategy

### Unit Tests Structure
```
tests/
├── unit/
│   ├── config/
│   │   ├── test_config_loading.py        # Test hierarchy loading
│   │   ├── test_config_validation.py     # Test YAML validation
│   │   └── test_config_merging.py        # Test config merging logic
│   ├── git/
│   │   ├── test_git_detection.py         # Test git repo detection
│   │   ├── test_git_filtering.py         # Test git-aware filtering
│   │   └── test_nested_git.py            # Test nested repositories
│   ├── filtering/
│   │   ├── test_pattern_matching.py      # Test glob patterns
│   │   ├── test_file_filtering.py        # Test include/exclude logic
│   │   └── test_size_filtering.py        # Test file size limits
│   ├── compression/
│   │   ├── test_compression_formats.py   # Test different formats
│   │   ├── test_compression_levels.py    # Test compression levels
│   │   └── test_archive_creation.py      # Test archive creation
│   ├── restore/
│   │   ├── test_conflict_detection.py    # Test conflict detection
│   │   ├── test_conflict_resolution.py   # Test resolution strategies
│   │   └── test_metadata_restore.py      # Test permission restoration
│   └── cli/
│       ├── test_argument_parsing.py      # Test CLI argument parsing
│       ├── test_config_printing.py       # Test --print-config
│       └── test_tab_completion.py        # Test completion functionality
```

### Integration Tests
```
tests/
├── integration/
│   ├── fixtures/
│   │   ├── sample_workspace/
│   │   │   ├── git_project/              # Git repository
│   │   │   │   ├── .git/                 # Git metadata
│   │   │   │   ├── src/                  # Source code
│   │   │   │   ├── node_modules/         # Should be included (git repo)
│   │   │   │   ├── __pycache__/          # Should be included (git repo)
│   │   │   │   ├── .gitignore           
│   │   │   │   └── large_file.dat        # Test size limits
│   │   │   ├── non_git_project/          # Regular directory
│   │   │   │   ├── src/                  # Should be included
│   │   │   │   ├── node_modules/         # Should be excluded
│   │   │   │   ├── __pycache__/          # Should be excluded
│   │   │   │   └── build/                # Should be excluded
│   │   │   ├── nested_workspace/
│   │   │   │   ├── outer_git/            # Git repository
│   │   │   │   │   ├── .git/
│   │   │   │   │   └── inner_project/    # All included
│   │   │   │   └── inner_git/            # Nested git repository
│   │   │   │       ├── .git/
│   │   │   │       └── src/
│   │   │   └── .DS_Store                 # Always excluded
│   │   ├── configs/
│   │   │   ├── minimal.yaml              # Minimal valid config
│   │   │   ├── comprehensive.yaml        # Full feature config
│   │   │   ├── invalid.yaml              # Invalid config for testing
│   │   │   └── profiles/
│   │   │       ├── development.yaml      # Development profile
│   │   │       └── production.yaml       # Production profile
│   │   └── backups/                      # Sample backup files
│   │       ├── test-backup.tar.zst
│   │       └── partial-backup.tar.zst
│   ├── test_end_to_end_backup.py         # Full backup workflow
│   ├── test_end_to_end_restore.py        # Full restore workflow
│   ├── test_config_hierarchy.py          # Config loading integration
│   ├── test_git_workflows.py             # Git-specific scenarios  
│   ├── test_cli_integration.py           # CLI command integration
│   ├── test_performance.py               # Performance benchmarks
│   └── test_cross_platform.py            # Cross-platform compatibility
```

### Test Categories
1. **Configuration Tests**
   - Default config loading
   - User config override merging
   - Command-line argument precedence
   - Profile system functionality
   - Config validation and error handling

2. **Git Integration Tests**
   - Git repository detection accuracy
   - Nested repository handling
   - Git-aware file inclusion
   - Submodule handling
   - .git directory preservation

3. **File Filtering Tests**
   - Include pattern matching
   - Exclude pattern matching
   - Git vs non-git filtering differences
   - Always-exclude pattern enforcement
   - File size limit enforcement

4. **Backup Workflow Tests**
   - End-to-end backup creation
   - Archive integrity verification
   - Progress reporting accuracy
   - Error handling and recovery
   - Different compression formats

5. **Restore Workflow Tests**
   - End-to-end restore process
   - Conflict detection accuracy
   - All conflict resolution strategies
   - Metadata preservation
   - Partial restore functionality

6. **CLI Interface Tests**
   - Argument parsing correctness
   - Tab completion functionality
   - Configuration printing
   - Error message clarity
   - Help system completeness

## Phase 7: Implementation Phases

### Phase 7.1: Core Infrastructure (Week 1)
1. **Configuration system** - Default config, user config loading, hierarchy
2. **XDG directory management** - Config directory creation and management
3. **Basic CLI structure** - Command parsing, help system
4. **Configuration printing** - `--print-config` functionality

### Phase 7.2: Git-Aware Backup (Week 1-2)
1. **Git repository detection** - Find and categorize git repositories
2. **File filtering logic** - Implement git-aware vs standard filtering
3. **Core compression** - Archive creation with chosen format
4. **Progress reporting** - Real-time backup progress

### Phase 7.3: Restore Functionality (Week 2)  
1. **Archive inspection** - Read and list archive contents
2. **Conflict detection** - Compare archive vs existing files
3. **Conflict resolution** - Implement all resolution strategies
4. **Metadata restoration** - Preserve permissions and timestamps

### Phase 7.4: Advanced CLI Features (Week 2-3)
1. **Tab completion** - Complete file paths, profiles, options
2. **Profile system** - Named backup profiles
3. **Selective operations** - Pattern-based backup/restore
4. **Dry-run functionality** - Preview operations without executing

### Phase 7.5: Testing & Polish (Week 3)
1. **Comprehensive test suite** - Unit and integration tests
2. **Performance optimization** - Profile and optimize hot paths  
3. **Error handling** - Graceful failure and user feedback
4. **Documentation** - User guide and API documentation

### Phase 7.6: Advanced Features (Future)
1. **Incremental backups** - Only backup changed files
2. **Archive encryption** - Password-protected backups
3. **Remote storage integration** - Cloud storage backends
4. **Scheduled backups** - Cron-like automation
5. **Backup verification** - Integrity checking and validation

## Success Criteria

### Functional Requirements
- ✅ Create compressed backups with configurable compression
- ✅ Include entire git repositories while filtering non-git directories
- ✅ Restore backups with conflict resolution
- ✅ Hierarchical configuration management
- ✅ Tab completion for common operations
- ✅ Progress reporting for long operations

### Technical Requirements
- ✅ Support ZSTD, LZ4, and gzip compression formats
- ✅ Handle large directories (>10GB) efficiently
- ✅ Cross-platform compatibility (Linux, macOS, Windows)
- ✅ Comprehensive error handling and recovery
- ✅ Extensible architecture for future enhancements

### User Experience Requirements  
- ✅ Intuitive CLI interface with helpful defaults
- ✅ Clear progress indication and logging
- ✅ Comprehensive help and documentation
- ✅ Flexible configuration without overwhelming complexity
- ✅ Fast operation with minimal user intervention

## Timeline Estimate
**Total Development Time**: 3 weeks
- Week 1: Core infrastructure and backup functionality  
- Week 2: Restore functionality and advanced CLI features
- Week 3: Testing, optimization, and documentation

## Risk Mitigation
- **Large file handling**: Implement streaming compression to avoid memory issues
- **Permission issues**: Graceful degradation when permissions prevent access
- **Cross-platform compatibility**: Use cross-platform libraries and extensive testing
- **Git complexity**: Thorough testing with various git repository configurations
- **Configuration complexity**: Provide sane defaults and clear documentation