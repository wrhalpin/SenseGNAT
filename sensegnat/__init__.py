"""SenseGNAT package."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("sensegnat")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0.0.0.dev0"
