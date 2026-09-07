"""Token counting, with the error bars stated out loud.

Three backends, in descending order of honesty-per-dependency:

``heuristic``   offline, zero dependencies, approximate. The default, because a tool
                that audits your context budget should not itself require a network
                round-trip or a 2 MB vocabulary download to answer "how big is this".
``tiktoken``    exact for OpenAI's ``o200k_base``, a close proxy for Claude. Opt-in via
                ``pip install contextlint[exact]``.
``anthropic``   exact for a named Claude model via the free ``count_tokens`` endpoint.
                Opt-in, needs ``ANTHROPIC_API_KEY``, and sends your config text to the
                API — which is why it is never the default.

The heuristic's measured error against ``tiktoken`` is reproduced by
``benchmarks/calibrate.py`` and reported in the README. Do not quote an accuracy
number that script cannot regenerate.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Callable

# --- Heuristic parameters ----------------------------------------------------
# Fitted by benchmarks/tune.py against tiktoken o200k_base over a corpus of real
# agent configuration — markdown skills, JSON tool schemas, YAML frontmatter. The
# resulting error is measured by benchmarks/calibrate.py and published in the
# README. Hand-editing these without re-running both scripts invalidates that claim.


@dataclass(frozen=True)
class HeuristicParams:
    word_free: float = 5.0      # letters absorbed by a word's first token
    word_step: float = 4.0      # additional letters per subsequent token
    digit_group: float = 3.0    # BPE groups digits in runs of up to three
    symbol_group: float = 1.6   # how far punctuation runs merge
    ws_spaces: float = 6.0      # spaces per token in an indentation run
    newline: float = 1.0        # tokens per newline character
    nonascii: float = 1.0       # tokens per non-ASCII character

    def as_dict(self) -> dict[str, float]:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}


DEFAULT_PARAMS = HeuristicParams(
    # Fitted on the training half only (benchmarks/tune.py), so the error published
    # in the README is genuinely out-of-sample for these exact values.
    word_free=10.0,
    word_step=9.0,
    digit_group=3.5,
    symbol_group=10.0,
    ws_spaces=64.0,
    newline=0.8,
    nonascii=0.75,
)

_PRETOKEN = re.compile(
    r"'(?:[sdmt]|ll|ve|re)"       # english contractions
    r"| ?[^\W\d_]+"                 # words, optionally preceded by one space
    r"| ?\d+"                       # digit runs
    r"| ?[^\s\w]+"                  # punctuation / symbol runs
    r"|\s+",                        # whitespace
    re.UNICODE,
)


def heuristic_count(text: str, params: HeuristicParams = DEFAULT_PARAMS) -> int:
    """Approximate BPE token count without a vocabulary.

    Mirrors GPT-style pre-tokenization (words carry their leading space, digits
    group in threes, symbol runs merge partially) and estimates sub-tokens per
    chunk from its length and character class.
    """
    if not text:
        return 0
    total = 0.0
    for chunk in _PRETOKEN.findall(text):
        body = chunk[1:] if chunk[:1] == " " else chunk
        if not body:
            total += 1.0
            continue
        if body.isspace():
            nl = body.count("\n") + body.count("\t")
            total += nl * params.newline
            spaces = len(body) - nl
            total += math.ceil(spaces / params.ws_spaces) if spaces else 0
            continue
        if not body.isascii():
            total += max(1.0, len(body) * params.nonascii)
            continue
        n = len(body)
        if body.isdigit():
            total += math.ceil(n / params.digit_group)
        elif body.isalpha():
            total += 1.0 if n <= params.word_free else 1.0 + math.ceil((n - params.word_free) / params.word_step)
        else:
            total += math.ceil(n / params.symbol_group)
    return int(round(total))


# --- Exact backends ----------------------------------------------------------

def _tiktoken_counter(encoding: str = "o200k_base") -> Callable[[str], int]:
    import tiktoken  # noqa: PLC0415 — optional dependency, imported on demand

    enc = tiktoken.get_encoding(encoding)
    return lambda text: len(enc.encode(text, disallowed_special=()))


def _anthropic_counter(model: str = "claude-sonnet-5") -> Callable[[str], int]:
    import anthropic  # noqa: PLC0415 — optional dependency, imported on demand

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "the anthropic backend needs ANTHROPIC_API_KEY. "
            "Use --tokenizer heuristic (offline) or --tokenizer tiktoken (local) instead."
        )
    client = anthropic.Anthropic()

    def count(text: str) -> int:
        if not text.strip():
            return 0
        r = client.messages.count_tokens(
            model=model, messages=[{"role": "user", "content": text}]
        )
        return int(r.input_tokens)

    return count


BACKENDS = ("heuristic", "tiktoken", "anthropic")


def get_counter(name: str = "heuristic", *, strict: bool = False) -> Callable[[str], int]:
    """Return a ``text -> token count`` callable.

    Falls back to the heuristic with a warning if an exact backend is unavailable,
    unless ``strict`` is set — benchmarks pass ``strict`` so a silent fallback can
    never quietly turn a measured number into an estimated one.
    """
    if name == "heuristic":
        return heuristic_count
    try:
        if name == "tiktoken":
            return _tiktoken_counter()
        if name == "anthropic":
            return _anthropic_counter()
    except Exception as exc:  # ImportError, missing key, network
        if strict:
            raise
        import sys

        print(
            f"contextlint: '{name}' tokenizer unavailable ({exc}); "
            f"falling back to the heuristic. Numbers below are estimates.",
            file=sys.stderr,
        )
        return heuristic_count
    raise ValueError(f"unknown tokenizer {name!r}; choose from {', '.join(BACKENDS)}")


def price(assets, counter: Callable[[str], int]) -> None:
    """Fill in ``always_on_tokens`` / ``on_demand_tokens`` on every asset, in place."""
    for a in assets:
        a.always_on_tokens = counter(a.always_on_text)
        a.on_demand_tokens = counter(a.on_demand_text)
