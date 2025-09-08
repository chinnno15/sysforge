"""Sphinx configuration."""

project = "Sysforge"
author = "System Tools Team"
copyright = "2025, System Tools Team"
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_click",
    "myst_parser",
]
autodoc_typehints = "description"
html_theme = "shibuya"
