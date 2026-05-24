"""GitHub GraphQL + REST client.

Fetches all data needed for stats, activity, and language cards. Uses a
single GraphQL query where possible to stay under the 5000 points/hour
rate limit.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

GRAPHQL_URL = "https://api.github.com/graphql"
REST_URL = "https://api.github.com"

# Excluded from language stats. Vendored libraries, generated code, and
# data formats inflate file-size metrics without reflecting authored work.
EXCLUDED_LANGS = {
    "Markdown",
    "Text",
    "JSON",
    "YAML",
    "TOML",
    "XML",
    "INI",
    "Roff",
    "Makefile",
    "CMake",
    "Dockerfile",
    "Shell",
    "Batchfile",
    "PowerShell",
}


@dataclass
class LanguageStat:
    name: str
    color: str
    bytes: int = 0
    commits: int = 0


@dataclass
class TopRepo:
    name: str
    stars: int
    forks: int
    primary_language: str | None
    primary_color: str | None


@dataclass
class GitHubData:
    login: str
    name: str
    avatar_url: str
    followers: int
    following: int
    public_repos: int
    created_at: str

    total_stars: int = 0
    total_forks: int = 0
    total_commits: int = 0
    total_prs: int = 0
    merged_prs: int = 0
    total_issues: int = 0
    closed_issues: int = 0
    reviews: int = 0
    contributions_year: int = 0
    contributions_total: int = 0
    longest_streak: int = 0
    current_streak: int = 0

    # Per-day contribution counts for the last 52 weeks (chronological).
    contribution_days: list[int] = field(default_factory=list)
    # Number of leading empty cells before contribution_days[0] within the
    # first column of the heatmap. Lets the renderer align the grid to
    # GitHub's Sun..Sat columns instead of starting at row 0.
    contribution_offset: int = 0

    languages_by_size: list[LanguageStat] = field(default_factory=list)
    languages_by_commits: list[LanguageStat] = field(default_factory=list)
    top_repos: list[TopRepo] = field(default_factory=list)


def _client() -> httpx.Client:
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("GH_TOKEN environment variable is not set")
    return httpx.Client(
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-profile-stats",
        },
        timeout=15.0,
    )


_USER_QUERY = """
query($login: String!) {
  user(login: $login) {
    login
    name
    avatarUrl
    createdAt
    followers { totalCount }
    following { totalCount }
    repositories(first: 1, ownerAffiliations: OWNER, isFork: false) { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
        weeks {
          firstDay
          contributionDays {
            date
            contributionCount
            weekday
          }
        }
      }
    }
    pullRequests(states: MERGED) { totalCount }
    issues(states: CLOSED) { totalCount }
    repositoriesContributedTo(
      first: 1,
      contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, PULL_REQUEST_REVIEW]
    ) { totalCount }
  }
}
"""


_REPOS_QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    repositories(
      first: 50,
      after: $cursor,
      ownerAffiliations: OWNER,
      isFork: false,
      orderBy: {field: STARGAZERS, direction: DESC}
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        stargazerCount
        forkCount
        primaryLanguage { name color }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def _gql(client: httpx.Client, query: str, variables: dict, retries: int = 3) -> dict:
    """POST GraphQL with retry on 502/503/504. GitHub is occasionally flaky."""
    import time

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            resp = client.post(GRAPHQL_URL, json={"query": query, "variables": variables})
            if resp.status_code in (502, 503, 504):
                last_error = httpx.HTTPStatusError(
                    f"transient {resp.status_code}", request=resp.request, response=resp
                )
                time.sleep(0.5 * (2**attempt))
                continue
            resp.raise_for_status()
            payload = resp.json()
            if "errors" in payload:
                raise RuntimeError(f"GraphQL errors: {payload['errors']}")
            return payload["data"]
        except httpx.HTTPStatusError as e:
            last_error = e
            if e.response.status_code not in (502, 503, 504):
                raise
            time.sleep(0.5 * (2**attempt))
    raise last_error or RuntimeError("GraphQL request failed after retries")


def _streaks(daily_counts: list[tuple[str, int]]) -> tuple[int, int]:
    """Return (current_streak, longest_streak) given chronological days."""
    longest = 0
    run = 0
    for _, count in daily_counts:
        if count > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    current = 0
    today = datetime.now(timezone.utc).date().isoformat()
    # Walk backwards from the most recent day. If today is empty, allow it
    # (the day may not be over yet) and start counting from the previous day.
    for i, (date_str, count) in enumerate(reversed(daily_counts)):
        if i == 0 and date_str == today and count == 0:
            continue
        if count > 0:
            current += 1
        else:
            break

    return current, longest


def fetch(username: str) -> GitHubData:
    with _client() as client:
        user_data = _gql(client, _USER_QUERY, {"login": username})["user"]

        cc = user_data["contributionsCollection"]
        cal = cc["contributionCalendar"]

        weeks = cal["weeks"]
        flat_days: list[tuple[str, int]] = []
        for week in weeks:
            for day in week["contributionDays"]:
                flat_days.append((day["date"], day["contributionCount"]))

        first_week = weeks[0]["contributionDays"] if weeks else []
        offset = first_week[0]["weekday"] if first_week else 0

        current_streak, longest_streak = _streaks(flat_days)

        data = GitHubData(
            login=user_data["login"],
            name=user_data.get("name") or user_data["login"],
            avatar_url=user_data["avatarUrl"],
            followers=user_data["followers"]["totalCount"],
            following=user_data["following"]["totalCount"],
            public_repos=user_data["repositories"]["totalCount"],
            created_at=user_data["createdAt"],
            total_commits=cc["totalCommitContributions"],
            total_prs=cc["totalPullRequestContributions"],
            merged_prs=user_data["pullRequests"]["totalCount"],
            total_issues=cc["totalIssueContributions"],
            closed_issues=user_data["issues"]["totalCount"],
            reviews=cc["totalPullRequestReviewContributions"],
            contributions_year=cal["totalContributions"],
            contribution_days=[c for _, c in flat_days],
            contribution_offset=offset,
            current_streak=current_streak,
            longest_streak=longest_streak,
        )

        size_acc: dict[str, LanguageStat] = {}
        commits_acc: dict[str, LanguageStat] = {}
        repos: list[TopRepo] = []

        # Only paginate the first 100 repos (sorted by stars desc). For accounts
        # with hundreds of repos, walking everything blows past GitHub camo's
        # ~5s fetch timeout. Top-100 covers all stargazed repos and the bulk of
        # language distribution; the long tail is forks/experiments anyway.
        MAX_REPOS = 100
        repos_seen = 0
        cursor = None
        while repos_seen < MAX_REPOS:
            page = _gql(client, _REPOS_QUERY, {"login": username, "cursor": cursor})
            repo_nodes = page["user"]["repositories"]
            for node in repo_nodes["nodes"]:
                data.total_stars += node["stargazerCount"]
                data.total_forks += node["forkCount"]

                primary = node.get("primaryLanguage") or {}
                repos.append(
                    TopRepo(
                        name=node["name"],
                        stars=node["stargazerCount"],
                        forks=node["forkCount"],
                        primary_language=primary.get("name"),
                        primary_color=primary.get("color"),
                    )
                )

                edges = node["languages"]["edges"]

                primary_name = primary.get("name")
                if primary_name:
                    # Proxy for "commits" metric: count repos using this language
                    # as primary. GitHub doesn't expose per-language commit count
                    # cheaply — exact totalCount triggers expensive history walks
                    # and frequent 502s. Repo count is a stable, cheap proxy.
                    bucket = commits_acc.setdefault(
                        primary_name,
                        LanguageStat(
                            name=primary_name,
                            color=primary.get("color") or "",
                        ),
                    )
                    bucket.commits += 1

                for edge in edges:
                    lang = edge["node"]
                    name = lang["name"]
                    size = edge["size"]
                    if name in EXCLUDED_LANGS:
                        continue
                    bucket = size_acc.setdefault(
                        name, LanguageStat(name=name, color=lang.get("color") or "")
                    )
                    bucket.bytes += size

                repos_seen += 1
                if repos_seen >= MAX_REPOS:
                    break

            if repos_seen >= MAX_REPOS or not repo_nodes["pageInfo"]["hasNextPage"]:
                break
            cursor = repo_nodes["pageInfo"]["endCursor"]

        data.contributions_total = data.contributions_year

        data.languages_by_size = sorted(
            size_acc.values(), key=lambda l: l.bytes, reverse=True
        )
        data.languages_by_commits = sorted(
            commits_acc.values(), key=lambda l: l.commits, reverse=True
        )
        data.top_repos = sorted(repos, key=lambda r: r.stars, reverse=True)[:6]

        return data


def language_percentages(
    stats: list[LanguageStat], metric: str = "size", limit: int = 10
) -> list[tuple[LanguageStat, float]]:
    key = "bytes" if metric == "size" else "commits"
    total = sum(getattr(s, key) for s in stats) or 1
    out: list[tuple[LanguageStat, float]] = []
    for stat in stats[:limit]:
        pct = getattr(stat, key) / total * 100
        out.append((stat, pct))
    return out
