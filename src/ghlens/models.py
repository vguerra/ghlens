from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationalComment:
    id: str
    author: str | None
    body: str
    url: str
    created_at: str


@dataclass(frozen=True)
class ReviewComment:
    id: str
    author: str | None
    body: str
    path: str
    line: int | None
    diff_hunk: str
    url: str
    created_at: str


@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    author: str | None
    state: str
    url: str
    created_at: str
    updated_at: str
    merged_at: str | None
    labels: list[str]
    changed_files: int
    additions: int
    deletions: int
    comments: list[ConversationalComment]
    review_comments: list[ReviewComment]
