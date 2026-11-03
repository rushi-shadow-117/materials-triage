"""The hand-written Spearman agrees with scipy (installed through pymatgen) including ties."""

import math
import warnings

from hypothesis import given, settings
from hypothesis import strategies as st
from scipy.stats import spearmanr
from validation.spearman import average_ranks, spearman


def test_average_ranks_share_positions_on_ties() -> None:
    assert average_ranks([10.0, 20.0, 20.0, 30.0]) == [1.0, 2.5, 2.5, 4.0]
    assert average_ranks([5.0, 5.0, 5.0]) == [2.0, 2.0, 2.0]
    assert average_ranks([3.0, 1.0, 2.0]) == [3.0, 1.0, 2.0]


def test_perfect_and_reversed() -> None:
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]).rho == 1.0
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]).rho == -1.0


def test_degenerate_inputs_are_none_with_a_reason() -> None:
    assert spearman([1.0], [2.0]) == spearman([1.0], [2.0])
    assert spearman([1.0], [2.0]).rho is None and spearman([1.0], [2.0]).n == 1
    assert spearman([], []).reason == "fewer than two pairs"
    assert spearman([1, 1, 1], [1, 2, 3]).reason == "constant ranks on one side"


def test_ties_match_scipy() -> None:
    x = [1.0, 2.0, 2.0, 3.0, 5.0, 5.0, 5.0, 8.0]
    y = [2.0, 1.0, 4.0, 4.0, 6.0, 5.0, 9.0, 9.0]
    ours = spearman(x, y).rho
    theirs = float(spearmanr(x, y).statistic)
    assert ours is not None and math.isclose(ours, theirs, abs_tol=1e-12)


@settings(max_examples=200, deadline=None)
@given(
    st.lists(st.integers(min_value=0, max_value=6), min_size=2, max_size=12),
    st.lists(st.integers(min_value=0, max_value=6), min_size=2, max_size=12),
)
def test_matches_scipy_on_random_small_lists(a: list[int], b: list[int]) -> None:
    n = min(len(a), len(b))
    x, y = [float(v) for v in a[:n]], [float(v) for v in b[:n]]
    ours = spearman(x, y)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        theirs = spearmanr(x, y).statistic
    if ours.rho is None:
        assert math.isnan(float(theirs))
    else:
        assert math.isclose(ours.rho, float(theirs), abs_tol=1e-12)
