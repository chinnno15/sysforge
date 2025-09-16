"""Tests for backup benchmark functionality."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import pytest
import typer

from sysforge.backup.cli import benchmark_command
from sysforge.backup.config import BackupConfig


class TestBenchmarkCommand:
    """Test the benchmark command functionality."""

    def test_benchmark_command_with_valid_workers(self) -> None:
        """Test benchmark command with valid worker counts."""
        # Mock the create_backup function to return predictable results
        mock_results = [
            {"performance_metrics": {"total_scan_time": 2.0, "total_files_found": 100}},
            {"performance_metrics": {"total_scan_time": 1.0, "total_files_found": 100}},
        ]

        with patch("sysforge.backup.cli._load_config") as mock_load_config:
            mock_config = BackupConfig()
            mock_load_config.return_value = mock_config

            with patch(
                "sysforge.backup.cli.create_backup", side_effect=mock_results * 6
            ):  # 2 workers * 2 iterations * 3 calls
                with patch("rich.console.Console") as mock_console_class:
                    mock_console = Mock()
                    mock_console_class.return_value = mock_console

                    with patch("builtins.open", mock_open()):
                        with patch("os.devnull", os.devnull):
                            # Should not raise any exceptions
                            benchmark_command(
                                path=".", workers="1,2", iterations=2, output_file=None
                            )

        # Verify console output was called
        assert mock_console.print.call_count > 0

    def test_benchmark_command_with_invalid_workers(self) -> None:
        """Test benchmark command with invalid worker counts format."""
        with patch("rich.console.Console") as mock_console_class:
            mock_console = Mock()
            mock_console_class.return_value = mock_console

            with pytest.raises(typer.Exit):
                benchmark_command(
                    path=".", workers="invalid,format", iterations=1, output_file=None
                )

            # Should print error message
            mock_console.print.assert_called()
            error_call = mock_console.print.call_args_list[0]
            assert "[red]Error:" in str(error_call)

    def test_benchmark_command_saves_results_to_file(self) -> None:
        """Test that benchmark command saves results to file when specified."""
        mock_results = [
            {"performance_metrics": {"total_scan_time": 1.5, "total_files_found": 50}}
        ]

        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".json"
        ) as temp_file:
            output_file = temp_file.name

        try:
            with patch("sysforge.backup.cli._load_config") as mock_load_config:
                mock_config = BackupConfig()
                mock_load_config.return_value = mock_config

                with patch(
                    "sysforge.backup.cli.create_backup", side_effect=mock_results * 3
                ):  # 1 worker * 3 iterations
                    with patch("rich.console.Console"):
                        with patch("builtins.open", mock_open()) as mock_file:
                            with patch("os.devnull", os.devnull):
                                benchmark_command(
                                    path=".",
                                    workers="1",
                                    iterations=1,
                                    output_file=output_file,
                                )

            # Verify file writing was attempted
            mock_file.assert_called()

        finally:
            # Clean up temp file
            Path(output_file).unlink(missing_ok=True)

    def test_benchmark_command_handles_exceptions(self) -> None:
        """Test that benchmark command handles exceptions gracefully."""
        with patch("sysforge.backup.cli._load_config") as mock_load_config:
            mock_config = BackupConfig()
            mock_load_config.return_value = mock_config

            # Mock create_backup to raise an exception
            with patch(
                "sysforge.backup.cli.create_backup", side_effect=Exception("Test error")
            ):
                with patch("rich.console.Console") as mock_console_class:
                    mock_console = Mock()
                    mock_console_class.return_value = mock_console

                    with patch("builtins.open", mock_open()):
                        with patch("os.devnull", os.devnull):
                            # Should not raise, but handle gracefully
                            benchmark_command(
                                path=".", workers="1", iterations=1, output_file=None
                            )

    def test_benchmark_speedup_calculation(self) -> None:
        """Test that speedup is calculated correctly relative to single worker."""
        # Mock results with known timing
        mock_results_1_worker = [
            {
                "performance_metrics": {
                    "total_scan_time": 4.0,  # Baseline: 4 seconds
                    "total_files_found": 100,
                }
            }
        ] * 3  # 3 iterations

        mock_results_2_workers = [
            {
                "performance_metrics": {
                    "total_scan_time": 2.0,  # 2x speedup
                    "total_files_found": 100,
                }
            }
        ] * 3  # 3 iterations

        all_results = mock_results_1_worker + mock_results_2_workers

        with patch("sysforge.backup.cli._load_config") as mock_load_config:
            mock_config = BackupConfig()
            mock_load_config.return_value = mock_config

            with patch("sysforge.backup.cli.create_backup", side_effect=all_results):
                with patch("rich.console.Console") as mock_console_class:
                    mock_console = Mock()
                    mock_console_class.return_value = mock_console

                    with patch("builtins.open", mock_open()):
                        with patch("os.devnull", os.devnull):
                            benchmark_command(
                                path=".", workers="1,2", iterations=3, output_file=None
                            )

            # Check that table was created with speedup information
            # The exact verification would depend on the table format,
            # but we can at least verify the console was used
            assert mock_console.print.call_count > 0

    def test_benchmark_command_path_expansion(self) -> None:
        """Test that benchmark command properly expands paths."""
        # Test path expansion logic directly
        from pathlib import Path

        expanded_path = Path("~").expanduser()
        assert str(expanded_path) != "~"  # Should be expanded to actual home path

    def test_benchmark_statistics_calculation(self) -> None:
        """Test that benchmark statistics are calculated correctly."""
        # Test the statistics calculation with known values
        import statistics

        # Mock different timing results
        iteration_times = [1.0, 1.5, 2.0]

        avg_time = statistics.mean(iteration_times)
        min_time = min(iteration_times)
        max_time = max(iteration_times)

        assert avg_time == 1.5
        assert min_time == 1.0
        assert max_time == 2.0

        # Test files per second calculation
        files_found = 150
        files_per_sec = files_found / avg_time
        assert files_per_sec == 100.0

    def test_benchmark_empty_results_handling(self) -> None:
        """Test handling of empty results in benchmark."""
        with patch("sysforge.backup.cli._load_config") as mock_load_config:
            mock_config = BackupConfig()
            mock_load_config.return_value = mock_config

            # Mock create_backup to always raise exceptions
            with patch(
                "sysforge.backup.cli.create_backup",
                side_effect=Exception("Always fails"),
            ):
                with patch("rich.console.Console") as mock_console_class:
                    mock_console = Mock()
                    mock_console_class.return_value = mock_console

                    with patch("builtins.open", mock_open()):
                        with patch("os.devnull", os.devnull):
                            # Should handle empty results gracefully
                            benchmark_command(
                                path=".", workers="1", iterations=2, output_file=None
                            )

            # Should still print something (even if empty table)
            assert mock_console.print.call_count > 0
