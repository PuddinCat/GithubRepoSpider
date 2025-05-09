from pathlib import Path
from datetime import datetime, timedelta
import asyncio
import os
import json

import jsonschema
import httpx

from search_response_scheme import JSON_SCHEMA
from typing import TypedDict, List, Dict, Any


# Replace with your GitHub personal access token
GITHUB_TOKEN = os.environ["GITHUB_API_TOKEN"]
GITHUB_API_URL = "https://api.github.com/search/repositories"


class FoundRepo(TypedDict):
    repo_id: str
    repo_data: Dict[str, Any]
    keyword: str


async def search_github_repositories(query, sort="stars", order="desc", pages=5):
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    all_results = {"items": []}
    async with httpx.AsyncClient() as client:
        resps = await asyncio.gather(
            *[
                client.get(
                    GITHUB_API_URL,
                    headers=headers,
                    params={
                        "q": query,
                        "sort": sort,
                        "order": order,
                        "page": page,
                        "per_page": 30,
                    },
                )
                for page in range(1, pages + 1)
            ]
        )
        all_results = []
        for page, resp in zip(range(1, pages + 1), resps):
            if resp.status_code != 200:
                print(f"Error on page {page}: {resp.status_code}, {resp.text}")
                return None

            data = resp.json()
            try:
                jsonschema.validate(instance=data, schema=JSON_SCHEMA)
                all_results += data["items"]
            except jsonschema.ValidationError as e:
                print(f"JSON Schema validation error on page {page}: {e}")
                return None
    return all_results


async def main():

    found_repos: Dict[str, FoundRepo] = {}
    if Path("found_repos.json").exists():
        found_repos = json.loads(Path("found_repos.json").read_text(encoding="utf-8"))

    keywords = [
        "CVE-2025",
    ]
    created_time_since = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    search_results = await asyncio.gather(
        *[
            search_github_repositories(f"{keyword} created:>{created_time_since}")
            for keyword in keywords
        ]
    )

    new_repos_list: List[FoundRepo] = [
        {
            "repo_id": f"{repo['owner']['login']}/{repo['name']}",
            "repo_data": repo,
            "keyword": keyword,
        }
        for keyword, repos in zip(keywords, search_results)
        if repos
        for repo in repos
        if f"{repo['owner']['login']}/{repo['name']}" not in found_repos
    ]
    new_repos = {repo["repo_id"]: repo for repo in new_repos_list}
    found_repos.update(new_repos)

    repos_content = ""
    three_days_ago = datetime.now() - timedelta(days=3)
    sorted_repos = sorted(
        found_repos.items(),
        key=lambda item: datetime.strptime(
            item[1]["repo_data"]["created_at"], "%Y-%m-%dT%H:%M:%SZ"
        ),
        reverse=True,
    )
    for repo_id, repo in sorted_repos:
        repo_data = repo["repo_data"]
        created_at = datetime.strptime(repo_data["created_at"], "%Y-%m-%dT%H:%M:%SZ")
        if created_at <= three_days_ago:
            continue
        repos_content += f"## {repo_id}\n\n"
        repos_content += f"**介绍:** {repo_data['description']}\n\n"
        repos_content += f"**地址:** {repo_data['html_url']}\n\n"
        repos_content += "---\n\n"

    readme_content = (
        Path("readme_template.md")
        .read_text(encoding="utf-8")
        .format(repos=repos_content)
    )

    Path("README.md").write_text(readme_content, encoding="utf-8")

    with open("found_repos.json", "w", encoding="utf-8") as json_file:
        json.dump(found_repos, json_file, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    asyncio.run(main())
