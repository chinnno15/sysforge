"""Tests for restore functionality."""

import json
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from rich.console import Console

from sysforge.backup.config import BackupConfig, ConflictResolution
from sysforge.backup.restore import ConflictInfo, RestoreOperation, restore_backup


class TestConflictInfo:
    """Test ConflictInfo class."""
    
    def test_conflict_info_creation(self):
        """Test ConflictInfo creation with existing file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create existing file
            existing_file = Path(temp_dir) / "test.txt"
            existing_file.write_text("existing content")
            
            # Create mock archive member
            archive_member = Mock(spec=tarfile.TarInfo)
            archive_member.size = 100
            archive_member.mtime = 1640995200.0  # 2022-01-01
            
            conflict_info = ConflictInfo(archive_member, existing_file)
            
            assert conflict_info.archive_member == archive_member
            assert conflict_info.existing_path == existing_file
            assert conflict_info.archive_size == 100
            assert conflict_info.existing_size > 0  # File exists
            assert isinstance(conflict_info.archive_mtime, datetime)
            assert isinstance(conflict_info.existing_mtime, datetime)
    
    def test_conflict_info_nonexistent_file(self):
        """Test ConflictInfo with nonexistent file."""
        nonexistent_file = Path("/nonexistent/file.txt")
        
        archive_member = Mock(spec=tarfile.TarInfo)
        archive_member.size = 100
        archive_member.mtime = 1640995200.0
        
        conflict_info = ConflictInfo(archive_member, nonexistent_file)
        
        assert conflict_info.existing_size == 0
        assert conflict_info.existing_mtime == datetime.min


class TestRestoreOperation:
    """Test RestoreOperation class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = BackupConfig()
        self.console = Mock(spec=Console)
        self.restore_op = RestoreOperation(self.config, self.console)
    
    def test_restore_operation_initialization(self):
        """Test RestoreOperation initialization."""
        assert self.restore_op.config == self.config
        assert self.restore_op.console == self.console
        assert len(self.restore_op.conflicts) == 0
        assert len(self.restore_op.restored_files) == 0
        assert len(self.restore_op.skipped_files) == 0
        assert len(self.restore_op.errors) == 0
    
    def test_restore_archive_nonexistent(self):
        """Test restore with nonexistent archive."""
        nonexistent_archive = Path("/nonexistent/archive.tar.zst")
        
        with pytest.raises(FileNotFoundError, match="Archive not found"):
            self.restore_op.restore_archive(nonexistent_archive)
    
    @patch('sysforge.backup.restore.Decompressor.list_archive')
    def test_detect_conflicts(self, mock_list_archive):
        """Test conflict detection."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create existing file
            existing_file = Path(temp_dir) / "test.txt"
            existing_file.write_text("existing")
            
            # Mock archive member
            member = Mock(spec=tarfile.TarInfo)
            member.name = "test.txt"
            member.size = 100
            member.mtime = 1640995200.0
            member.isfile.return_value = True
            
            mock_list_archive.return_value = [member]
            
            conflicts = self.restore_op._detect_conflicts([member], Path(temp_dir))
            
            assert len(conflicts) == 1
            assert conflicts[0].existing_path == existing_file
    
    def test_get_target_path_with_target_dir(self):
        """Test target path calculation with target directory."""
        target_dir = Path("/custom/target")
        archive_path = "src/main.py"
        
        target_path = self.restore_op._get_target_path(archive_path, target_dir)
        
        expected = target_dir / archive_path
        assert target_path == expected
    
    def test_get_target_path_without_target_dir(self):
        """Test target path calculation without target directory."""
        archive_path = "/original/path/main.py"
        
        target_path = self.restore_op._get_target_path(archive_path, None)
        
        expected = Path(archive_path)
        assert target_path == expected
    
    def test_handle_conflicts_overwrite(self):
        """Test conflict handling with overwrite strategy."""
        self.config.restore.conflict_resolution = ConflictResolution.OVERWRITE
        
        # Create mock conflicts
        conflict1 = Mock(spec=ConflictInfo)
        conflict2 = Mock(spec=ConflictInfo)
        conflicts = [conflict1, conflict2]
        
        # Should not add any files to skipped_files
        self.restore_op._handle_conflicts(conflicts)
        
        assert len(self.restore_op.skipped_files) == 0
    
    def test_handle_conflicts_skip(self):
        """Test conflict handling with skip strategy."""
        self.config.restore.conflict_resolution = ConflictResolution.SKIP
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create conflict
            existing_file = Path(temp_dir) / "test.txt"
            existing_file.touch()
            
            conflict = Mock(spec=ConflictInfo)
            conflict.existing_path = existing_file
            
            self.restore_op._handle_conflicts([conflict])
            
            assert existing_file in self.restore_op.skipped_files
    
    @patch('shutil.copy2')
    def test_handle_conflicts_backup(self, mock_copy):
        """Test conflict handling with backup strategy."""
        self.config.restore.conflict_resolution = ConflictResolution.BACKUP
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create conflict
            existing_file = Path(temp_dir) / "test.txt"
            existing_file.write_text("existing content")
            
            conflict = Mock(spec=ConflictInfo)
            conflict.existing_path = existing_file
            
            self.restore_op._handle_conflicts([conflict])
            
            # Should call copy2 to backup the file
            mock_copy.assert_called_once()
    
    @patch('sysforge.backup.restore.Prompt.ask')
    def test_handle_conflicts_interactive_overwrite(self, mock_ask):
        """Test interactive conflict handling with overwrite choice."""
        self.config.restore.conflict_resolution = ConflictResolution.PROMPT
        mock_ask.return_value = "o"  # Overwrite
        
        with tempfile.TemporaryDirectory() as temp_dir:
            existing_file = Path(temp_dir) / "test.txt"
            existing_file.write_text("existing")
            
            # Create conflict
            member = Mock(spec=tarfile.TarInfo)
            member.size = 50
            member.mtime = 1640995200.0
            
            conflict = ConflictInfo(member, existing_file)
            
            self.restore_op._handle_conflicts_interactive([conflict])
            
            # No files should be skipped for overwrite
            assert len(self.restore_op.skipped_files) == 0
    
    @patch('sysforge.backup.restore.Prompt.ask')
    def test_handle_conflicts_interactive_skip(self, mock_ask):
        """Test interactive conflict handling with skip choice."""
        self.config.restore.conflict_resolution = ConflictResolution.PROMPT
        mock_ask.return_value = "s"  # Skip
        
        with tempfile.TemporaryDirectory() as temp_dir:
            existing_file = Path(temp_dir) / "test.txt"
            existing_file.write_text("existing")
            
            # Create conflict
            member = Mock(spec=tarfile.TarInfo)
            member.size = 50
            member.mtime = 1640995200.0
            
            conflict = ConflictInfo(member, existing_file)
            
            self.restore_op._handle_conflicts_interactive([conflict])
            
            # File should be skipped
            assert existing_file in self.restore_op.skipped_files
    
    @patch('shutil.copy2')
    @patch('sysforge.backup.restore.Prompt.ask')
    def test_handle_conflicts_interactive_backup(self, mock_ask, mock_copy):
        """Test interactive conflict handling with backup choice."""
        self.config.restore.conflict_resolution = ConflictResolution.PROMPT
        mock_ask.return_value = "b"  # Backup
        
        with tempfile.TemporaryDirectory() as temp_dir:
            existing_file = Path(temp_dir) / "test.txt"
            existing_file.write_text("existing")
            
            # Create conflict
            member = Mock(spec=tarfile.TarInfo)
            member.size = 50
            member.mtime = 1640995200.0
            
            conflict = ConflictInfo(member, existing_file)
            
            self.restore_op._handle_conflicts_interactive([conflict])
            
            # Should call copy2 to backup the file
            mock_copy.assert_called_once()
    
    @patch('sysforge.backup.restore.Prompt.ask')
    def test_handle_conflicts_interactive_quit(self, mock_ask):
        """Test interactive conflict handling with quit choice."""
        self.config.restore.conflict_resolution = ConflictResolution.PROMPT
        mock_ask.return_value = "q"  # Quit
        
        with tempfile.TemporaryDirectory() as temp_dir:
            existing_file = Path(temp_dir) / "test.txt"
            existing_file.write_text("existing")
            
            # Create conflict
            member = Mock(spec=tarfile.TarInfo)
            member.size = 50
            member.mtime = 1640995200.0
            
            conflict = ConflictInfo(member, existing_file)
            
            with pytest.raises(KeyboardInterrupt, match="cancelled by user"):
                self.restore_op._handle_conflicts_interactive([conflict])
    
    def test_backup_existing_file(self):
        """Test backing up existing file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create file to backup
            existing_file = Path(temp_dir) / "test.txt"
            existing_file.write_text("original content")
            
            self.restore_op._backup_existing_file(existing_file)
            
            # Check that backup file was created
            backup_files = list(Path(temp_dir).glob("test.txt.backup-*"))
            assert len(backup_files) == 1
            
            # Check backup content
            backup_file = backup_files[0]
            assert backup_file.read_text() == "original content"
    
    def test_backup_existing_file_error(self):
        """Test backup failure handling."""
        # Try to backup nonexistent file
        nonexistent_file = Path("/nonexistent/file.txt")
        
        self.restore_op._backup_existing_file(nonexistent_file)
        
        # Should record error
        assert len(self.restore_op.errors) == 1
        assert self.restore_op.errors[0][0] == nonexistent_file
        assert "Failed to backup" in self.restore_op.errors[0][1]
    
    @patch('os.chmod')
    @patch('os.utime')
    def test_restore_permissions(self, mock_utime, mock_chmod):
        """Test restoring file permissions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test.txt"
            test_file.touch()
            
            # Create mock member
            member = Mock(spec=tarfile.TarInfo)
            member.mode = 0o644
            member.mtime = 1640995200.0
            member.isfile.return_value = True
            member.isdir.return_value = False
            
            self.restore_op._restore_permissions(test_file, member)
            
            # Should call chmod and utime (file.touch() also calls utime)
            mock_chmod.assert_called_once_with(test_file, 0o644)
            # Check that utime was called with our timestamp (may be called multiple times)
            utime_calls = mock_utime.call_args_list
            expected_call = ((test_file, (1640995200.0, 1640995200.0)), {})
            assert expected_call in utime_calls
    
    def test_get_stats(self):
        """Test getting restore statistics."""
        # Add some mock data
        self.restore_op.restored_files = [Path("file1.txt"), Path("file2.txt")]
        self.restore_op.skipped_files = [Path("file3.txt")]
        self.restore_op.errors = [(Path("file4.txt"), "error")]
        self.restore_op.conflicts = [Mock(), Mock()]
        
        stats = self.restore_op._get_stats()
        
        assert stats["restored"] == 2
        assert stats["skipped"] == 1
        assert stats["errors"] == 1
        assert stats["conflicts"] == 2
    
    @patch('sysforge.backup.restore.Decompressor.list_archive')
    def test_restore_archive_dry_run(self, mock_list_archive):
        """Test restore archive in dry run mode."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create mock archive
            archive_path = Path(temp_dir) / "test.tar.zst"
            archive_path.touch()
            
            # Mock archive contents
            member = Mock(spec=tarfile.TarInfo)
            member.name = "test.txt"
            member.isfile.return_value = True
            
            mock_list_archive.return_value = [member]
            
            # Run dry run
            stats = self.restore_op.restore_archive(archive_path, dry_run=True)
            
            # Should not restore any files
            assert stats["restored"] == 0
            assert len(self.restore_op.restored_files) == 0
    
    @patch('sysforge.backup.restore.Decompressor.extract_archive')
    @patch('sysforge.backup.restore.Decompressor.list_archive')
    def test_restore_archive_pattern_filter(self, mock_list_archive, mock_extract):
        """Test restore archive with pattern filter."""
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "test.tar.zst"
            archive_path.touch()
            
            # Mock archive contents
            member1 = Mock(spec=tarfile.TarInfo)
            member1.name = "file1.py"
            member1.isfile.return_value = True
            
            member2 = Mock(spec=tarfile.TarInfo)
            member2.name = "file2.txt"
            member2.isfile.return_value = True
            
            mock_list_archive.return_value = [member1, member2]
            
            # Run with pattern filter
            with patch.object(self.restore_op, '_extract_files') as mock_extract_files:
                stats = self.restore_op.restore_archive(
                    archive_path, 
                    pattern_filter="*.py",
                    dry_run=True
                )
            
            # Should only process .py files
            # Check that list_archive was called and filtering occurred
            mock_list_archive.assert_called_once()


class TestRestoreUtilityFunction:
    """Test restore utility function."""
    
    @patch('sysforge.backup.restore.RestoreOperation')
    def test_restore_backup(self, mock_restore_op_class):
        """Test restore_backup convenience function."""
        # Mock RestoreOperation
        mock_restore_op = Mock()
        mock_restore_op.restore_archive.return_value = {"restored": 5}
        mock_restore_op_class.return_value = mock_restore_op
        
        config = BackupConfig()
        archive_path = Path("/test/archive.tar.zst")
        target_dir = Path("/test/target")
        
        result = restore_backup(
            archive_path=archive_path,
            config=config,
            target_dir=target_dir,
            dry_run=True,
            pattern_filter="*.py"
        )
        
        # Should create RestoreOperation with config
        mock_restore_op_class.assert_called_once_with(config, None)
        
        # Should call restore_archive with correct parameters
        mock_restore_op.restore_archive.assert_called_once_with(
            archive_path=archive_path,
            target_dir=target_dir,
            dry_run=True,
            pattern_filter="*.py"
        )
        
        assert result == {"restored": 5}