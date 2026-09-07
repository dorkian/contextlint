import pytest

from contextlint.tokens import (
    DEFAULT_PARAMS,
    BACKENDS,
    HeuristicParams,
    get_counter,
    heuristic_count,
)


def test_empty_is_zero():
    assert heuristic_count("") == 0
    assert heuristic_count("   ") >= 0


def test_monotonic_in_length():
    short = heuristic_count("the quick brown fox")
    long = heuristic_count("the quick brown fox " * 20)
    assert long > short


@pytest.mark.parametrize(
    "text,lo,hi",
    [
        ("The quick brown fox jumps over the lazy dog.", 8, 14),
        ("hello world", 1, 4),
        ('{"name":"get_weather","description":"Get the weather"}', 8, 22),
    ],
)
def test_within_plausible_range(text, lo, hi):
    """Guards against a parameter edit that silently breaks every published number."""
    assert lo <= heuristic_count(text) <= hi


def test_params_are_honoured():
    cheap = HeuristicParams(**{**DEFAULT_PARAMS.as_dict(), "word_free": 100.0, "word_step": 100.0})
    text = "internationalisation configuration deserialisation"
    assert heuristic_count(text, cheap) < heuristic_count(text, DEFAULT_PARAMS)


def test_unknown_backend_raises():
    with pytest.raises(ValueError):
        get_counter("nope")


def test_heuristic_backend_is_the_default():
    assert get_counter() is heuristic_count
    assert "heuristic" in BACKENDS


def test_missing_optional_backend_falls_back_loudly(capsys):
    counter = get_counter("tiktoken")
    assert counter(" ") is not None
    # Either tiktoken is installed (exact) or we warned on stderr before falling back.
    if counter is heuristic_count:
        assert "falling back" in capsys.readouterr().err


def test_strict_mode_refuses_to_silently_estimate():
    """Benchmarks must never mistake an estimate for a measurement."""
    try:
        import tiktoken  # noqa: F401
    except ImportError:
        with pytest.raises(Exception):
            get_counter("tiktoken", strict=True)
    else:
        assert get_counter("tiktoken", strict=True) is not heuristic_count
