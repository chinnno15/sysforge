"""Compression utilities for backup operations."""

import gzip
import tarfile
from pathlib import Path
from typing import BinaryIO, Optional

import lz4.frame
import zstandard as zstd

from .config import CompressionFormat


class CompressorBase:
    """Base class for compressors."""

    def __init__(self, level: int):
        self.level = level

    def create_compressor(self, output_file: BinaryIO):
        """Create a compressor for the given output file."""
        raise NotImplementedError

    def get_file_extension(self) -> str:
        """Get the file extension for this compression format."""
        raise NotImplementedError


class ZstdCompressor(CompressorBase):
    """ZSTD compressor."""

    def create_compressor(self, output_file: BinaryIO):
        """Create a ZSTD compressor."""
        cctx = zstd.ZstdCompressor(level=self.level)
        return cctx.stream_writer(output_file)

    def get_file_extension(self) -> str:
        return ".zst"


class Lz4Compressor(CompressorBase):
    """LZ4 compressor."""

    def create_compressor(self, output_file: BinaryIO):
        """Create an LZ4 compressor."""
        return lz4.frame.LZ4FrameFile(
            output_file,
            mode='wb',
            compression_level=self.level
        )

    def get_file_extension(self) -> str:
        return ".lz4"


class GzipCompressor(CompressorBase):
    """GZIP compressor."""

    def create_compressor(self, output_file: BinaryIO):
        """Create a GZIP compressor."""
        return gzip.GzipFile(
            fileobj=output_file,
            mode='wb',
            compresslevel=self.level
        )

    def get_file_extension(self) -> str:
        return ".gz"


class NoCompressor(CompressorBase):
    """No compression (just tar)."""

    def __init__(self):
        super().__init__(0)

    def create_compressor(self, output_file: BinaryIO):
        """Return the output file directly (no compression)."""
        return output_file

    def get_file_extension(self) -> str:
        return ""


def get_compressor(format_type: CompressionFormat, level: int) -> CompressorBase:
    """Get the appropriate compressor for the given format."""
    if format_type == CompressionFormat.ZSTD:
        return ZstdCompressor(level)
    elif format_type == CompressionFormat.LZ4:
        return Lz4Compressor(level)
    elif format_type == CompressionFormat.GZIP:
        return GzipCompressor(level)
    else:
        raise ValueError(f"Unsupported compression format: {format_type}")


class CompressedTarFile:
    """A tar file with compression support."""

    def __init__(
        self,
        output_path: Path,
        format_type: CompressionFormat,
        compression_level: int
    ):
        self.output_path = output_path
        self.format_type = format_type
        self.compression_level = compression_level
        self.compressor = get_compressor(format_type, compression_level)

        self._output_file: Optional[BinaryIO] = None
        self._compressed_file: Optional[BinaryIO] = None
        self._tar_file: Optional[tarfile.TarFile] = None

    def __enter__(self):
        """Enter context manager."""
        self._output_file = open(self.output_path, 'wb')
        self._compressed_file = self.compressor.create_compressor(self._output_file)

        # Create tar file
        self._tar_file = tarfile.open(
            fileobj=self._compressed_file,
            mode='w|'  # Stream mode for better memory usage
        )

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager."""
        if self._tar_file:
            self._tar_file.close()
            self._tar_file = None

        if self._compressed_file and self._compressed_file != self._output_file:
            self._compressed_file.close()
            self._compressed_file = None

        if self._output_file:
            self._output_file.close()
            self._output_file = None

    def add(self, file_path: Path, arcname: Optional[str] = None):
        """Add a file to the tar archive."""
        if not self._tar_file:
            raise RuntimeError("CompressedTarFile not opened")

        try:
            self._tar_file.add(str(file_path), arcname=arcname)
        except (OSError, PermissionError) as e:
            # Log the error but continue with other files
            print(f"Warning: Could not add {file_path}: {e}")

    def add_string(self, content: str, arcname: str):
        """Add string content as a file to the tar archive."""
        if not self._tar_file:
            raise RuntimeError("CompressedTarFile not opened")

        import io

        content_bytes = content.encode('utf-8')
        tarinfo = tarfile.TarInfo(name=arcname)
        tarinfo.size = len(content_bytes)

        self._tar_file.addfile(tarinfo, io.BytesIO(content_bytes))


class Decompressor:
    """Handles decompression of backup archives."""

    @staticmethod
    def detect_format(file_path: Path) -> CompressionFormat:
        """Detect compression format from file extension."""
        suffix = file_path.suffix.lower()

        if suffix == '.zst':
            return CompressionFormat.ZSTD
        elif suffix == '.lz4':
            return CompressionFormat.LZ4
        elif suffix == '.gz':
            return CompressionFormat.GZIP
        else:
            # Assume no compression
            return CompressionFormat.GZIP  # Default for safety

    @staticmethod
    def open_archive(file_path: Path) -> tarfile.TarFile:
        """Open a compressed tar archive for reading."""
        # Try to detect format from extension
        suffix = file_path.suffix.lower()

        if suffix == '.zst':
            # ZSTD compressed
            input_file = open(file_path, 'rb')
            dctx = zstd.ZstdDecompressor()
            decompressed = dctx.stream_reader(input_file)
            return tarfile.open(fileobj=decompressed, mode='r|')

        elif suffix == '.lz4':
            # LZ4 compressed
            input_file = open(file_path, 'rb')
            decompressed = lz4.frame.LZ4FrameFile(input_file, mode='rb')
            return tarfile.open(fileobj=decompressed, mode='r|')

        elif suffix == '.gz':
            # GZIP compressed
            return tarfile.open(file_path, 'r:gz')

        else:
            # No compression
            return tarfile.open(file_path, 'r')

    @staticmethod
    def extract_archive(
        archive_path: Path,
        extract_to: Path,
        members: Optional[list] = None
    ) -> None:
        """Extract archive to specified directory."""
        extract_to.mkdir(parents=True, exist_ok=True)

        with Decompressor.open_archive(archive_path) as tar:
            if members:
                tar.extractall(path=extract_to, members=members)
            else:
                tar.extractall(path=extract_to)

    @staticmethod
    def list_archive(archive_path: Path) -> list[tarfile.TarInfo]:
        """List contents of archive."""
        with Decompressor.open_archive(archive_path) as tar:
            return tar.getmembers()


def get_recommended_extension(format_type: CompressionFormat) -> str:
    """Get the recommended file extension for a compression format."""
    compressor = get_compressor(format_type, 1)  # Level doesn't matter for extension
    return f".tar{compressor.get_file_extension()}"
