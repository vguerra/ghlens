# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install / sync dependencies
uv sync

# Run the CLI
uv run ghlens --help
uv run ghlens fetch OWNER/REPO --limit 5 --format json
uv run ghlens fetch OWNER/REPO --limit 5 --format markdown --output prs.md

# Run tests
uv run pytest

# Run a single test file or test
uv run pytest tests/test_client.py
uv run pytest tests/test_client.py::test_execute_retries
```

`GITHUB_TOKEN` is read from the environment or from a `.env` file in the working directory (via `python-dotenv`).

## Architecture

The data flow is: **CLI → GitHubClient → GraphQL API → models → formatter → output**.

### Pagination strategy (`client.py`)

`fetch_prs()` is a generator that pages through PRs 50 at a time. For each PR node returned by `PR_LIST_QUERY`, the first page of conversational comments (50) and review threads (30, each with 10 comments) is already inlined. Overflow is handled by three follow-up methods that use node-by-ID queries:

- `_complete_comments` — fetches overflow conversational comments for a PR
- `_complete_review_threads` — fetches overflow review thread pages for a PR
- `_flatten_threads` — iterates thread nodes, fetches overflow thread comments, and flattens everything into `list[ReviewComment]`

`execute()` handles HTTP-level concerns: 401 → `AuthError`, 5xx/timeout → retry (1/5/15s backoff, 3 attempts), GraphQL `errors[]` → domain exceptions, rate limit checking.

### Models (`models.py`)

All three dataclasses (`PullRequest`, `ConversationalComment`, `ReviewComment`) are frozen. Dates are stored as ISO-8601 strings to stay trivially JSON-serializable. `PullRequest.review_comments` is the already-flattened list of all comments from all review threads.

### Formatters (`formatters/`)

`get_formatter(fmt, **kwargs)` returns a `Callable[[list[PullRequest]], str]`. JSON uses `dataclasses.asdict()`. Markdown accepts `owner_repo` as a kwarg (passed through the factory closure) for the document title.

### Error hierarchy (`errors.py`)

```
GhLensError
├── AuthError
├── ApiError
│   └── RateLimitError
├── NetworkError
└── RepoNotFoundError
```

The CLI catches `GhLensError` and exits 1. All other exceptions propagate normally.

### GraphQL queries (`queries.py`)

Four module-level string constants. `PR_LIST_QUERY` includes `rateLimit` on every request. The three follow-up queries (`COMMENTS_PAGE_QUERY`, `REVIEW_THREADS_PAGE_QUERY`, `THREAD_COMMENTS_PAGE_QUERY`) all use `node(id: $id)` to target a specific PR or thread by its GraphQL node ID.
