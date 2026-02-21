from __future__ import annotations

import dataclasses
import json

from ..models import PullRequest


def format_json(prs: list[PullRequest]) -> str:
    return json.dumps([dataclasses.asdict(pr) for pr in prs], indent=2)
