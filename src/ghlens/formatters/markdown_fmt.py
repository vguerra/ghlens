from __future__ import annotations

from datetime import datetime, timezone

from ..models import PullRequest


def format_markdown(prs: list[PullRequest], owner_repo: str = "") -> str:
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state_label = prs[0].state if len({pr.state for pr in prs}) == 1 else "ALL"
    lines: list[str] = []

    title = f"Pull Requests: {owner_repo}" if owner_repo else "Pull Requests"
    lines.append(f"# {title}")
    lines.append(f"> Fetched {len(prs)} PRs · State: {state_label} · Generated: {now}")
    lines.append("")

    for pr in prs:
        lines.append(f"## PR #{pr.number} — {pr.title}")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("| --- | --- |")
        lines.append(f"| Author | {pr.author or 'ghost'} |")
        lines.append(f"| State | {pr.state} |")
        lines.append(f"| Created | {pr.created_at} |")
        lines.append(f"| Updated | {pr.updated_at} |")
        if pr.merged_at:
            lines.append(f"| Merged | {pr.merged_at} |")
        lines.append(f"| Changed Files | {pr.changed_files} |")
        lines.append(f"| Additions | {pr.additions} |")
        lines.append(f"| Deletions | {pr.deletions} |")
        if pr.labels:
            lines.append(f"| Labels | {', '.join(pr.labels)} |")
        lines.append(f"| URL | {pr.url} |")
        lines.append("")

        if pr.comments:
            lines.append(f"### Conversational Comments ({len(pr.comments)})")
            lines.append("")
            for c in pr.comments:
                author = c.author or "ghost"
                lines.append(f"#### Comment by @{author} — {c.created_at}")
                lines.append("")
                lines.append(f"[View comment]({c.url})")
                lines.append("")
                lines.append(c.body)
                lines.append("")

        if pr.review_comments:
            lines.append(f"### Code Review Comments ({len(pr.review_comments)})")
            lines.append("")
            for rc in pr.review_comments:
                author = rc.author or "ghost"
                lines.append(f"#### Review Comment by @{author} — {rc.created_at}")
                lines.append("")
                line_info = f" **Line:** {rc.line}" if rc.line is not None else ""
                lines.append(f"**File:** `{rc.path}`{line_info}")
                lines.append("")
                lines.append("```diff")
                lines.append(rc.diff_hunk)
                lines.append("```")
                lines.append("")
                lines.append(f"[View comment]({rc.url})")
                lines.append("")
                lines.append(rc.body)
                lines.append("")

    return "\n".join(lines)
