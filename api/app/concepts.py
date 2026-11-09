"""Concept names, and the validation of the concepts the model proposes.

Purpose
-------
The language model proposes concepts; this module decides which are kept
and what they are called (decision record 11). It is pure: no database, no
model, so every rule can be tested directly.

A concept's identity is its normalized name: the same text always
normalizes the same way, so "Threads" in one lecture and "Thread" in another
are one concept. Aliases never decide identity: the model's aliases are too
often descriptions ("disk busy all the time") or plain wrong ("valid bit"
for demand paging) to merge concepts on.

Validation drops what cannot be trusted rather than storing it: a concept
whose name normalizes to nothing, has no letters, or cites no passage it was
given; aliases that are empty, repeat the name or another alias, or read
like a description.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

MAX_NAME = 80
MAX_DEFINITION = 300
MAX_ALIASES = 5
MAX_ALIAS_WORDS = 4  # longer "aliases" are descriptions, not names

# Small joining words that turn up in descriptions ("disk busy all the time",
# "evicting a victim page") and rarely in names. An alias containing one is
# taken for a description. The price is the odd real alias such as
# "principle of locality"; aliases are only shown, never matched on.
_DESCRIPTION_WORDS = {
    "a",
    "an",
    "the",
    "of",
    "for",
    "to",
    "into",
    "when",
    "all",
    "by",
    "with",
    "is",
    "are",
    "that",
    "which",
    "from",
    "on",
    "in",
    "its",
    "their",
    "only",
}

# Typographic characters folded to plain ones, so "Belady’s" and "Belady's"
# are the same name.
_PLAIN = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
# A bracketed part of a name, such as the "(SJF)" in "Shortest Job First (SJF)".
_BRACKETED = re.compile(r"\s*[(\[]([^()\[\]]*)[)\]]")
_SEPARATORS = re.compile(r"[-_/]")
_NOT_WORD = re.compile(r"[^\w\s']")
_ARTICLES = {"the", "a", "an"}


def tidy(text: str) -> str:
    """Unicode-normalized, typographic quotes and dashes made plain,
    whitespace collapsed."""
    text = unicodedata.normalize("NFKC", text).translate(_PLAIN)
    return " ".join(text.split())


def split_name(name: str) -> tuple[str, list[str]]:
    """A name without its bracketed parts, and those parts:
    "Shortest Job First (SJF)" gives ("Shortest Job First", ["SJF"])."""
    name = tidy(name)
    inner = [tidy(part) for part in _BRACKETED.findall(name)]
    return tidy(_BRACKETED.sub(" ", name)), [part for part in inner if part]


def singular(word: str) -> str:
    """A conservative singular for the last word of a name: "processes" to
    "process", "policies" to "policy", "threads" to "thread". Words ending
    in -ss, -us or -is, and short words, are left alone ("address",
    "status", "analysis", "bus"). It errs towards leaving a word as it is."""
    if len(word) <= 3:
        return word
    if word.endswith("sses"):
        return word[:-2]
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def normalize(name: str) -> str:
    """The identity of a concept name: bracketed parts removed, case folded,
    hyphens and slashes read as spaces, other punctuation dropped (apostrophes
    kept, for "Banker's algorithm"), leading articles dropped, and the last
    word made singular."""
    bare, _ = split_name(name)
    text = _NOT_WORD.sub(" ", _SEPARATORS.sub(" ", bare.casefold()))
    words = text.split()
    while words and words[0] in _ARTICLES:
        words = words[1:]
    if words:
        words[-1] = singular(words[-1])
    return " ".join(words)


@dataclass
class ValidConcept:
    """A proposed concept that passed validation."""

    name: str  # as shown: tidied, bracketed parts moved to aliases
    normalized_name: str
    definition: str
    aliases: list[str] = field(default_factory=list)
    passages: list[int] = field(default_factory=list)  # in the order cited


def clean_aliases(aliases: Iterable[str], *taken: str) -> list[str]:
    """Aliases worth keeping: non-empty, a name rather than a description
    (at most MAX_ALIAS_WORDS words, none of them a joining word), and
    different from the concept's name and from each other once normalized.
    At most MAX_ALIASES."""
    seen = set(taken)
    kept = []
    for alias in aliases:
        alias = tidy(alias)
        key = normalize(alias)
        words = alias.casefold().split()
        if (
            not key
            or key in seen
            or len(alias) > MAX_NAME
            or len(words) > MAX_ALIAS_WORDS
            or _DESCRIPTION_WORDS.intersection(words)
        ):
            continue
        seen.add(key)
        kept.append(alias)
        if len(kept) == MAX_ALIASES:
            break
    return kept


def validate(proposed: Iterable, allowed: set[int]) -> tuple[list[ValidConcept], int]:
    """The concepts worth keeping from what the model proposed, and how many
    were dropped.

    Each proposal needs name, definition, aliases and sources (passage
    numbers). One is dropped when its name normalizes to nothing or has no
    letters, its name or definition is empty or too long, or none of its
    passage numbers is one the model was given. Proposals with the same
    normalized name are merged: the first name and definition are kept, and
    passages and aliases are combined.
    """
    kept: dict[str, ValidConcept] = {}
    dropped = 0
    for item in proposed:
        bare, bracketed = split_name(item.name)
        key = normalize(item.name)
        definition = tidy(item.definition)
        passages = [n for n in dict.fromkeys(item.sources) if n in allowed]
        if (
            not key
            or not re.search(r"[^\W\d_]", key)
            or len(bare) > MAX_NAME
            or not definition
            or len(definition) > MAX_DEFINITION
            or not passages
        ):
            dropped += 1
            continue
        if key in kept:
            concept = kept[key]
            concept.passages += [n for n in passages if n not in concept.passages]
            concept.aliases = clean_aliases(
                [*concept.aliases, *bracketed, *item.aliases], key
            )
            continue
        kept[key] = ValidConcept(
            name=bare,
            normalized_name=key,
            definition=definition,
            aliases=clean_aliases([*bracketed, *item.aliases], key),
            passages=passages,
        )
    return list(kept.values()), dropped
