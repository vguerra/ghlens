PR_LIST_QUERY = """
query PullRequests($owner: String!, $repo: String!, $states: [PullRequestState!], $labels: [String!], $after: String) {
  rateLimit {
    cost
    remaining
    resetAt
  }
  repository(owner: $owner, name: $repo) {
    pullRequests(first: 50, states: $states, labelNames: $labels, after: $after, orderBy: {field: CREATED_AT, direction: DESC}) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        id
        number
        title
        state
        url
        createdAt
        updatedAt
        mergedAt
        additions
        deletions
        changedFiles
        author {
          login
        }
        labels(first: 20) {
          nodes {
            name
          }
        }
        comments(first: 50) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            id
            author {
              login
            }
            body
            url
            createdAt
          }
        }
        reviewThreads(first: 30) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            id
            comments(first: 10) {
              pageInfo {
                hasNextPage
                endCursor
              }
              nodes {
                id
                author {
                  login
                }
                body
                path
                line
                diffHunk
                url
                createdAt
              }
            }
          }
        }
      }
    }
  }
}
"""

COMMENTS_PAGE_QUERY = """
query PullRequestComments($prId: ID!, $after: String) {
  node(id: $prId) {
    ... on PullRequest {
      comments(first: 100, after: $after) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          author {
            login
          }
          body
          url
          createdAt
        }
      }
    }
  }
}
"""

REVIEW_THREADS_PAGE_QUERY = """
query PullRequestReviewThreads($prId: ID!, $after: String) {
  node(id: $prId) {
    ... on PullRequest {
      reviewThreads(first: 50, after: $after) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          comments(first: 10) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              id
              author {
                login
              }
              body
              path
              line
              diffHunk
              url
              createdAt
            }
          }
        }
      }
    }
  }
}
"""

THREAD_COMMENTS_PAGE_QUERY = """
query ReviewThreadComments($threadId: ID!, $after: String) {
  node(id: $threadId) {
    ... on PullRequestReviewThread {
      comments(first: 100, after: $after) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          author {
            login
          }
          body
          path
          line
          diffHunk
          url
          createdAt
        }
      }
    }
  }
}
"""
