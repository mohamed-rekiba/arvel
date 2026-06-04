"""Universal properties for `calculate_responsive_widths`.

Not Hypothesis-driven (avoiding the dev-dep cost), just dense parametrize
sweeps. The function is deterministic and only has two integer inputs, so a
sample of ~70 (width, file_size) pairs across the realistic range catches any
ordering / duplication / overflow regression without needing generators.
"""

from __future__ import annotations

import pytest
from arvel_image.media.responsive_image_generator import calculate_responsive_widths

# Sample widths from "tiny thumbnail" through "8K source". Each one stresses
# the loop's break conditions differently — sub-MIN_WIDTH steps trigger early
# stop, file-size estimate triggers second early stop.
_WIDTHS = [
    20,
    21,
    32,
    50,
    100,
    150,
    200,
    320,
    400,
    480,
    640,
    768,
    800,
    1024,
    1200,
    1366,
    1440,
    1600,
    1920,
    2048,
    2400,
    2560,
    3000,
    3840,
    4096,
    5120,
    7680,
    8192,
]

# File sizes from "tiny" (forces immediate file-size break) through "huge" (only
# the width-based break ever fires).
_FILE_SIZES = [10_000, 100_000, 1_000_000, 5_000_000, 25_000_000]


@pytest.mark.parametrize("width", _WIDTHS)
@pytest.mark.parametrize("file_size", _FILE_SIZES)
def test_returns_ascending_with_no_duplicates(width: int, file_size: int) -> None:
    """Every returned widths list is sorted ascending and has no duplicates."""
    result = calculate_responsive_widths(width, file_size)
    assert result == sorted(result), f"not ascending for ({width}, {file_size}): {result}"
    assert len(result) == len(set(result)), f"duplicates for ({width}, {file_size}): {result}"


@pytest.mark.parametrize("width", _WIDTHS)
@pytest.mark.parametrize("file_size", _FILE_SIZES)
def test_every_width_is_less_than_or_equal_to_original(width: int, file_size: int) -> None:
    """No returned width exceeds the original — srcset can only shrink."""
    for w in calculate_responsive_widths(width, file_size):
        assert w <= width, f"width {w} exceeds original {width} (file_size={file_size})"


@pytest.mark.parametrize("width", _WIDTHS)
@pytest.mark.parametrize("file_size", _FILE_SIZES)
def test_result_is_non_empty_and_includes_original(width: int, file_size: int) -> None:
    """Result always contains the original width — even at tiny file sizes."""
    result = calculate_responsive_widths(width, file_size)
    assert result, f"empty result for ({width}, {file_size})"
    assert width in result, f"original {width} missing from {result}"


def test_tiny_file_size_returns_only_the_original() -> None:
    """When the file is already below _MIN_FILE_SIZE, no smaller widths are added."""
    result = calculate_responsive_widths(1920, 5_000)  # 5 KB << 10 KB floor
    assert result == [1920]


def test_below_min_width_after_one_step_returns_only_original() -> None:
    """Original just above MIN_WIDTH — one shrink lands below 20, no second entry."""
    # 20 * sqrt(0.7) ≈ 16.7 → int = 16, < _MIN_WIDTH, loop breaks immediately.
    result = calculate_responsive_widths(20, 10_000_000)
    assert result == [20]


def test_idempotent_for_same_inputs() -> None:
    """Pure function — same inputs always produce the same list."""
    a = calculate_responsive_widths(1920, 800_000)
    b = calculate_responsive_widths(1920, 800_000)
    assert a == b
