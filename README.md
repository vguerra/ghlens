# ghlens

Fetch pull request metadata and comments from the GitHub GraphQL API. Captures both conversational (issue-style) comments and inline code review comments, making it easy to extract reviewer knowledge from any public or private repository you have access to.

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo-url>
cd ghlens
uv sync
```

## Authentication

`ghlens` reads `GITHUB_TOKEN` from your environment or from a `.env` file in the working directory:

```bash
# .env
GITHUB_TOKEN=ghp_your_token_here
```

The token needs the `repo` scope for private repositories; no extra scopes are required for public ones.

## Usage

### Fetch multiple PRs

```
ghlens fetch [OPTIONS] OWNER/REPO
```

| Option | Default | Description |
|---|---|---|
| `--state` | `ALL` | Filter by PR state: `OPEN`, `CLOSED`, `MERGED`, or `ALL` |
| `--label LABEL` | none | Filter by label (repeat for multiple labels, OR logic) |
| `--format` | `json` | Output format: `json` or `markdown` |
| `--output PATH` | stdout | Write output to a file |
| `--limit N` | unlimited | Stop after fetching N PRs |

### Fetch a single PR

```
ghlens pr OWNER/REPO NUMBER [--format json|markdown] [--output PATH]
```

| Option | Default | Description |
|---|---|---|
| `--format` | `json` | Output format: `json` or `markdown` |
| `--output PATH` | stdout | Write output to a file |

### Examples

```bash
# Fetch the 10 most recent PRs as JSON, pipe to jq
ghlens fetch torvalds/linux --limit 10 | jq '.[0] | {number, title, comments: (.comments | length)}'

# Fetch only merged PRs and save as Markdown
ghlens fetch rust-lang/rust --state MERGED --limit 50 --format markdown --output rust-prs.md

# Stream all open PRs from a private repo (requires repo scope on token)
ghlens fetch myorg/myrepo --state OPEN --format json

# Fetch PRs with a specific label
ghlens fetch owner/repo --label bug --limit 20

# Fetch PRs that have any of several labels (OR logic)
ghlens fetch owner/repo --label bug --label performance --format markdown --output issues.md

# Fetch a single PR as JSON
ghlens pr torvalds/linux 12345

# Fetch a single PR as Markdown and save to file
ghlens pr rust-lang/rust 99999 --format markdown --output pr.md
```

## Output

### JSON

A JSON array of PR objects. Each object includes metadata fields plus two comment arrays:

- `comments` — conversational comments on the PR itself
- `review_comments` — inline code review comments, each with `path`, `line`, and `diff_hunk`

```json
[
  {
    "number": 42,
    "title": "Fix memory leak in parser",
    "author": "octocat",
    "state": "MERGED",
    "url": "https://github.com/owner/repo/pull/42",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-16T08:00:00Z",
    "merged_at": "2024-01-16T08:00:00Z",
    "labels": ["bug", "performance"],
    "changed_files": 3,
    "additions": 12,
    "deletions": 45,
    "comments": [...],
    "review_comments": [
      {
        "id": "...",
        "author": "reviewer",
        "body": "This could cause a race condition.",
        "path": "src/parser.c",
        "line": 87,
        "diff_hunk": "@@ -85,6 +85,8 @@\n ...",
        "url": "...",
        "created_at": "2024-01-15T14:22:00Z"
      }
    ]
  }
]
```

### Markdown

A hierarchical document with a metadata table per PR, followed by conversational comments and code review comments (with diff hunks in fenced ` ```diff ` blocks). Empty sections are omitted.

## Rate limits

GitHub's GraphQL API has a rate limit of 5,000 points per hour. `ghlens` fetches `rateLimit` on every request and will:

- Print a warning to stderr when fewer than 100 requests remain
- Exit with an error when the limit is exhausted, reporting the reset time
- Automatically retry transient 5xx errors and timeouts (3 attempts, backoff: 1 / 5 / 15 s)
