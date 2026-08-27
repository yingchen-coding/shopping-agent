"""The GUI's own display rules, which are domain rules rather than styling."""
import pytest

pytest.importorskip("PySide6", reason="GUI extra not installed")

from shopping_agent.gui import format_score
from shopping_agent.scoring import UNKNOWN


def test_unknown_never_renders_as_a_number():
    """An unassessed product must not read as one that scored badly."""
    rendered = format_score(UNKNOWN)
    assert "?" in rendered
    assert "0" not in rendered


def test_a_real_score_renders_numerically():
    assert format_score(0.0).strip() == "0.00"
    assert format_score(0.875).strip() == "0.88"
    assert format_score(1.0).strip() == "1.00"


def test_zero_and_unknown_are_visibly_different():
    """The whole point: 'scored zero' and 'could not be scored' must not look alike."""
    assert format_score(0.0).strip() != format_score(UNKNOWN).strip()
