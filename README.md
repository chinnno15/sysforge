# Sysforge

[![PyPI](https://img.shields.io/pypi/v/sysforge.svg)][pypi status]
[![Status](https://img.shields.io/pypi/status/sysforge.svg)][pypi status]
[![Python Version](https://img.shields.io/pypi/pyversions/sysforge)][pypi status]
[![License](https://img.shields.io/pypi/l/sysforge)][license]

[![Read the documentation at https://sysforge.readthedocs.io/](https://img.shields.io/readthedocs/sysforge/latest.svg?label=Read%20the%20Docs)][read the docs]
[![Tests](https://github.com/bosd/sysforge/workflows/Tests/badge.svg)][tests]
[![Codecov](https://codecov.io/gh/bosd/sysforge/branch/main/graph/badge.svg)][codecov]

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)][pre-commit]
[![Ruff codestyle][ruff badge]][ruff project]

[pypi status]: https://pypi.org/project/sysforge/
[read the docs]: https://sysforge.readthedocs.io/
[tests]: https://github.com/bosd/sysforge/actions?workflow=Tests
[codecov]: https://app.codecov.io/gh/bosd/sysforge
[pre-commit]: https://github.com/pre-commit/pre-commit
[ruff badge]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
[ruff project]: https://github.com/charliermarsh/ruff

## Features

Modern Python toolkit for Linux system administration and automation:

- 🚀 **Fast & Modern**: Built with UV package manager for 10-100x faster dependency management
- 🎨 **Rich CLI**: Beautiful terminal output with Rich library and Typer framework
- 📊 **System Monitoring**: Real-time CPU, memory, disk, and network statistics
- 🔧 **Process Management**: View and analyze running processes with sorting and filtering
- 🌐 **Network Tools**: Network interface information and I/O statistics
- ⚡ **Type-Safe**: Full type hints with mypy strict mode
- 🧪 **Well-Tested**: Comprehensive test coverage with pytest
- 📦 **Performance**: Optional mypyc compilation for enhanced performance

## Requirements

- Python 3.9 or higher
- Linux operating system
- UV package manager (for development)

## Installation

You can install _Sysforge_ via [pip] from [PyPI]. The package is distributed as a pure Python package, but also with pre-compiled wheels for major platforms, which include performance optimizations.

```console
$ pip install sysforge
```

The pre-compiled wheels are built using `mypyc` and will be used automatically if your platform is supported.

### Development Installation

For development, we recommend using UV:

```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup
git clone https://github.com/bosd/sysforge.git
cd sysforge
uv sync

# Run the CLI
uv run sysforge --help
```

## Usage

### System Status

Get a comprehensive overview of your system:

```bash
sysforge status
```

Shows:
- Hostname and platform information
- CPU cores and usage
- Memory statistics
- Disk usage
- System boot time

### Process Management

List top processes by various criteria:

```bash
# Show top 10 processes by CPU usage (default)
sysforge processes

# Show top 20 processes sorted by memory
sysforge processes --top 20 --sort memory

# Sort by process name
sysforge processes --sort name
```

### Network Information

Display network interfaces and statistics:

```bash
sysforge network
```

Shows:
- Network interface status (UP/DOWN)
- IP addresses and netmasks
- Network I/O statistics (bytes sent/received, packets)

Please see the [Command-line Reference] for more details.

## Configuration

Sysforge supports environment variables for configuration:

```bash
# Set default number of processes to show
export SYSFORGE_DEFAULT_TOP_PROCESSES=20

# Set default sort criteria
export SYSFORGE_DEFAULT_SORT_BY=memory

# Disable colored output
export SYSFORGE_USE_COLORS=false
```

You can also use a `.env` file in the project root.

## Development

To contribute to this project, please see the [Contributor Guide].

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov

# Run linting
uv run ruff check src/ tests/

# Run type checking
uv run mypy src/
```

### Mypyc Compilation

This project can be compiled with `mypyc` to produce a high-performance version of the package. The compilation is optional and is controlled by an environment variable.

To build and install the compiled version locally, you can use the `tests_compiled` nox session:

```console
$ nox -s tests_compiled
```

This will set the `SYSFORGE_COMPILE_MYPYC=1` environment variable, which triggers the compilation logic in `setup.py`. The compiled package will be installed in editable mode in a new virtual environment.

You can also build the compiled wheels for distribution using the `cibuildwheel` workflow, which is configured to run on releases. If you want to build the wheels locally, you can use `cibuildwheel` directly:

```console
$ pip install cibuildwheel
$ export SYSFORGE_COMPILE_MYPYC=1
$ cibuildwheel --output-dir wheelhouse
```

This will create the compiled wheels in the `wheelhouse` directory.

## Contributing

Contributions are very welcome.
To learn more, see the [Contributor Guide].

## License

Distributed under the terms of the [MIT license][license],
_Sysforge_ is free and open source software.

## Issues

If you encounter any problems,
please [file an issue] along with a detailed description.

## Credits

This project was generated from [@cjolowicz]'s [uv hypermodern python cookiecutter] template.

[@cjolowicz]: https://github.com/cjolowicz
[pypi]: https://pypi.org/
[uv hypermodern python cookiecutter]: https://github.com/bosd/cookiecutter-uv-hypermodern-python
[file an issue]: https://github.com/bosd/sysforge/issues
[pip]: https://pip.pypa.io/

<!-- github-only -->

[license]: https://github.com/bosd/sysforge/blob/main/LICENSE
[contributor guide]: https://github.com/bosd/sysforge/blob/main/CONTRIBUTING.md
[command-line reference]: https://sysforge.readthedocs.io/en/latest/usage.html