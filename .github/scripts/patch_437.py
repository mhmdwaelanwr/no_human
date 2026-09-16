from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVIEWER = ROOT / "src/no_human/review/reviewer.py"
TESTS = ROOT / "tests/test_diff_coverage.py"
MODULE = ROOT / "src/no_human/review/diff_coverage.py"


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one match, found {count}: {old[:120]!r}")
    return text.replace(old, new, 1)


reviewer = REVIEWER.read_text(encoding="utf-8")

reviewer = replace_once(
    reviewer,
    "from ..core.task import Task\n",
    "from ..core.task import Task\nfrom .diff_coverage import DiffCoverageError, budget_diff\n",
)

reviewer = replace_once(
    reviewer,
    'def _git_diff(repo_path: Path, before: str = "HEAD~1", after: str = "HEAD") -> tuple[str, int]:\n',
    'def _git_diff(repo_path: Path, before: str = "HEAD~1", after: str = "HEAD") -> tuple[str, int, list[str]]:\n',
)

reviewer = replace_once(
    reviewer,
    '    raw = proc.stdout or ""\n    return raw[:_DIFF_CAP], len(raw)\n',
    '    raw = proc.stdout or ""\n'
    '    try:\n'
    '        rendered, cut_paths = budget_diff(raw, _DIFF_CAP)\n'
    '    except DiffCoverageError as exc:\n'
    '        raise ReviewerUnavailable(f"review diff coverage unavailable: {exc}") from exc\n'
    '    return rendered, len(raw), cut_paths\n',
)

reviewer = replace_once(
    reviewer,
    '        diff, total = _git_diff(lpath, lbefore, "HEAD")\n',
    '        diff, total, _cut_paths = _git_diff(lpath, lbefore, "HEAD")\n',
)

reviewer = replace_once(
    reviewer,
    '        full_files, omitted_files = "", []\n        lint_evidence = ""\n',
    '        full_files, omitted_files = "", []\n        cut_paths: list[str] = []\n        lint_evidence = ""\n',
)

reviewer = replace_once(
    reviewer,
    '            diff, diff_total_len = _git_diff(repo_path, before_ref, after_ref)\n',
    '            diff, diff_total_len, cut_paths = _git_diff(repo_path, before_ref, after_ref)\n',
)

reviewer = replace_once(
    reviewer,
    '                max_turns=self._tier_review_turns(task),\n                extra_repos=linked_repos or None,\n            )\n',
    '                max_turns=self._tier_review_turns(task),\n'
    '                extra_repos=linked_repos or None,\n'
    '                required_inspections=cut_paths,\n'
    '            )\n',
)

reviewer = replace_once(
    reviewer,
    '        before_ref: str = "HEAD~1", verify_citations: bool = True,\n'
    '        extra_repos: list[tuple[Path, str]] | None = None,\n'
    '    ) -> ReviewDecision:\n',
    '        before_ref: str = "HEAD~1", verify_citations: bool = True,\n'
    '        extra_repos: list[tuple[Path, str]] | None = None,\n'
    '        required_inspections: list[str] | None = None,\n'
    '    ) -> ReviewDecision:\n',
)

reviewer = replace_once(
    reviewer,
    '                before_ref=before_ref, verify_citations=verify_citations,\n'
    '                extra_repos=extra_repos,\n'
    '            )\n',
    '                before_ref=before_ref, verify_citations=verify_citations,\n'
    '                extra_repos=extra_repos,\n'
    '                required_inspections=required_inspections,\n'
    '            )\n',
)

reviewer = replace_once(
    reviewer,
    '        before_ref: str = "HEAD~1", verify_citations: bool = True,\n'
    '        extra_repos: list[tuple[Path, str]] | None = None,\n'
    '    ) -> tuple[ReviewDecision | None, str, AgentResult | None]:\n',
    '        before_ref: str = "HEAD~1", verify_citations: bool = True,\n'
    '        extra_repos: list[tuple[Path, str]] | None = None,\n'
    '        required_inspections: list[str] | None = None,\n'
    '    ) -> tuple[ReviewDecision | None, str, AgentResult | None]:\n',
)

reviewer = replace_once(
    reviewer,
    '        all_text_parts: list[str] = []\n'
    '        original_on_event = self._on_event\n\n'
    '        def _capture_event(event):\n'
    '            if event.text:\n'
    '                all_text_parts.append(event.text)\n'
    '            if original_on_event:\n'
    '                original_on_event(event)\n',
    '        all_text_parts: list[str] = []\n'
    '        required = set(required_inspections or ())\n'
    '        inspected: set[str] = set()\n'
    '        original_on_event = self._on_event\n\n'
    '        def _capture_event(event):\n'
    '            if event.text:\n'
    '                all_text_parts.append(event.text)\n'
    '            if required and getattr(event, "kind", "") == "tool_use":\n'
    '                payload = getattr(event, "tool_input", None) or {}\n'
    '                stack = [payload]\n'
    '                while stack:\n'
    '                    value = stack.pop()\n'
    '                    if isinstance(value, dict):\n'
    '                        stack.extend(value.values())\n'
    '                    elif isinstance(value, (list, tuple, set)):\n'
    '                        stack.extend(value)\n'
    '                    elif isinstance(value, str):\n'
    '                        inspected.update(path for path in required if path in value)\n'
    '            if original_on_event:\n'
    '                original_on_event(event)\n',
)

reviewer = replace_once(
    reviewer,
    '        decision.output_tokens = getattr(result, "output_tokens", None)\n'
    '        return decision, "", result\n',
    '        decision.output_tokens = getattr(result, "output_tokens", None)\n'
    '        missing = sorted(required - inspected)\n'
    '        if missing:\n'
    '            return None, ("reviewer reached a verdict without inspecting truncated "\n'
    '                          f"changed file(s): {\", \".join(missing)}"), result\n'
    '        return decision, "", result\n',
)

REVIEWER.write_text(reviewer, encoding="utf-8")

MODULE.write_text('''"""Bound large gate diffs without letting path order hide changed files.

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
    "\\nDIFF COVERAGE — these changed-file patches were cut by the per-file "
    "budget. Inspect every listed path with read/search tools before reaching "
    "a verdict:\\n"
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
    newline = chunk.find("\\n")
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
    worst_note = _COVERAGE_NOTE + "".join(f"- {path}\\n" for path in required_paths)
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
    note = _COVERAGE_NOTE + "".join(f"- {path}\\n" for path in cut_paths)
    rendered = prefix[:prefix_budget] + "".join(
        chunk[:take] for chunk, take in zip(chunks, allocation)
    ) + note
    if len(rendered) > cap:
        raise DiffCoverageError("bounded diff exceeded its cap after rendering")
    return rendered, cut_paths
''', encoding="utf-8")

TESTS.write_text('''from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from no_human.agent.claude_backend import AgentEvent, AgentResult
from no_human.review.diff_coverage import DiffCoverageError, budget_diff
from no_human.review.reviewer import (
    AdversarialReviewer,
    ReviewerUnavailable,
    _DIFF_CAP,
    _git_diff,
)


def _chunk(path: str, body: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\\n"
        f"--- a/{path}\\n"
        f"+++ b/{path}\\n"
        "@@ -1 +1 @@\\n-old\\n+" + body + "\\n"
    )


def _passing_block() -> str:
    return (
        "REVIEW_JSON_START\\n"
        '{"passed": true, "items": [{"label": "ok", "passed": true, '
        '"severity": "low", "evidence": "covered"}]}\\n'
        "REVIEW_JSON_END\\n"
    )


def test_small_diff_is_byte_identical():
    raw = _chunk("a.py", "new")
    rendered, cut = budget_diff(raw, len(raw) + 10)
    assert rendered == raw
    assert cut == []


def test_large_diff_gives_every_file_a_patch_share_and_names_cut_paths():
    raw = "stat header\\n" + _chunk("a.py", "A" * 4000) + _chunk(
        "tests/test_a.py", "B" * 4000
    ) + _chunk("z.py", "C" * 4000)
    rendered, cut = budget_diff(raw, 2500)

    assert len(rendered) <= 2500
    assert "diff --git a/a.py b/a.py" in rendered
    assert "diff --git a/tests/test_a.py b/tests/test_a.py" in rendered
    assert "diff --git a/z.py b/z.py" in rendered
    assert cut
    for path in cut:
        assert f"- {path}\\n" in rendered


def test_impossible_file_count_fails_instead_of_second_level_truncation():
    raw = "".join(_chunk(f"very-long-file-name-{i:03d}.py", "x") for i in range(40))
    with pytest.raises(DiffCoverageError):
        budget_diff(raw, 700)


def _commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", message], check=True)


def test_git_diff_integration_keeps_late_paths_visible(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    for path in ("a.py", "tests/test_a.py", "z.py"):
        p = repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("old\\n")
    _commit(repo, "base")
    for path, char in (("a.py", "A"), ("tests/test_a.py", "B"), ("z.py", "C")):
        (repo / path).write_text(char * (_DIFF_CAP // 2) + "\\n")
    _commit(repo, "large change")

    rendered, total, cut = _git_diff(repo)
    assert total > _DIFF_CAP
    assert len(rendered) <= _DIFF_CAP
    assert "diff --git a/a.py b/a.py" in rendered
    assert "diff --git a/tests/test_a.py b/tests/test_a.py" in rendered
    assert "diff --git a/z.py b/z.py" in rendered
    assert cut


class _CoverageBackend:
    model = "test"

    def __init__(self, inspect: bool):
        self.inspect = inspect
        self.calls = 0

    async def run(self, prompt, *, cwd, max_turns, effort=None, on_event=None, **kwargs):
        self.calls += 1
        if self.inspect and on_event is not None:
            on_event(AgentEvent(
                "tool_use",
                tool_name="Read",
                tool_input={"file_path": "tests/hidden.py"},
            ))
        return AgentResult(
            final_text=_passing_block(),
            num_turns=1,
            is_error=False,
            tokens_used=10,
            session_id="coverage",
            stop_reason="end_turn",
        )


@pytest.mark.asyncio
async def test_uninspected_cut_file_routes_through_reviewer_unavailable(tmp_path):
    backend = _CoverageBackend(inspect=False)
    reviewer = AdversarialReviewer(backend=backend, timeout=1)
    with pytest.raises(ReviewerUnavailable):
        await reviewer._agent_review(
            "prompt", tmp_path, max_turns=1,
            required_inspections=["tests/hidden.py"],
        )
    assert backend.calls == 2


@pytest.mark.asyncio
async def test_inspected_cut_file_allows_the_real_verdict(tmp_path):
    backend = _CoverageBackend(inspect=True)
    reviewer = AdversarialReviewer(backend=backend, timeout=1)
    decision = await reviewer._agent_review(
        "prompt", tmp_path, max_turns=1,
        required_inspections=["tests/hidden.py"],
    )
    assert decision.passed is True
    assert backend.calls == 1
''', encoding="utf-8")

print("issue 437 patch applied")
