"""Tests for JSON and Markdown formatters."""
from __future__ import annotations

import dataclasses
import json

import pytest

from ghlens.formatters import get_formatter
from ghlens.formatters.json_fmt import format_json
from ghlens.formatters.markdown_fmt import format_markdown

from .conftest import make_conv_comment, make_pull_request, make_review_comment


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------


class TestJsonFormatter:
    def test_empty_list_returns_empty_array(self):
        assert format_json([]) == "[]"

    def test_output_is_valid_json(self):
        pr = make_pull_request()
        result = format_json([pr])
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 1

    def test_pr_fields_are_present(self):
        pr = make_pull_request(number=42, title="My PR", author="bob", state="OPEN")
        parsed = json.loads(format_json([pr]))
        item = parsed[0]
        assert item["number"] == 42
        assert item["title"] == "My PR"
        assert item["author"] == "bob"
        assert item["state"] == "OPEN"

    def test_author_none_serializes_as_null(self):
        pr = make_pull_request(author=None)
        parsed = json.loads(format_json([pr]))
        assert parsed[0]["author"] is None

    def test_merged_at_none_serializes_as_null(self):
        pr = make_pull_request(merged_at=None, state="OPEN")
        parsed = json.loads(format_json([pr]))
        assert parsed[0]["merged_at"] is None

    def test_labels_serialized_as_list(self):
        pr = make_pull_request(labels=["bug", "performance"])
        parsed = json.loads(format_json([pr]))
        assert parsed[0]["labels"] == ["bug", "performance"]

    def test_comments_nested_in_output(self):
        comment = make_conv_comment(id="C1", body="LGTM")
        pr = make_pull_request(comments=[comment])
        parsed = json.loads(format_json([pr]))
        assert len(parsed[0]["comments"]) == 1
        assert parsed[0]["comments"][0]["body"] == "LGTM"
        assert parsed[0]["comments"][0]["id"] == "C1"

    def test_review_comments_nested_in_output(self):
        rc = make_review_comment(id="RC1", path="main.py", line=7)
        pr = make_pull_request(review_comments=[rc])
        parsed = json.loads(format_json([pr]))
        rc_out = parsed[0]["review_comments"][0]
        assert rc_out["id"] == "RC1"
        assert rc_out["path"] == "main.py"
        assert rc_out["line"] == 7

    def test_multiple_prs_in_output(self):
        prs = [make_pull_request(number=i, title=f"PR {i}") for i in range(3)]
        parsed = json.loads(format_json(prs))
        assert len(parsed) == 3
        assert [p["number"] for p in parsed] == [0, 1, 2]

    def test_output_matches_dataclasses_asdict(self):
        comment = make_conv_comment()
        rc = make_review_comment()
        pr = make_pull_request(comments=[comment], review_comments=[rc])
        expected = json.dumps([dataclasses.asdict(pr)], indent=2)
        assert format_json([pr]) == expected

    def test_get_formatter_returns_json_callable(self):
        formatter = get_formatter("json")
        pr = make_pull_request()
        result = formatter([pr])
        assert json.loads(result)[0]["number"] == pr.number

    def test_get_formatter_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown format"):
            get_formatter("xml")


# ---------------------------------------------------------------------------
# Markdown formatter
# ---------------------------------------------------------------------------


class TestMarkdownFormatter:
    def test_title_includes_owner_repo(self):
        pr = make_pull_request()
        result = format_markdown([pr], owner_repo="myorg/myrepo")
        assert "# Pull Requests: myorg/myrepo" in result

    def test_title_without_owner_repo(self):
        pr = make_pull_request()
        result = format_markdown([pr], owner_repo="")
        assert result.startswith("# Pull Requests\n")

    def test_pr_heading_includes_number_and_title(self):
        pr = make_pull_request(number=99, title="Add feature")
        result = format_markdown([pr])
        assert "## PR #99 — Add feature" in result

    def test_metadata_table_contains_key_fields(self):
        pr = make_pull_request(
            author="alice",
            state="MERGED",
            created_at="2024-01-01T00:00:00Z",
            additions=10,
            deletions=5,
            changed_files=3,
        )
        result = format_markdown([pr])
        assert "| Author | alice |" in result
        assert "| State | MERGED |" in result
        assert "| Additions | 10 |" in result
        assert "| Deletions | 5 |" in result
        assert "| Changed Files | 3 |" in result

    def test_merged_at_row_present_when_set(self):
        pr = make_pull_request(merged_at="2024-01-02T00:00:00Z")
        result = format_markdown([pr])
        assert "| Merged |" in result

    def test_merged_at_row_absent_when_none(self):
        pr = make_pull_request(merged_at=None, state="OPEN")
        result = format_markdown([pr])
        assert "| Merged |" not in result

    def test_labels_row_present_when_set(self):
        pr = make_pull_request(labels=["bug", "perf"])
        result = format_markdown([pr])
        assert "| Labels | bug, perf |" in result

    def test_labels_row_absent_when_empty(self):
        pr = make_pull_request(labels=[])
        result = format_markdown([pr])
        assert "| Labels |" not in result

    def test_author_none_shown_as_ghost(self):
        pr = make_pull_request(author=None)
        result = format_markdown([pr])
        assert "| Author | ghost |" in result

    def test_conversational_comments_section(self):
        comment = make_conv_comment(author="bob", body="Please fix this", created_at="2024-01-01T10:00:00Z")
        pr = make_pull_request(comments=[comment])
        result = format_markdown([pr])
        assert "### Conversational Comments (1)" in result
        assert "#### Comment by @bob" in result
        assert "Please fix this" in result

    def test_no_comments_section_when_empty(self):
        pr = make_pull_request(comments=[])
        result = format_markdown([pr])
        assert "Conversational Comments" not in result

    def test_review_comments_section(self):
        rc = make_review_comment(
            author="carol",
            body="Consider caching",
            path="src/cache.py",
            line=15,
            diff_hunk="@@ -10,6 +10,8 @@\n ctx\n+cache",
        )
        pr = make_pull_request(review_comments=[rc])
        result = format_markdown([pr])
        assert "### Code Review Comments (1)" in result
        assert "#### Review Comment by @carol" in result
        assert "**File:** `src/cache.py`" in result
        assert "**Line:** 15" in result
        assert "```diff" in result
        assert "@@ -10,6 +10,8 @@" in result
        assert "Consider caching" in result

    def test_no_review_comments_section_when_empty(self):
        pr = make_pull_request(review_comments=[])
        result = format_markdown([pr])
        assert "Code Review Comments" not in result

    def test_review_comment_null_line_omits_line_field(self):
        rc = make_review_comment(line=None)
        pr = make_pull_request(review_comments=[rc])
        result = format_markdown([pr])
        assert "**Line:**" not in result

    def test_review_comment_author_none_shown_as_ghost(self):
        rc = make_review_comment(author=None)
        pr = make_pull_request(review_comments=[rc])
        result = format_markdown([pr])
        assert "#### Review Comment by @ghost" in result

    def test_state_label_uniform_state(self):
        prs = [make_pull_request(state="MERGED"), make_pull_request(number=2, state="MERGED")]
        result = format_markdown(prs)
        assert "State: MERGED" in result

    def test_state_label_mixed_states_shows_all(self):
        prs = [make_pull_request(state="OPEN"), make_pull_request(number=2, state="MERGED")]
        result = format_markdown(prs)
        assert "State: ALL" in result

    def test_fetched_count_in_header(self):
        prs = [make_pull_request(number=i) for i in range(5)]
        result = format_markdown(prs)
        assert "Fetched 5 PRs" in result

    def test_get_formatter_markdown_with_owner_repo(self):
        pr = make_pull_request()
        formatter = get_formatter("markdown", owner_repo="acme/widget")
        result = formatter([pr])
        assert "# Pull Requests: acme/widget" in result

    def test_multiple_prs_all_have_headings(self):
        prs = [make_pull_request(number=i, title=f"PR {i}") for i in range(3)]
        result = format_markdown(prs)
        for i in range(3):
            assert f"## PR #{i} — PR {i}" in result
