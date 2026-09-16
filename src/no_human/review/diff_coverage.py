"""Bound large gate diffs without letting path order hide changed files.

The trusted exclusion set is intentionally empty. If exclusions are ever added,
they must live in this module (reviewer-owned code), never in target-repository
configuration that the code under review can edit.
"""

from __future__ import annotations

import ast
import re
import shlex


TRUSTED_COVERAGE_EXCLUSIONS: frozenset[str] = frozenset()
_COVERAGE_NOTE = (
    "\nDIFF COVERAGE — these changed-file patches were cut by the per-file "
    "budget. Inspect every listed path with read/search tools before reaching "
    "a verdict:\n"
)
_MAX_PREFIX_CHARS = 2_000


class DiffCoverageError(RuntimeError):
    """The capped representation cannot honestly expose every changed file."""


def _unquote_path(token: str) -> str:
    token = token.strip()
    if token.startswith('"'):
        try:
            token = ast.literal_eval(token)
        except (SyntaxError, ValueError):
            token = token.strip('"')
    if token.startswith(("a/", "b/")):
        token = token[2:]
    return token


def _patch_path(chunk: str) -> str:
    for line in chunk.splitlines():
        if line.startswith("rename to "):
            return _unquote_path(line[len("rename to "):])
        if line.startswith("+++ "):
            candidate = line[4:].strip()
            if candidate != "/dev/null":
                return _unquote_path(candidate)
    for line in chunk.splitlines():
        if line.startswith("--- "):
            candidate = line[4:].strip()
            if candidate != "/dev/null":
                return _unquote_path(candidate)
    first = chunk.splitlines()[0] if chunk else ""
    try:
        parts = shlex.split(first)
    except ValueError:
        parts = []
    if len(parts) >= 4 and parts[:2] == ["diff", "--git"]:
        return _unquote_path(parts[3])
    raise DiffCoverageError("could not identify a changed path from a patch header")


def _split(raw: str) -> tuple[str, list[str]]:
    starts = [m.start() for m in re.finditer(r"(?m)^diff --git ", raw)]
    if not starts:
        raise DiffCoverageError("large diff has no per-file patch boundaries")
    prefix = raw[:starts[0]]
    chunks = [
        raw[start:(starts[i + 1] if i + 1 < len(starts) else len(raw))]
        for i, start in enumerate(starts)
    ]
    return prefix, chunks


def _header_len(chunk: str) -> int:
    newline = chunk.find("\n")
    return len(chunk) if newline < 0 else newline + 1


def _allocate(chunks: list[str], budget: int) -> list[int]:
    allocation = [_header_len(chunk) for chunk in chunks]
    minimum = sum(allocation)
    if minimum > budget:
        raise DiffCoverageError(
            f"{len(chunks)} changed files need {minimum:,} chars just for patch headers, "
            f"but only {budget:,} are available"
        )

    remaining = budget - minimum
    active = {i for i, chunk in enumerate(chunks) if allocation[i] < len(chunk)}
    while active and remaining:
        share = max(1, remaining // len(active))
        progressed = False
        for i in list(active):
            need = len(chunks[i]) - allocation[i]
            grant = min(need, share, remaining)
            if grant:
                allocation[i] += grant
                remaining -= grant
                progressed = True
            if allocation[i] == len(chunks[i]):
                active.remove(i)
            if remaining == 0:
                break
        if not progressed:
            break
    return allocation


def budget_diff(raw: str, cap: int) -> tuple[str, list[str]]:
    """Return small diffs unchanged; fairly bound oversized diffs by file.

    Every changed file keeps at least its ``diff --git`` header. Remaining
    space is shared across incomplete patches. Paths whose patch content is cut
    are appended to the rendered diff, so the caller can require explicit tool
    inspection before accepting any verdict.
    """
    if len(raw) <= cap:
        return raw, []
    if cap <= 0:
        raise DiffCoverageError("diff cap must be positive")

    prefix, chunks = _split(raw)
    paths = [_patch_path(chunk) for chunk in chunks]
    required_paths = [p for p in paths if p not in TRUSTED_COVERAGE_EXCLUSIONS]

    # Reserve the worst-case ledger first; doing so guarantees the final output
    # never has to hide a path merely because the note itself did not fit.
    worst_note = _COVERAGE_NOTE + "".join(f"- {path}\n" for path in required_paths)
    header_total = sum(_header_len(chunk) for chunk in chunks)
    prefix_budget = min(len(prefix), _MAX_PREFIX_CHARS)
    available = cap - len(worst_note) - prefix_budget
    if available < header_total:
        prefix_budget = max(0, cap - len(worst_note) - header_total)
        available = cap - len(worst_note) - prefix_budget
    if available < header_total:
        raise DiffCoverageError(
            f"{len(chunks)} changed files cannot all expose their patch headers "
            f"and coverage ledger within {cap:,} chars"
        )

    allocation = _allocate(chunks, available)
    cut_paths = [
        path for path, chunk, take in zip(paths, chunks, allocation)
        if take < len(chunk) and path not in TRUSTED_COVERAGE_EXCLUSIONS
    ]
    note = _COVERAGE_NOTE + "".join(f"- {path}\n" for path in cut_paths)
    rendered = prefix[:prefix_budget] + "".join(
        chunk[:take] for chunk, take in zip(chunks, allocation)
    ) + note
    if len(rendered) > cap:
        raise DiffCoverageError("bounded diff exceeded its cap after rendering")
    return rendered, cut_paths
