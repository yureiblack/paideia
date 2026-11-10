"""The learning roadmap's structure: which concepts, in which stages, in
which order.

Purpose
-------
The roadmap is decided here, by fixed rules, never by the model (decision
record 13). The model only writes each stage's title and description, after
the structure is settled. Pure functions, no database and no model, so the
rules can be tested directly.

The rules, in order:

1. Cycles. Prerequisites that loop (A before B, B before A, perhaps through
   others) cannot all be honoured. Each loop is found as a strongly
   connected component, kept together in one stage, in reading order, and
   reported, so the roadmap can say "learn these together".
2. Stages. Concepts joined by any relationship within the document where
   each first appears form a group. A relationship across documents orders
   groups but never merges them: one such link would otherwise glue two
   lectures together. A concept with no relationship inside its document
   joins the group of its neighbour there in reading order, the one just
   before it, else just after.
3. Stage order. Groups follow the prerequisites between them, then the
   material's own reading order. Groups whose prerequisites loop are merged.
4. Order within a stage. Prerequisites first; a whole before its parts
   unless a prerequisite says otherwise; then the concept with more
   evidence; then reading order.
5. Size. A stage of more than MAX_STAGE concepts is split, in order, into
   stages as even as possible.
"""

import hashlib
import heapq
import math
import uuid
from collections import defaultdict
from collections.abc import Callable, Hashable, Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise

MAX_STAGE = 8


@dataclass(frozen=True)
class Node:
    """A concept, as the roadmap needs it. position is where it first
    appears: the document's place in the environment (in the order the
    documents were added), then the passage's place in the document. home is
    that document. evidence is how many passages explain it."""

    id: uuid.UUID
    name: str
    normalized_name: str
    definition: str
    position: tuple[int, int]
    home: uuid.UUID
    evidence: int


@dataclass(frozen=True)
class Link:
    """A relationship from the knowledge graph."""

    source: uuid.UUID
    target: uuid.UUID
    kind: str  # PREREQUISITE_OF, PART_OF or RELATED_TO


@dataclass(frozen=True)
class Cycle:
    """Concepts whose prerequisites loop, in reading order, and the
    prerequisites forming the loop."""

    concepts: tuple[uuid.UUID, ...]
    links: tuple[tuple[uuid.UUID, uuid.UUID], ...]


@dataclass(frozen=True)
class Roadmap:
    stages: tuple[tuple[uuid.UUID, ...], ...]  # concept ids, in order
    cycles: tuple[Cycle, ...]


def _reachable(after: dict[Hashable, set], start: Hashable) -> set:
    seen, stack = set(), [start]
    while stack:
        for nxt in after.get(stack.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def strong_components(
    items: Sequence[Hashable], edges: Iterable[tuple[Hashable, Hashable]]
) -> list[list]:
    """The strongly connected components: items that can each reach the
    other along the edges. Each component lists its items in the order
    given, and components come in the order of their first item. Simple
    rather than fast: a roadmap has hundreds of concepts at most."""
    after = defaultdict(set)
    for a, b in edges:
        after[a].add(b)
    reach = {item: _reachable(after, item) for item in items}
    placed, components = set(), []
    for item in items:
        if item in placed:
            continue
        component = [
            other
            for other in items
            if other == item or (other in reach[item] and item in reach[other])
        ]
        placed.update(component)
        components.append(component)
    return components


def ordered(
    items: Sequence[Hashable],
    before: Iterable[tuple[Hashable, Hashable]],
    key: Callable[[Hashable], tuple],
) -> list:
    """A topological order (Kahn's algorithm): every (a, b) in before puts a
    ahead of b. Among the items free to come next, the smallest key comes
    first, so the order is always the same. Raises ValueError on a cycle."""
    after, waiting = defaultdict(set), dict.fromkeys(items, 0)
    for a, b in before:
        if b not in after[a]:
            after[a].add(b)
            waiting[b] += 1
    free = [(key(item), n, item) for n, item in enumerate(items) if not waiting[item]]
    heapq.heapify(free)
    index = {item: n for n, item in enumerate(items)}
    result = []
    while free:
        *_, item = heapq.heappop(free)
        result.append(item)
        for nxt in after[item]:
            waiting[nxt] -= 1
            if not waiting[nxt]:
                heapq.heappush(free, (key(nxt), index[nxt], nxt))
    if len(result) != len(items):
        raise ValueError("the constraints form a cycle")
    return result


class _Groups:
    """Union-find: which group each concept is in."""

    def __init__(self, items):
        self.parent = {item: item for item in items}

    def find(self, item):
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return self.parent[item]

    def join(self, a, b):
        self.parent[self.find(a)] = self.find(b)

    def members(self, items) -> dict:
        groups = defaultdict(list)
        for item in items:
            groups[self.find(item)].append(item)
        return groups


def _even_split(concepts: list, limit: int) -> list[tuple]:
    count = math.ceil(len(concepts) / limit)
    size, extra = divmod(len(concepts), count)
    parts, start = [], 0
    for n in range(count):
        end = start + size + (1 if n < extra else 0)
        parts.append(tuple(concepts[start:end]))
        start = end
    return parts


def build(nodes: Iterable[Node], links: Iterable[Link]) -> Roadmap:
    """The roadmap of these concepts and relationships."""
    by_id = {node.id: node for node in nodes}
    ids = sorted(by_id, key=lambda i: (by_id[i].position, by_id[i].normalized_name))

    def reading(i):
        return (by_id[i].position, by_id[i].normalized_name)

    def priority(i):
        return (-by_id[i].evidence, *reading(i))

    links = sorted(
        {
            link
            for link in links
            if link.source in by_id
            and link.target in by_id
            and link.source != link.target
        },
        key=lambda link: (reading(link.source), reading(link.target), link.kind),
    )
    prerequisites = [(x.source, x.target) for x in links if x.kind == "PREREQUISITE_OF"]

    # 1. Cycles.
    loops = [c for c in strong_components(ids, prerequisites) if len(c) > 1]
    loop_of = {i: n for n, loop in enumerate(loops) for i in loop}
    cycles = tuple(
        Cycle(
            concepts=tuple(loop),
            links=tuple((a, b) for a, b in prerequisites if a in loop and b in loop),
        )
        for loop in loops
    )

    # 2. Stages: groups within each concept's home document.
    groups = _Groups(ids)
    for link in links:
        if by_id[link.source].home == by_id[link.target].home:
            groups.join(link.source, link.target)
    for loop in loops:
        for i in loop[1:]:
            groups.join(loop[0], i)
    sizes = defaultdict(int)
    for i in ids:
        sizes[groups.find(i)] += 1
    by_home = defaultdict(list)
    for i in ids:
        by_home[by_id[i].home].append(i)
    for in_document in by_home.values():
        settled = [i for i in in_document if sizes[groups.find(i)] > 1]
        alone = [i for i in in_document if sizes[groups.find(i)] == 1]
        for i in alone:
            earlier = [s for s in settled if reading(s) < reading(i)]
            later = [s for s in settled if reading(s) > reading(i)]
            if earlier or later:
                groups.join(i, earlier[-1] if earlier else later[0])
            else:  # nothing in the document is related: it is one stage
                groups.join(i, alone[0])

    # 3. Stage order; groups whose prerequisites loop are merged first.
    def group_links():
        return {
            (groups.find(a), groups.find(b))
            for a, b in prerequisites
            if groups.find(a) != groups.find(b)
        }

    heads = list(dict.fromkeys(groups.find(i) for i in ids))
    for loop in strong_components(heads, group_links()):
        for head in loop[1:]:
            groups.join(loop[0], head)
    members = groups.members(ids)
    stage_order = ordered(
        list(members),
        group_links(),
        key=lambda head: min(reading(i) for i in members[head]),
    )

    # 4. Order within each stage.
    stages = []
    for head in stage_order:
        inside = members[head]
        chosen = set(inside)
        before = {
            (a, b)
            for a, b in prerequisites
            if a in chosen
            and b in chosen
            and not (a in loop_of and loop_of.get(b) == loop_of[a])
        }
        for loop in loops:
            if loop[0] in chosen:
                before.update(pairwise(loop))
        for link in links:
            if (
                link.kind != "PART_OF"
                or link.source not in chosen
                or link.target not in chosen
            ):
                continue
            whole, part = link.target, link.source
            after = defaultdict(set)
            for a, b in before:
                after[a].add(b)
            if whole not in _reachable(after, part):  # no prerequisite says otherwise
                before.add((whole, part))
        in_order = ordered(inside, before, key=priority)
        # 5. Size.
        stages.extend(
            _even_split(in_order, MAX_STAGE)
            if len(in_order) > MAX_STAGE
            else [tuple(in_order)]
        )
    return Roadmap(stages=tuple(stages), cycles=cycles)


def stage_key(stage: Sequence[uuid.UUID], nodes: dict[uuid.UUID, Node]) -> str:
    """A stage as the model sees it: its concepts' names and definitions, in
    order. The same key means the same question, so the same title."""
    text = "\n".join(
        f"{nodes[i].normalized_name}\t{nodes[i].definition}" for i in stage
    )
    return hashlib.sha256(text.encode()).hexdigest()


def plain_title(names: Sequence[str]) -> str:
    """A stage's title when the model has not written one."""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{names[0]} and {len(names) - 1} more"
