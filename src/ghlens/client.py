from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx
from rich.console import Console

from .errors import ApiError, AuthError, NetworkError, RateLimitError, RepoNotFoundError
from .models import ConversationalComment, PullRequest, ReviewComment
from .queries import (
    COMMENTS_PAGE_QUERY,
    PR_BY_NUMBER_QUERY,
    PR_LIST_QUERY,
    REVIEW_THREADS_PAGE_QUERY,
    THREAD_COMMENTS_PAGE_QUERY,
)

_GRAPHQL_URL = "https://api.github.com/graphql"
_RETRY_DELAYS = (1, 5, 15)
_stderr = Console(stderr=True)


class GitHubClient:
    def __init__(self, token: str) -> None:
        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(30.0),
        )

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self._client.close()

    def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        last_exc: Exception | None = None
        for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
            try:
                response = self._client.post(_GRAPHQL_URL, json=payload)
            except httpx.TimeoutException as exc:
                last_exc = exc
                if delay is not None:
                    time.sleep(delay)
                continue
            except httpx.RequestError as exc:
                raise NetworkError(str(exc)) from exc

            if response.status_code == 401:
                raise AuthError("GitHub token is invalid or missing required scopes.")
            if response.status_code >= 500:
                last_exc = ApiError(f"GitHub API returned HTTP {response.status_code}")
                if delay is not None:
                    time.sleep(delay)
                continue
            if response.status_code != 200:
                raise ApiError(f"GitHub API returned HTTP {response.status_code}: {response.text}")

            data = response.json()

            if errors := data.get("errors"):
                msg = errors[0].get("message", "Unknown GraphQL error")
                if "Could not resolve to a Repository" in msg or "NOT_FOUND" in str(errors[0].get("type", "")):
                    raise RepoNotFoundError(msg)
                raise ApiError(msg)

            if rate_limit := data.get("data", {}).get("rateLimit"):
                remaining = rate_limit.get("remaining", 9999)
                if remaining == 0:
                    reset_at = rate_limit.get("resetAt", "unknown")
                    raise RateLimitError(f"GitHub rate limit exhausted. Resets at {reset_at}.")
                if remaining < 100:
                    _stderr.print(
                        f"[yellow]Warning:[/yellow] GitHub rate limit low: {remaining} requests remaining "
                        f"(resets at {rate_limit.get('resetAt', 'unknown')})"
                    )

            return data

        raise NetworkError(f"Request failed after retries: {last_exc}") from last_exc

    def fetch_prs(
        self,
        owner: str,
        repo: str,
        states: list[str],
        limit: int | None = None,
        labels: list[str] | None = None,
    ) -> Iterator[PullRequest]:
        after: str | None = None
        fetched = 0
        variables: dict[str, Any] = {"owner": owner, "repo": repo}
        if states != ["OPEN", "CLOSED", "MERGED"]:
            variables["states"] = states
        if labels:
            variables["labels"] = labels

        while True:
            if after:
                variables["after"] = after
            else:
                variables.pop("after", None)

            data = self.execute(PR_LIST_QUERY, variables)
            repo_data = data.get("data", {}).get("repository")
            if repo_data is None:
                raise RepoNotFoundError(f"Repository {owner}/{repo} not found.")

            prs_conn = repo_data["pullRequests"]
            page_info = prs_conn["pageInfo"]
            nodes = prs_conn["nodes"]

            for node in nodes:
                if limit is not None and fetched >= limit:
                    return

                comments = self._complete_comments(
                    pr_node_id=node["id"],
                    existing=[self._parse_comment(c) for c in node["comments"]["nodes"]],
                    page_info=node["comments"]["pageInfo"],
                )

                review_comments = self._complete_review_threads(
                    pr_node_id=node["id"],
                    existing_threads=node["reviewThreads"]["nodes"],
                    page_info=node["reviewThreads"]["pageInfo"],
                )

                pr = PullRequest(
                    number=node["number"],
                    title=node["title"],
                    author=node["author"]["login"] if node.get("author") else None,
                    state=node["state"],
                    url=node["url"],
                    created_at=node["createdAt"],
                    updated_at=node["updatedAt"],
                    merged_at=node.get("mergedAt"),
                    labels=[lbl["name"] for lbl in node["labels"]["nodes"]],
                    changed_files=node["changedFiles"],
                    additions=node["additions"],
                    deletions=node["deletions"],
                    comments=comments,
                    review_comments=review_comments,
                )
                yield pr
                fetched += 1

                if limit is not None and fetched >= limit:
                    return

            if not page_info["hasNextPage"]:
                break
            after = page_info["endCursor"]

    def fetch_pr(self, owner: str, repo: str, number: int) -> PullRequest:
        data = self.execute(PR_BY_NUMBER_QUERY, {"owner": owner, "repo": repo, "number": number})
        repo_data = data.get("data", {}).get("repository")
        if repo_data is None:
            raise RepoNotFoundError(f"Repository {owner}/{repo} not found.")
        node = repo_data.get("pullRequest")
        if node is None:
            raise RepoNotFoundError(f"Pull request #{number} not found in {owner}/{repo}.")

        comments = self._complete_comments(
            pr_node_id=node["id"],
            existing=[self._parse_comment(c) for c in node["comments"]["nodes"]],
            page_info=node["comments"]["pageInfo"],
        )
        review_comments = self._complete_review_threads(
            pr_node_id=node["id"],
            existing_threads=node["reviewThreads"]["nodes"],
            page_info=node["reviewThreads"]["pageInfo"],
        )
        return PullRequest(
            number=node["number"],
            title=node["title"],
            author=node["author"]["login"] if node.get("author") else None,
            state=node["state"],
            url=node["url"],
            created_at=node["createdAt"],
            updated_at=node["updatedAt"],
            merged_at=node.get("mergedAt"),
            labels=[lbl["name"] for lbl in node["labels"]["nodes"]],
            changed_files=node["changedFiles"],
            additions=node["additions"],
            deletions=node["deletions"],
            comments=comments,
            review_comments=review_comments,
        )

    def _complete_comments(
        self,
        pr_node_id: str,
        existing: list[ConversationalComment],
        page_info: dict[str, Any],
    ) -> list[ConversationalComment]:
        comments = list(existing)
        cursor = page_info.get("endCursor")

        while page_info.get("hasNextPage") and cursor:
            data = self.execute(COMMENTS_PAGE_QUERY, {"prId": pr_node_id, "after": cursor})
            conn = data["data"]["node"]["comments"]
            comments.extend(self._parse_comment(c) for c in conn["nodes"])
            page_info = conn["pageInfo"]
            cursor = page_info.get("endCursor")

        return comments

    def _complete_review_threads(
        self,
        pr_node_id: str,
        existing_threads: list[dict[str, Any]],
        page_info: dict[str, Any],
    ) -> list[ReviewComment]:
        threads = list(existing_threads)
        cursor = page_info.get("endCursor")

        while page_info.get("hasNextPage") and cursor:
            data = self.execute(REVIEW_THREADS_PAGE_QUERY, {"prId": pr_node_id, "after": cursor})
            conn = data["data"]["node"]["reviewThreads"]
            threads.extend(conn["nodes"])
            page_info = conn["pageInfo"]
            cursor = page_info.get("endCursor")

        return self._flatten_threads(threads)

    def _flatten_threads(self, thread_nodes: list[dict[str, Any]]) -> list[ReviewComment]:
        result: list[ReviewComment] = []
        for thread in thread_nodes:
            thread_id = thread["id"]
            comments_conn = thread["comments"]
            comment_nodes = list(comments_conn["nodes"])
            thread_page_info = comments_conn["pageInfo"]
            cursor = thread_page_info.get("endCursor")

            while thread_page_info.get("hasNextPage") and cursor:
                data = self.execute(THREAD_COMMENTS_PAGE_QUERY, {"threadId": thread_id, "after": cursor})
                conn = data["data"]["node"]["comments"]
                comment_nodes.extend(conn["nodes"])
                thread_page_info = conn["pageInfo"]
                cursor = thread_page_info.get("endCursor")

            for c in comment_nodes:
                result.append(self._parse_review_comment(c))

        return result

    @staticmethod
    def _parse_comment(node: dict[str, Any]) -> ConversationalComment:
        return ConversationalComment(
            id=node["id"],
            author=node["author"]["login"] if node.get("author") else None,
            body=node["body"],
            url=node["url"],
            created_at=node["createdAt"],
        )

    @staticmethod
    def _parse_review_comment(node: dict[str, Any]) -> ReviewComment:
        return ReviewComment(
            id=node["id"],
            author=node["author"]["login"] if node.get("author") else None,
            body=node["body"],
            path=node["path"],
            line=node.get("line"),
            diff_hunk=node["diffHunk"],
            url=node["url"],
            created_at=node["createdAt"],
        )
