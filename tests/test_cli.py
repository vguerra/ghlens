"""Tests for the Click CLI (ghlens fetch)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from ghlens.cli import cli
from ghlens.errors import AuthError, RateLimitError, RepoNotFoundError

from .conftest import make_conv_comment, make_pull_request, make_review_comment


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def sample_pr():
    return make_pull_request(
        number=1,
        title="Fix bug",
        author="alice",
        labels=["bug"],
        comments=[make_conv_comment()],
        review_comments=[make_review_comment()],
    )


@pytest.fixture
def mock_client(mocker, sample_pr):
    """Patch GitHubClient so fetch_prs yields sample_pr."""
    mock_instance = MagicMock()
    mock_instance.__enter__ = MagicMock(return_value=mock_instance)
    mock_instance.__exit__ = MagicMock(return_value=False)
    mock_instance.fetch_prs.return_value = iter([sample_pr])
    mocker.patch("ghlens.cli.GitHubClient", return_value=mock_instance)
    return mock_instance


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestRepoArgValidation:
    def test_missing_slash_exits_nonzero(self, runner):
        result = runner.invoke(cli, ["fetch", "notaslash"], env={"GITHUB_TOKEN": "tok"})
        assert result.exit_code != 0
        assert "OWNER/REPO" in result.output

    def test_empty_owner_exits_nonzero(self, runner):
        result = runner.invoke(cli, ["fetch", "/repo"], env={"GITHUB_TOKEN": "tok"})
        assert result.exit_code != 0

    def test_empty_repo_name_exits_nonzero(self, runner):
        result = runner.invoke(cli, ["fetch", "owner/"], env={"GITHUB_TOKEN": "tok"})
        assert result.exit_code != 0

    def test_multiple_slashes_exits_nonzero(self, runner):
        result = runner.invoke(cli, ["fetch", "a/b/c"], env={"GITHUB_TOKEN": "tok"})
        assert result.exit_code != 0

    def test_invalid_state_choice_exits_nonzero(self, runner):
        result = runner.invoke(
            cli, ["fetch", "owner/repo", "--state", "DRAFT"], env={"GITHUB_TOKEN": "tok"}
        )
        assert result.exit_code != 0

    def test_invalid_format_choice_exits_nonzero(self, runner):
        result = runner.invoke(
            cli, ["fetch", "owner/repo", "--format", "csv"], env={"GITHUB_TOKEN": "tok"}
        )
        assert result.exit_code != 0

    def test_limit_zero_exits_nonzero(self, runner):
        result = runner.invoke(
            cli, ["fetch", "owner/repo", "--limit", "0"], env={"GITHUB_TOKEN": "tok"}
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Token handling
# ---------------------------------------------------------------------------


class TestTokenHandling:
    def test_missing_token_exits_1(self, runner, mocker):
        mocker.patch.dict(os.environ, {}, clear=True)
        result = runner.invoke(cli, ["fetch", "owner/repo"])
        assert result.exit_code == 1
        assert "GITHUB_TOKEN" in result.output

    def test_empty_string_token_exits_1(self, runner):
        result = runner.invoke(cli, ["fetch", "owner/repo"], env={"GITHUB_TOKEN": ""})
        assert result.exit_code == 1
        assert "GITHUB_TOKEN" in result.output


# ---------------------------------------------------------------------------
# Successful fetch — JSON output
# ---------------------------------------------------------------------------


class TestFetchJson:
    def test_exits_0_on_success(self, runner, mock_client):
        result = runner.invoke(
            cli, ["fetch", "owner/repo"], env={"GITHUB_TOKEN": "tok"}
        )
        assert result.exit_code == 0

    def test_stdout_is_valid_json(self, runner, mock_client):
        result = runner.invoke(
            cli, ["fetch", "owner/repo"], env={"GITHUB_TOKEN": "tok"}
        )
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)

    def test_json_contains_pr_fields(self, runner, mock_client, sample_pr):
        result = runner.invoke(
            cli, ["fetch", "owner/repo"], env={"GITHUB_TOKEN": "tok"}
        )
        parsed = json.loads(result.output)
        assert parsed[0]["number"] == sample_pr.number
        assert parsed[0]["title"] == sample_pr.title
        assert parsed[0]["author"] == sample_pr.author

    def test_passes_limit_to_client(self, runner, mock_client):
        runner.invoke(
            cli, ["fetch", "owner/repo", "--limit", "7"], env={"GITHUB_TOKEN": "tok"}
        )
        assert mock_client.fetch_prs.call_args.args[3] == 7

    def test_passes_state_to_client(self, runner, mock_client):
        runner.invoke(
            cli, ["fetch", "owner/repo", "--state", "OPEN"], env={"GITHUB_TOKEN": "tok"}
        )
        call_args = mock_client.fetch_prs.call_args[0]
        assert "OPEN" in call_args[2]  # states positional arg

    def test_all_state_passes_three_states(self, runner, mock_client):
        runner.invoke(
            cli, ["fetch", "owner/repo", "--state", "ALL"], env={"GITHUB_TOKEN": "tok"}
        )
        call_args = mock_client.fetch_prs.call_args[0]
        assert set(call_args[2]) == {"OPEN", "CLOSED", "MERGED"}

    def test_single_label_passed_to_client(self, runner, mock_client):
        runner.invoke(
            cli, ["fetch", "owner/repo", "--label", "bug"], env={"GITHUB_TOKEN": "tok"}
        )
        assert mock_client.fetch_prs.call_args.kwargs["labels"] == ["bug"]

    def test_multiple_labels_passed_to_client(self, runner, mock_client):
        runner.invoke(
            cli,
            ["fetch", "owner/repo", "--label", "bug", "--label", "enhancement"],
            env={"GITHUB_TOKEN": "tok"},
        )
        assert mock_client.fetch_prs.call_args.kwargs["labels"] == ["bug", "enhancement"]

    def test_no_label_passes_none_to_client(self, runner, mock_client):
        runner.invoke(
            cli, ["fetch", "owner/repo"], env={"GITHUB_TOKEN": "tok"}
        )
        assert mock_client.fetch_prs.call_args.kwargs["labels"] is None


# ---------------------------------------------------------------------------
# Successful fetch — Markdown output
# ---------------------------------------------------------------------------


class TestFetchMarkdown:
    def test_markdown_output_contains_pr_heading(self, runner, mock_client, sample_pr):
        result = runner.invoke(
            cli, ["fetch", "owner/repo", "--format", "markdown"], env={"GITHUB_TOKEN": "tok"}
        )
        assert result.exit_code == 0
        assert f"## PR #{sample_pr.number}" in result.output

    def test_markdown_output_contains_repo_in_title(self, runner, mock_client):
        result = runner.invoke(
            cli, ["fetch", "owner/repo", "--format", "markdown"], env={"GITHUB_TOKEN": "tok"}
        )
        assert "owner/repo" in result.output


# ---------------------------------------------------------------------------
# Output to file
# ---------------------------------------------------------------------------


class TestOutputToFile:
    def test_writes_file_and_exits_0(self, runner, mock_client, tmp_path):
        out = tmp_path / "prs.json"
        result = runner.invoke(
            cli,
            ["fetch", "owner/repo", "--output", str(out)],
            env={"GITHUB_TOKEN": "tok"},
        )
        assert result.exit_code == 0
        assert out.exists()

    def test_file_contains_valid_json(self, runner, mock_client, tmp_path):
        out = tmp_path / "prs.json"
        runner.invoke(
            cli,
            ["fetch", "owner/repo", "--output", str(out)],
            env={"GITHUB_TOKEN": "tok"},
        )
        parsed = json.loads(out.read_text())
        assert isinstance(parsed, list)
        assert len(parsed) == 1

    def test_stdout_does_not_contain_json_when_writing_to_file(self, runner, mock_client, tmp_path):
        out = tmp_path / "prs.json"
        result = runner.invoke(
            cli,
            ["fetch", "owner/repo", "--output", str(out)],
            env={"GITHUB_TOKEN": "tok"},
        )
        assert result.exit_code == 0
        # The JSON payload goes to the file, not stdout
        assert not result.output.strip().startswith("[")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_ghlens_error_exits_1(self, runner, mocker):
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.fetch_prs.side_effect = AuthError("Bad token")
        mocker.patch("ghlens.cli.GitHubClient", return_value=mock_instance)

        result = runner.invoke(cli, ["fetch", "owner/repo"], env={"GITHUB_TOKEN": "tok"})
        assert result.exit_code == 1

    def test_rate_limit_error_exits_1(self, runner, mocker):
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.fetch_prs.side_effect = RateLimitError("Rate limit hit")
        mocker.patch("ghlens.cli.GitHubClient", return_value=mock_instance)

        result = runner.invoke(cli, ["fetch", "owner/repo"], env={"GITHUB_TOKEN": "tok"})
        assert result.exit_code == 1

    def test_help_exits_0(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "fetch" in result.output

    def test_fetch_help_exits_0(self, runner):
        result = runner.invoke(cli, ["fetch", "--help"])
        assert result.exit_code == 0
        assert "OWNER/REPO" in result.output
        assert "--state" in result.output
        assert "--format" in result.output
        assert "--limit" in result.output
        assert "--output" in result.output


# ---------------------------------------------------------------------------
# pr subcommand
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_pr_client(mocker, sample_pr):
    """Patch GitHubClient so fetch_pr returns sample_pr."""
    mock_instance = MagicMock()
    mock_instance.__enter__ = MagicMock(return_value=mock_instance)
    mock_instance.__exit__ = MagicMock(return_value=False)
    mock_instance.fetch_pr.return_value = sample_pr
    mocker.patch("ghlens.cli.GitHubClient", return_value=mock_instance)
    return mock_instance


class TestPrCommand:
    def test_exits_0_on_success(self, runner, mock_pr_client):
        result = runner.invoke(cli, ["pr", "owner/repo", "1"], env={"GITHUB_TOKEN": "tok"})
        assert result.exit_code == 0

    def test_stdout_is_valid_json(self, runner, mock_pr_client):
        result = runner.invoke(cli, ["pr", "owner/repo", "1"], env={"GITHUB_TOKEN": "tok"})
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert len(parsed) == 1

    def test_pr_fields_present(self, runner, mock_pr_client, sample_pr):
        result = runner.invoke(cli, ["pr", "owner/repo", "1"], env={"GITHUB_TOKEN": "tok"})
        parsed = json.loads(result.output)
        assert parsed[0]["number"] == sample_pr.number
        assert parsed[0]["title"] == sample_pr.title

    def test_passes_number_to_client(self, runner, mock_pr_client):
        runner.invoke(cli, ["pr", "owner/repo", "42"], env={"GITHUB_TOKEN": "tok"})
        mock_pr_client.fetch_pr.assert_called_once_with("owner", "repo", 42)

    def test_pr_not_found_exits_1(self, runner, mocker):
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.fetch_pr.side_effect = RepoNotFoundError("PR #99 not found")
        mocker.patch("ghlens.cli.GitHubClient", return_value=mock_instance)

        result = runner.invoke(cli, ["pr", "owner/repo", "99"], env={"GITHUB_TOKEN": "tok"})
        assert result.exit_code == 1

    def test_markdown_format(self, runner, mock_pr_client, sample_pr):
        result = runner.invoke(
            cli, ["pr", "owner/repo", "1", "--format", "markdown"], env={"GITHUB_TOKEN": "tok"}
        )
        assert result.exit_code == 0
        assert f"## PR #{sample_pr.number}" in result.output

    def test_output_to_file(self, runner, mock_pr_client, tmp_path):
        out = tmp_path / "pr.json"
        result = runner.invoke(
            cli,
            ["pr", "owner/repo", "1", "--output", str(out)],
            env={"GITHUB_TOKEN": "tok"},
        )
        assert result.exit_code == 0
        assert out.exists()
        parsed = json.loads(out.read_text())
        assert isinstance(parsed, list)
        assert len(parsed) == 1
