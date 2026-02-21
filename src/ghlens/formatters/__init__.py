from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .json_fmt import format_json
from .markdown_fmt import format_markdown
from ..models import PullRequest


def get_formatter(fmt: str, **kwargs: Any) -> Callable[[list[PullRequest]], str]:
    if fmt == "json":
        return format_json
    if fmt == "markdown":
        owner_repo = kwargs.get("owner_repo", "")
        return lambda prs: format_markdown(prs, owner_repo=owner_repo)
    raise ValueError(f"Unknown format: {fmt!r}")
