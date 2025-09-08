"""Tests for backup configuration system."""

import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from sysforge.backup.config import (
    BackupConfig,
    CompressionConfig,
    CompressionFormat,
    ConfigManager,
    ConflictResolution,
    GitConfig,
    RestoreConfig,
    TargetConfig,
)


class TestCompressionConfig:
    """Test compression configuration."""
    
    def test_default_compression_config(self):
        """Test default compression configuration."""
        config = CompressionConfig()
        assert config.format == CompressionFormat.ZSTD
        assert config.level == 3
    
    def test_compression_level_validation(self):
        """Test compression level validation for different formats."""
        # Valid ZSTD levels
        config = CompressionConfig(format=CompressionFormat.ZSTD, level=1)
        assert config.level == 1
        
        config = CompressionConfig(format=CompressionFormat.ZSTD, level=22)
        assert config.level == 22
        
        # Valid GZIP levels
        config = CompressionConfig(format=CompressionFormat.GZIP, level=1)
        assert config.level == 1
        
        config = CompressionConfig(format=CompressionFormat.GZIP, level=9)
        assert config.level == 9
        
        # Invalid ZSTD level - pydantic will catch this with Field constraints first
        with pytest.raises(ValidationError):
            CompressionConfig(format=CompressionFormat.ZSTD, level=25)
        
        # Invalid GZIP level
        with pytest.raises(ValidationError):
            CompressionConfig(format=CompressionFormat.GZIP, level=15)


class TestTargetConfig:
    """Test target configuration."""
    
    def test_default_target_config(self):
        """Test default target configuration."""
        config = TargetConfig()
        assert config.base_path == "~"
        assert "backup-{timestamp}" in config.output_path
    
    def test_get_base_path(self):
        """Test base path expansion."""
        config = TargetConfig(base_path="~/Work")
        base_path = config.get_base_path()
        assert isinstance(base_path, Path)
        assert str(base_path).startswith('/')  # Should be absolute path
    
    def test_get_output_path(self):
        """Test output path with timestamp."""
        from datetime import datetime
        
        config = TargetConfig(output_path="~/backups/test-{timestamp}.tar.zst")
        timestamp = datetime(2024, 1, 15, 14, 30, 0)
        
        output_path = config.get_output_path(timestamp)
        assert isinstance(output_path, Path)
        assert "test-2024-01-15_14-30-00.tar.zst" in str(output_path)


class TestGitConfig:
    """Test git configuration."""
    
    def test_default_git_config(self):
        """Test default git configuration."""
        config = GitConfig()
        assert config.include_repos is True
        assert config.respect_gitignore is False  # Changed to False for complete git backup
        assert config.include_git_dir is True
        assert config.backup_complete_git is True  # New field for complete git backup
        assert len(config.gitignore_override_patterns) > 0  # Should have default override patterns
        assert "**/.env*" in config.gitignore_override_patterns


class TestRestoreConfig:
    """Test restore configuration."""
    
    def test_default_restore_config(self):
        """Test default restore configuration."""
        config = RestoreConfig()
        assert config.conflict_resolution == ConflictResolution.PROMPT
        assert config.preserve_permissions is True
        assert config.create_backup_on_conflict is True
        assert "{timestamp}" in config.backup_suffix
    
    def test_get_backup_suffix(self):
        """Test backup suffix with timestamp."""
        from datetime import datetime
        
        config = RestoreConfig(backup_suffix=".backup-{timestamp}")
        timestamp = datetime(2024, 1, 15, 14, 30, 0)
        
        suffix = config.get_backup_suffix(timestamp)
        assert suffix == ".backup-20240115_143000"


class TestBackupConfig:
    """Test complete backup configuration."""
    
    def test_default_backup_config(self):
        """Test default backup configuration."""
        config = BackupConfig()
        
        # Check components
        assert isinstance(config.compression, CompressionConfig)
        assert isinstance(config.target, TargetConfig)
        assert isinstance(config.git, GitConfig)
        assert isinstance(config.restore, RestoreConfig)
        
        # Check patterns
        assert len(config.include_patterns) > 0
        assert len(config.exclude_patterns) > 0
        assert len(config.always_exclude) > 0
        
        # Check max file size
        assert config.max_file_size == "100MB"
    
    def test_get_max_file_size_bytes(self):
        """Test max file size conversion."""
        config = BackupConfig(max_file_size="50MB")
        assert config.get_max_file_size_bytes() == 50 * 1024 * 1024
        
        config = BackupConfig(max_file_size="2GB")
        assert config.get_max_file_size_bytes() == 2 * 1024 * 1024 * 1024
        
        config = BackupConfig(max_file_size="512KB")
        assert config.get_max_file_size_bytes() == 512 * 1024
        
        config = BackupConfig(max_file_size="1024")
        assert config.get_max_file_size_bytes() == 1024


class TestConfigManager:
    """Test configuration manager."""
    
    def test_get_default_config(self):
        """Test getting default configuration."""
        config = ConfigManager.get_default_config()
        assert isinstance(config, BackupConfig)
    
    def test_merge_configs(self):
        """Test configuration merging."""
        config1 = {
            "compression": {"level": 5},
            "target": {"base_path": "~/Work"}
        }
        
        config2 = {
            "compression": {"format": "lz4"},
            "git": {"include_repos": False}
        }
        
        merged = ConfigManager.merge_configs(config1, config2)
        
        assert merged["compression"]["level"] == 5  # From config1
        assert merged["compression"]["format"] == "lz4"  # From config2
        assert merged["target"]["base_path"] == "~/Work"  # From config1
        assert merged["git"]["include_repos"] is False  # From config2
    
    def test_merge_configs_with_none(self):
        """Test merging with None values."""
        config1 = {"compression": {"level": 5}}
        
        merged = ConfigManager.merge_configs(config1, None)
        assert merged == config1
        
        merged = ConfigManager.merge_configs(None, config1)
        assert merged == config1
        
        merged = ConfigManager.merge_configs(None, None)
        assert merged == {}
    
    @patch('sysforge.backup.config.Path.exists')
    @patch('builtins.open')
    def test_load_user_config(self, mock_open, mock_exists):
        """Test loading user configuration."""
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = """
        compression:
          level: 8
        target:
          base_path: "~/Documents"
        """
        
        with patch('yaml.safe_load') as mock_yaml:
            mock_yaml.return_value = {
                "compression": {"level": 8},
                "target": {"base_path": "~/Documents"}
            }
            
            config = ConfigManager.load_user_config()
            assert config is not None
            assert config["compression"]["level"] == 8
            assert config["target"]["base_path"] == "~/Documents"
    
    @patch('sysforge.backup.config.Path.exists')
    def test_load_user_config_not_exists(self, mock_exists):
        """Test loading user config when file doesn't exist."""
        mock_exists.return_value = False
        config = ConfigManager.load_user_config()
        assert config is None
    
    def test_load_effective_config_default_only(self):
        """Test loading effective config with only defaults."""
        with patch.object(ConfigManager, 'load_user_config', return_value=None):
            config = ConfigManager.load_effective_config()
            assert isinstance(config, BackupConfig)
            assert config.compression.format == CompressionFormat.ZSTD
    
    def test_load_effective_config_with_overrides(self):
        """Test loading effective config with overrides."""
        overrides = {
            "compression": {"level": 10},
            "target": {"base_path": "/custom/path"}
        }
        
        with patch.object(ConfigManager, 'load_user_config', return_value=None):
            config = ConfigManager.load_effective_config(overrides=overrides)
            assert config.compression.level == 10
            assert config.target.base_path == "/custom/path"
    
    def test_save_and_load_config_integration(self):
        """Test saving and loading configuration (integration)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Mock config directories
            with patch.object(ConfigManager, 'CONFIG_DIR', temp_path):
                with patch.object(ConfigManager, 'USER_CONFIG_FILE', temp_path / "config.yaml"):
                    
                    # Save config
                    test_config = {
                        "compression": {"level": 7},
                        "target": {"base_path": "~/TestDir"}
                    }
                    ConfigManager.save_user_config(test_config)
                    
                    # Load config
                    loaded_config = ConfigManager.load_user_config()
                    assert loaded_config is not None
                    assert loaded_config["compression"]["level"] == 7
                    assert loaded_config["target"]["base_path"] == "~/TestDir"
    
    def test_list_profiles_empty(self):
        """Test listing profiles when none exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            profiles_dir = temp_path / "profiles"
            profiles_dir.mkdir()
            
            with patch.object(ConfigManager, 'PROFILES_DIR', profiles_dir):
                profiles = ConfigManager.list_profiles()
                assert profiles == []
    
    def test_list_profiles_with_files(self):
        """Test listing profiles with existing files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            profiles_dir = temp_path / "profiles"
            profiles_dir.mkdir()
            
            # Create profile files
            (profiles_dir / "work.yaml").touch()
            (profiles_dir / "personal.yaml").touch()
            (profiles_dir / "not_yaml.txt").touch()  # Should be ignored
            
            with patch.object(ConfigManager, 'PROFILES_DIR', profiles_dir):
                profiles = ConfigManager.list_profiles()
                assert sorted(profiles) == ["personal", "work"]
    
    def test_list_backups_empty(self):
        """Test listing backups when none exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backups_dir = temp_path / "backups"
            backups_dir.mkdir()
            
            with patch.object(ConfigManager, 'BACKUPS_DIR', backups_dir):
                backups = ConfigManager.list_backups()
                assert backups == []
    
    def test_list_backups_with_files(self):
        """Test listing backups with existing files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backups_dir = temp_path / "backups"
            backups_dir.mkdir()
            
            # Create backup files
            (backups_dir / "backup1.tar.zst").touch()
            (backups_dir / "backup2.tar.lz4").touch()
            (backups_dir / "backup3.tar.gz").touch()
            (backups_dir / "not_backup.txt").touch()  # Should be ignored
            
            with patch.object(ConfigManager, 'BACKUPS_DIR', backups_dir):
                backups = ConfigManager.list_backups()
                backup_names = [backup.name for backup in backups]
                assert "backup1.tar.zst" in backup_names
                assert "backup2.tar.lz4" in backup_names
                assert "backup3.tar.gz" in backup_names
                assert "not_backup.txt" not in backup_names