"""Shared factories and fixtures for the test suite."""
from __future__ import annotations

import pytest

from ghlens.models import ConversationalComment, PullRequest, ReviewComment

# ---------------------------------------------------------------------------
# GraphQL node factories — return raw dicts that mirror API responses
# ---------------------------------------------------------------------------

_RATE_LIMIT = {"cost": 1, "remaining": 4999, "resetAt": "2024-12-31T23:59:59Z"}


def rate_limit_data(remaining: int = 4999) -> dict:
    return {"cost": 1, "remaining": remaining, "resetAt": "2024-12-31T23:59:59Z"}


def comment_node(
    id: str = "C1",
    author: str | None = "reviewer",
    body: str = "Looks good",
    url: str = "https://github.com/owner/repo/pull/1#issuecomment-1",
    created_at: str = "2024-01-01T10:00:00Z",
) -> dict:
    return {
        "id": id,
        "author": {"login": author} if author else None,
        "body": body,
        "url": url,
        "createdAt": created_at,
    }


def review_comment_node(
    id: str = "RC1",
    author: str | None = "reviewer",
    body: str = "Fix this",
    path: str = "src/foo.py",
    line: int | None = 42,
    diff_hunk: str = "@@ -1,3 +1,4 @@\n context\n+new line",
    url: str = "https://github.com/owner/repo/pull/1#discussion_r1",
    created_at: str = "2024-01-01T11:00:00Z",
) -> dict:
    return {
        "id": id,
        "author": {"login": author} if author else None,
        "body": body,
        "path": path,
        "line": line,
        "diffHunk": diff_hunk,
        "url": url,
        "createdAt": created_at,
    }


def thread_node(
    id: str = "T1",
    comment_nodes: list[dict] | None = None,
    has_next_page: bool = False,
    end_cursor: str | None = None,
) -> dict:
    if comment_nodes is None:
        comment_nodes = [review_comment_node()]
    return {
        "id": id,
        "comments": {
            "pageInfo": {"hasNextPage": has_next_page, "endCursor": end_cursor},
            "nodes": comment_nodes,
        },
    }


def pr_node(
    id: str = "PR_1",
    number: int = 1,
    title: str = "Fix bug",
    state: str = "MERGED",
    author: str | None = "alice",
    merged_at: str | None = "2024-01-02T00:00:00Z",
    labels: list[str] | None = None,
    comment_nodes: list[dict] | None = None,
    thread_nodes: list[dict] | None = None,
    comments_has_next: bool = False,
    comments_cursor: str | None = None,
    threads_has_next: bool = False,
    threads_cursor: str | None = None,
) -> dict:
    return {
        "id": id,
        "number": number,
        "title": title,
        "state": state,
        "url": f"https://github.com/owner/repo/pull/{number}",
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-02T00:00:00Z",
        "mergedAt": merged_at,
        "additions": 10,
        "deletions": 5,
        "changedFiles": 2,
        "author": {"login": author} if author else None,
        "labels": {"nodes": [{"name": lbl} for lbl in (labels or [])]},
        "comments": {
            "pageInfo": {"hasNextPage": comments_has_next, "endCursor": comments_cursor},
            "nodes": comment_nodes or [],
        },
        "reviewThreads": {
            "pageInfo": {"hasNextPage": threads_has_next, "endCursor": threads_cursor},
            "nodes": thread_nodes or [],
        },
    }


def pr_list_response(
    pr_nodes: list[dict],
    has_next_page: bool = False,
    end_cursor: str | None = None,
    remaining: int = 4999,
) -> dict:
    return {
        "data": {
            "rateLimit": rate_limit_data(remaining),
            "repository": {
                "pullRequests": {
                    "pageInfo": {"hasNextPage": has_next_page, "endCursor": end_cursor},
                    "nodes": pr_nodes,
                }
            },
        }
    }


def comments_page_response(
    nodes: list[dict],
    has_next_page: bool = False,
    end_cursor: str | None = None,
) -> dict:
    return {
        "data": {
            "node": {
                "comments": {
                    "pageInfo": {"hasNextPage": has_next_page, "endCursor": end_cursor},
                    "nodes": nodes,
                }
            }
        }
    }


def review_threads_page_response(
    thread_nodes: list[dict],
    has_next_page: bool = False,
    end_cursor: str | None = None,
) -> dict:
    return {
        "data": {
            "node": {
                "reviewThreads": {
                    "pageInfo": {"hasNextPage": has_next_page, "endCursor": end_cursor},
                    "nodes": thread_nodes,
                }
            }
        }
    }


def pr_by_number_response(
    node: dict,
    remaining: int = 4999,
) -> dict:
    return {
        "data": {
            "rateLimit": rate_limit_data(remaining),
            "repository": {
                "pullRequest": node,
            },
        }
    }


def thread_comments_page_response(
    nodes: list[dict],
    has_next_page: bool = False,
    end_cursor: str | None = None,
) -> dict:
    return {
        "data": {
            "node": {
                "comments": {
                    "pageInfo": {"hasNextPage": has_next_page, "endCursor": end_cursor},
                    "nodes": nodes,
                }
            }
        }
    }


# ---------------------------------------------------------------------------
# Model object factories — construct typed model instances
# ---------------------------------------------------------------------------


def make_conv_comment(
    id: str = "C1",
    author: str | None = "reviewer",
    body: str = "Looks good",
    url: str = "https://github.com/owner/repo/pull/1#issuecomment-1",
    created_at: str = "2024-01-01T10:00:00Z",
) -> ConversationalComment:
    return ConversationalComment(
        id=id, author=author, body=body, url=url, created_at=created_at
    )


def make_review_comment(
    id: str = "RC1",
    author: str | None = "reviewer",
    body: str = "Fix this",
    path: str = "src/foo.py",
    line: int | None = 42,
    diff_hunk: str = "@@ -1,3 +1,4 @@\n context\n+new line",
    url: str = "https://github.com/owner/repo/pull/1#discussion_r1",
    created_at: str = "2024-01-01T11:00:00Z",
) -> ReviewComment:
    return ReviewComment(
        id=id,
        author=author,
        body=body,
        path=path,
        line=line,
        diff_hunk=diff_hunk,
        url=url,
        created_at=created_at,
    )


def make_pull_request(
    number: int = 1,
    title: str = "Fix bug",
    author: str | None = "alice",
    state: str = "MERGED",
    url: str = "https://github.com/owner/repo/pull/1",
    created_at: str = "2024-01-01T00:00:00Z",
    updated_at: str = "2024-01-02T00:00:00Z",
    merged_at: str | None = "2024-01-02T00:00:00Z",
    labels: list[str] | None = None,
    changed_files: int = 2,
    additions: int = 10,
    deletions: int = 5,
    comments: list[ConversationalComment] | None = None,
    review_comments: list[ReviewComment] | None = None,
) -> PullRequest:
    return PullRequest(
        number=number,
        title=title,
        author=author,
        state=state,
        url=url,
        created_at=created_at,
        updated_at=updated_at,
        merged_at=merged_at,
        labels=labels or [],
        changed_files=changed_files,
        additions=additions,
        deletions=deletions,
        comments=comments or [],
        review_comments=review_comments or [],
    )


# ---------------------------------------------------------------------------
# Autouse fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_dotenv(mocker):
    """Prevent tests from loading a real .env file."""
    mocker.patch("ghlens.cli.load_dotenv")
