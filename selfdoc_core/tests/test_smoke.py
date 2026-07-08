"""Smoke tests for selfdoc_core -- verify the package imports and basic
extractor registry works."""

import selfdoc_core


def test_import():
    """Package imports without error."""
    assert hasattr(selfdoc_core, "__version__")


def test_extractor_registry():
    """Language extractor registry returns known languages."""
    from selfdoc_core.extractors import EXTRACTORS

    assert "python" in EXTRACTORS
    assert "go" in EXTRACTORS
