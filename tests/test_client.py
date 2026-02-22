"""Tests for GitHubClient: execute(), fetch_prs(), and pagination helpers."""
from __future__ import annotations

import json

import httpx
import pytest

from ghlens.client import GitHubClient
from ghlens.errors import ApiError, AuthError, NetworkError, RateLimitError, RepoNotFoundError

from .conftest import (
    comment_node,
    comments_page_response,
    pr_by_number_response,
    pr_list_response,
    pr_node,
    review_comment_node,
    review_threads_page_response,
    thread_comments_page_response,
    thread_node,
)

GQL_URL = "https://api.github.com/graphql"

# A minimal successful response with no rate-limit pressure
_OK_DATA = {"data": {"rateLimit": {"cost": 1, "remaining": 4999, "resetAt": "2024-12-31T23:59:59Z"}}}


# ---------------------------------------------------------------------------
# execute()
# ---------------------------------------------------------------------------


class TestExecute:
    def test_happy_path_returns_data(self, respx_mock):
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=_OK_DATA))
        with GitHubClient("token") as client:
            result = client.execute("{ viewer { login } }")
        assert result["data"]["rateLimit"]["remaining"] == 4999

    def test_sends_auth_header(self, respx_mock):
        route = respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=_OK_DATA))
        with GitHubClient("mytoken") as client:
            client.execute("{ viewer { login } }")
        assert route.calls[0].request.headers["Authorization"] == "Bearer mytoken"

    def test_sends_api_version_header(self, respx_mock):
        route = respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=_OK_DATA))
        with GitHubClient("token") as client:
            client.execute("{ viewer { login } }")
        assert route.calls[0].request.headers["X-GitHub-Api-Version"] == "2022-11-28"

    def test_401_raises_auth_error(self, respx_mock):
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(401))
        with GitHubClient("bad") as client:
            with pytest.raises(AuthError):
                client.execute("{ viewer { login } }")

    def test_non_200_non_401_non_5xx_raises_api_error(self, respx_mock):
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(403, text="Forbidden"))
        with GitHubClient("token") as client:
            with pytest.raises(ApiError, match="403"):
                client.execute("{ viewer { login } }")

    def test_graphql_errors_array_raises_api_error(self, respx_mock):
        body = {"errors": [{"message": "Something went wrong", "type": "INTERNAL"}]}
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=body))
        with GitHubClient("token") as client:
            with pytest.raises(ApiError, match="Something went wrong"):
                client.execute("{ viewer { login } }")

    def test_graphql_not_found_raises_repo_not_found(self, respx_mock):
        body = {
            "errors": [
                {
                    "message": "Could not resolve to a Repository with the name 'x/y'.",
                    "type": "NOT_FOUND",
                }
            ]
        }
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=body))
        with GitHubClient("token") as client:
            with pytest.raises(RepoNotFoundError):
                client.execute("{ viewer { login } }")

    def test_rate_limit_exhausted_raises(self, respx_mock):
        body = {"data": {"rateLimit": {"cost": 1, "remaining": 0, "resetAt": "2024-12-31T23:59:59Z"}}}
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=body))
        with GitHubClient("token") as client:
            with pytest.raises(RateLimitError, match="exhausted"):
                client.execute("{ viewer { login } }")

    def test_rate_limit_low_does_not_raise(self, respx_mock):
        body = {"data": {"rateLimit": {"cost": 1, "remaining": 50, "resetAt": "2024-12-31T23:59:59Z"}}}
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=body))
        with GitHubClient("token") as client:
            result = client.execute("{ viewer { login } }")
        assert result["data"]["rateLimit"]["remaining"] == 50

    def test_5xx_retries_then_succeeds(self, respx_mock, mocker):
        mocker.patch("ghlens.client.time.sleep")
        call_count = 0

        def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return httpx.Response(503)
            return httpx.Response(200, json=_OK_DATA)

        respx_mock.post(GQL_URL).mock(side_effect=side_effect)
        with GitHubClient("token") as client:
            client.execute("{ viewer { login } }")
        assert call_count == 3

    def test_5xx_exhausts_all_retries_raises_network_error(self, respx_mock, mocker):
        mocker.patch("ghlens.client.time.sleep")
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(503))
        with GitHubClient("token") as client:
            with pytest.raises(NetworkError):
                client.execute("{ viewer { login } }")

    def test_timeout_retries_then_succeeds(self, respx_mock, mocker):
        mocker.patch("ghlens.client.time.sleep")
        call_count = 0

        def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("timed out", request=request)
            return httpx.Response(200, json=_OK_DATA)

        respx_mock.post(GQL_URL).mock(side_effect=side_effect)
        with GitHubClient("token") as client:
            client.execute("{ viewer { login } }")
        assert call_count == 2

    def test_timeout_exhausts_all_retries_raises_network_error(self, respx_mock, mocker):
        mocker.patch("ghlens.client.time.sleep")

        def always_timeout(request):
            raise httpx.TimeoutException("timed out", request=request)

        respx_mock.post(GQL_URL).mock(side_effect=always_timeout)
        with GitHubClient("token") as client:
            with pytest.raises(NetworkError):
                client.execute("{ viewer { login } }")

    def test_request_error_raises_network_error_immediately(self, respx_mock):
        respx_mock.post(GQL_URL).mock(side_effect=httpx.ConnectError("connection refused"))
        with GitHubClient("token") as client:
            with pytest.raises(NetworkError):
                client.execute("{ viewer { login } }")

    def test_retry_sleeps_with_backoff(self, respx_mock, mocker):
        sleep = mocker.patch("ghlens.client.time.sleep")
        call_count = 0

        def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                return httpx.Response(503)
            return httpx.Response(200, json=_OK_DATA)

        respx_mock.post(GQL_URL).mock(side_effect=side_effect)
        with GitHubClient("token") as client:
            client.execute("{ viewer { login } }")

        delays = [call.args[0] for call in sleep.call_args_list]
        assert delays == [1, 5, 15]


# ---------------------------------------------------------------------------
# fetch_prs()
# ---------------------------------------------------------------------------


class TestFetchPrs:
    def test_basic_single_pr(self, respx_mock):
        node = pr_node(number=1, title="Fix bug", labels=["bug"])
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=pr_list_response([node])))
        with GitHubClient("token") as client:
            prs = list(client.fetch_prs("owner", "repo", ["MERGED"]))
        assert len(prs) == 1
        pr = prs[0]
        assert pr.number == 1
        assert pr.title == "Fix bug"
        assert pr.labels == ["bug"]
        assert pr.author == "alice"
        assert pr.state == "MERGED"
        assert pr.additions == 10
        assert pr.deletions == 5
        assert pr.changed_files == 2

    def test_author_is_none_for_deleted_account(self, respx_mock):
        node = pr_node(author=None)
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=pr_list_response([node])))
        with GitHubClient("token") as client:
            prs = list(client.fetch_prs("owner", "repo", ["MERGED"]))
        assert prs[0].author is None

    def test_merged_at_none_for_open_pr(self, respx_mock):
        node = pr_node(state="OPEN", merged_at=None)
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=pr_list_response([node])))
        with GitHubClient("token") as client:
            prs = list(client.fetch_prs("owner", "repo", ["OPEN"]))
        assert prs[0].merged_at is None

    def test_inline_comments_are_parsed(self, respx_mock):
        node = pr_node(comment_nodes=[comment_node(id="C1", body="LGTM")])
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=pr_list_response([node])))
        with GitHubClient("token") as client:
            prs = list(client.fetch_prs("owner", "repo", ["MERGED"]))
        assert len(prs[0].comments) == 1
        assert prs[0].comments[0].body == "LGTM"
        assert prs[0].comments[0].id == "C1"

    def test_inline_review_thread_comments_are_flattened(self, respx_mock):
        rc = review_comment_node(id="RC1", path="main.py", line=10)
        thread = thread_node(id="T1", comment_nodes=[rc])
        node = pr_node(thread_nodes=[thread])
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=pr_list_response([node])))
        with GitHubClient("token") as client:
            prs = list(client.fetch_prs("owner", "repo", ["MERGED"]))
        assert len(prs[0].review_comments) == 1
        rc_result = prs[0].review_comments[0]
        assert rc_result.id == "RC1"
        assert rc_result.path == "main.py"
        assert rc_result.line == 10

    def test_limit_stops_after_n_prs(self, respx_mock):
        nodes = [pr_node(id=f"PR_{i}", number=i) for i in range(10)]
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=pr_list_response(nodes)))
        with GitHubClient("token") as client:
            prs = list(client.fetch_prs("owner", "repo", ["MERGED"], limit=3))
        assert len(prs) == 3

    def test_pagination_fetches_next_page(self, respx_mock):
        page1 = pr_list_response(
            [pr_node(id="PR_1", number=1)], has_next_page=True, end_cursor="cur1"
        )
        page2 = pr_list_response([pr_node(id="PR_2", number=2)], has_next_page=False)
        respx_mock.post(GQL_URL).mock(side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
        ])
        with GitHubClient("token") as client:
            prs = list(client.fetch_prs("owner", "repo", ["MERGED"]))
        assert [pr.number for pr in prs] == [1, 2]

    def test_pagination_sends_cursor_in_second_request(self, respx_mock):
        page1 = pr_list_response(
            [pr_node(id="PR_1", number=1)], has_next_page=True, end_cursor="abc123"
        )
        page2 = pr_list_response([pr_node(id="PR_2", number=2)])
        route = respx_mock.post(GQL_URL).mock(side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
        ])
        with GitHubClient("token") as client:
            list(client.fetch_prs("owner", "repo", ["MERGED"]))
        second_body = json.loads(route.calls[1].request.content)
        assert second_body["variables"]["after"] == "abc123"

    def test_all_states_omits_states_variable(self, respx_mock):
        route = respx_mock.post(GQL_URL).mock(
            return_value=httpx.Response(200, json=pr_list_response([pr_node()]))
        )
        with GitHubClient("token") as client:
            list(client.fetch_prs("owner", "repo", ["OPEN", "CLOSED", "MERGED"]))
        body = json.loads(route.calls[0].request.content)
        assert "states" not in body.get("variables", {})

    def test_filtered_state_sends_states_variable(self, respx_mock):
        route = respx_mock.post(GQL_URL).mock(
            return_value=httpx.Response(200, json=pr_list_response([pr_node()]))
        )
        with GitHubClient("token") as client:
            list(client.fetch_prs("owner", "repo", ["OPEN"]))
        body = json.loads(route.calls[0].request.content)
        assert body["variables"]["states"] == ["OPEN"]

    def test_repo_not_found_raises(self, respx_mock):
        body = {
            "data": {
                "rateLimit": {"cost": 1, "remaining": 4999, "resetAt": "x"},
                "repository": None,
            }
        }
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=body))
        with GitHubClient("token") as client:
            with pytest.raises(RepoNotFoundError):
                list(client.fetch_prs("owner", "nonexistent", ["MERGED"]))

    def test_limit_of_one_fetches_exactly_one_from_large_page(self, respx_mock):
        nodes = [pr_node(id=f"PR_{i}", number=i) for i in range(50)]
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=pr_list_response(nodes)))
        with GitHubClient("token") as client:
            prs = list(client.fetch_prs("owner", "repo", ["MERGED"], limit=1))
        assert len(prs) == 1

    def test_labels_variable_sent_when_specified(self, respx_mock):
        route = respx_mock.post(GQL_URL).mock(
            return_value=httpx.Response(200, json=pr_list_response([pr_node()]))
        )
        with GitHubClient("token") as client:
            list(client.fetch_prs("owner", "repo", ["MERGED"], labels=["bug"]))
        body = json.loads(route.calls[0].request.content)
        assert body["variables"]["labels"] == ["bug"]

    def test_no_labels_omits_labels_variable(self, respx_mock):
        route = respx_mock.post(GQL_URL).mock(
            return_value=httpx.Response(200, json=pr_list_response([pr_node()]))
        )
        with GitHubClient("token") as client:
            list(client.fetch_prs("owner", "repo", ["MERGED"]))
        body = json.loads(route.calls[0].request.content)
        assert "labels" not in body.get("variables", {})

    def test_multiple_labels_sent_as_list(self, respx_mock):
        route = respx_mock.post(GQL_URL).mock(
            return_value=httpx.Response(200, json=pr_list_response([pr_node()]))
        )
        with GitHubClient("token") as client:
            list(client.fetch_prs("owner", "repo", ["MERGED"], labels=["bug", "enhancement"]))
        body = json.loads(route.calls[0].request.content)
        assert body["variables"]["labels"] == ["bug", "enhancement"]


# ---------------------------------------------------------------------------
# Comment overflow pagination (_complete_comments)
# ---------------------------------------------------------------------------


class TestCompleteComments:
    def test_fetches_overflow_comments(self, respx_mock):
        inline = comment_node(id="C1", body="First")
        overflow = comment_node(id="C2", body="Second")
        node = pr_node(
            comment_nodes=[inline],
            comments_has_next=True,
            comments_cursor="cur1",
        )
        page1 = pr_list_response([node])
        page2 = comments_page_response([overflow], has_next_page=False)

        respx_mock.post(GQL_URL).mock(side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
        ])
        with GitHubClient("token") as client:
            prs = list(client.fetch_prs("owner", "repo", ["MERGED"]))

        assert len(prs[0].comments) == 2
        assert [c.id for c in prs[0].comments] == ["C1", "C2"]

    def test_multi_page_comment_overflow(self, respx_mock):
        inline = comment_node(id="C1")
        node = pr_node(comment_nodes=[inline], comments_has_next=True, comments_cursor="p1")
        page1 = pr_list_response([node])
        page2 = comments_page_response(
            [comment_node(id="C2")], has_next_page=True, end_cursor="p2"
        )
        page3 = comments_page_response([comment_node(id="C3")], has_next_page=False)

        respx_mock.post(GQL_URL).mock(side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
            httpx.Response(200, json=page3),
        ])
        with GitHubClient("token") as client:
            prs = list(client.fetch_prs("owner", "repo", ["MERGED"]))

        assert [c.id for c in prs[0].comments] == ["C1", "C2", "C3"]


# ---------------------------------------------------------------------------
# Review thread overflow pagination (_complete_review_threads / _flatten_threads)
# ---------------------------------------------------------------------------


class TestReviewThreadPagination:
    def test_fetches_overflow_review_threads(self, respx_mock):
        rc1 = review_comment_node(id="RC1")
        rc2 = review_comment_node(id="RC2")
        inline_thread = thread_node(id="T1", comment_nodes=[rc1])
        overflow_thread = thread_node(id="T2", comment_nodes=[rc2])

        node = pr_node(
            thread_nodes=[inline_thread],
            threads_has_next=True,
            threads_cursor="tcur1",
        )
        page1 = pr_list_response([node])
        page2 = review_threads_page_response([overflow_thread], has_next_page=False)

        respx_mock.post(GQL_URL).mock(side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
        ])
        with GitHubClient("token") as client:
            prs = list(client.fetch_prs("owner", "repo", ["MERGED"]))

        assert len(prs[0].review_comments) == 2
        assert {rc.id for rc in prs[0].review_comments} == {"RC1", "RC2"}

    def test_fetches_overflow_comments_within_thread(self, respx_mock):
        rc1 = review_comment_node(id="RC1")
        rc2 = review_comment_node(id="RC2")
        # Thread with inline comment that has overflow
        inline_thread = thread_node(
            id="T1",
            comment_nodes=[rc1],
            has_next_page=True,
            end_cursor="rcur1",
        )
        node = pr_node(thread_nodes=[inline_thread])
        page1 = pr_list_response([node])
        page2 = thread_comments_page_response([rc2], has_next_page=False)

        respx_mock.post(GQL_URL).mock(side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
        ])
        with GitHubClient("token") as client:
            prs = list(client.fetch_prs("owner", "repo", ["MERGED"]))

        assert [rc.id for rc in prs[0].review_comments] == ["RC1", "RC2"]

    def test_review_comment_null_line_is_preserved(self, respx_mock):
        rc = review_comment_node(id="RC1", line=None)
        node = pr_node(thread_nodes=[thread_node(comment_nodes=[rc])])
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=pr_list_response([node])))
        with GitHubClient("token") as client:
            prs = list(client.fetch_prs("owner", "repo", ["MERGED"]))
        assert prs[0].review_comments[0].line is None


# ---------------------------------------------------------------------------
# fetch_pr()
# ---------------------------------------------------------------------------


class TestFetchPr:
    def test_returns_single_pr(self, respx_mock):
        node = pr_node(number=42, title="Single PR", labels=["feature"])
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=pr_by_number_response(node)))
        with GitHubClient("token") as client:
            result = client.fetch_pr("owner", "repo", 42)
        assert result.number == 42
        assert result.title == "Single PR"
        assert result.labels == ["feature"]
        assert result.author == "alice"
        assert result.additions == 10
        assert result.deletions == 5
        assert result.changed_files == 2

    def test_pr_not_found_raises(self, respx_mock):
        body = {
            "data": {
                "rateLimit": {"cost": 1, "remaining": 4999, "resetAt": "x"},
                "repository": {"pullRequest": None},
            }
        }
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=body))
        with GitHubClient("token") as client:
            with pytest.raises(RepoNotFoundError, match="#99"):
                client.fetch_pr("owner", "repo", 99)

    def test_repo_not_found_raises(self, respx_mock):
        body = {
            "data": {
                "rateLimit": {"cost": 1, "remaining": 4999, "resetAt": "x"},
                "repository": None,
            }
        }
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=body))
        with GitHubClient("token") as client:
            with pytest.raises(RepoNotFoundError, match="owner/repo"):
                client.fetch_pr("owner", "repo", 1)

    def test_inline_comments_parsed(self, respx_mock):
        node = pr_node(comment_nodes=[comment_node(id="C1", body="Nice work")])
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=pr_by_number_response(node)))
        with GitHubClient("token") as client:
            result = client.fetch_pr("owner", "repo", 1)
        assert len(result.comments) == 1
        assert result.comments[0].id == "C1"
        assert result.comments[0].body == "Nice work"

    def test_inline_review_comments_flattened(self, respx_mock):
        rc = review_comment_node(id="RC1", path="main.py", line=7)
        node = pr_node(thread_nodes=[thread_node(id="T1", comment_nodes=[rc])])
        respx_mock.post(GQL_URL).mock(return_value=httpx.Response(200, json=pr_by_number_response(node)))
        with GitHubClient("token") as client:
            result = client.fetch_pr("owner", "repo", 1)
        assert len(result.review_comments) == 1
        assert result.review_comments[0].id == "RC1"
        assert result.review_comments[0].path == "main.py"
        assert result.review_comments[0].line == 7

    def test_sends_correct_variables(self, respx_mock):
        node = pr_node(number=123)
        route = respx_mock.post(GQL_URL).mock(
            return_value=httpx.Response(200, json=pr_by_number_response(node))
        )
        with GitHubClient("token") as client:
            client.fetch_pr("myowner", "myrepo", 123)
        body = json.loads(route.calls[0].request.content)
        assert body["variables"]["owner"] == "myowner"
        assert body["variables"]["repo"] == "myrepo"
        assert body["variables"]["number"] == 123
