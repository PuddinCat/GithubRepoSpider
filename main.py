from pathlib import Path
from datetime import datetime, timedelta
from traceback import print_exc
import asyncio
import os
import re
import json
import time
import random

import jsonschema
import httpx
import telegram

from const import JSON_SCHEMA, KEYWORDS
from typing import TypedDict, List, Dict, Any


GITHUB_TOKEN = os.environ["GITHUB_TOKEN"] if "GITHUB_TOKEN" in os.environ else None
GITHUB_API_URL = "https://api.github.com/search/repositories"
TELEGRAM_BOT_API = os.environ["TELEGRAM_BOT_TOKEN"]

TELEGARM_BOT_TEMPLATE = """\
GitHub又有新仓库了! #{keyword}

介绍: {desc}
链接: {url}
"""

DESC_BLACKLIST_REGEX = re.compile(r"cheat|free download", re.I)

MIN_REQUEST_INTERVAL = 0.03
last_request_time_lock = asyncio.Lock()
last_request_time = 0


class FoundRepo(TypedDict):
    repo_id: str
    repo_data: Dict[str, Any]
    keyword: str


async def query_github(
    client: httpx.AsyncClient,
    headers: dict,
    query: str,
    sort: str,
    order: str,
    page: int,
):
    global last_request_time
    while True:
        duration = time.perf_counter() - last_request_time
        if duration < MIN_REQUEST_INTERVAL:
            await asyncio.sleep(MIN_REQUEST_INTERVAL - duration)
            continue

        async with last_request_time_lock:
            last_request_time = time.perf_counter()
            break

    return await client.get(
        GITHUB_API_URL,
        headers=headers,
        params={
            "q": query,
            "sort": sort,
            "order": order,
            "page": page,
            "per_page": 100,
        },
    )


async def search_github_repositories(query, sort="stars", order="desc", pages=1):
    headers = {
        "Accept": "application/vnd.github.v3+json",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    all_results = {"items": []}
    async with httpx.AsyncClient() as client:
        resps = await asyncio.gather(
            *[
                query_github(
                    client=client,
                    headers=headers,
                    query=query,
                    sort=sort,
                    order=order,
                    page=page,
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


async def send_repo_messages(bot: telegram.Bot, repos: List[FoundRepo]):
    telegram_sent_repos = set()
    if Path("telegram_sent_repos.json").exists():
        telegram_sent_repos = set(
            json.loads(Path("telegram_sent_repos.json").read_text(encoding="utf-8"))
        )

    for repo in repos:
        if repo["repo_id"] in telegram_sent_repos:
            continue
        try:
            await bot.send_message(
                chat_id="@puddin_github_sec_repo",
                text=TELEGARM_BOT_TEMPLATE.format(
                    keyword=repo["keyword"].replace(" ", "_"),
                    desc=repo["repo_data"]["description"],
                    url=repo["repo_data"]["html_url"],
                ),
            )
        except telegram.error.RetryAfter:
            print("rate limit")
            await asyncio.sleep(5)
            continue
        except telegram.error.TimedOut:
            continue
        except telegram.error.TelegramError:
            print_exc()
            continue
        except Exception:
            print_exc()
            continue

        telegram_sent_repos.add(repo["repo_id"])
        Path("telegram_sent_repos.json").write_text(
            json.dumps(list(telegram_sent_repos)), encoding="utf-8"
        )


async def is_valuable_repo(client: httpx.AsyncClient, repo: Dict[str, Any]) -> bool:

    if "description" in repo and repo["description"] is not None and DESC_BLACKLIST_REGEX.search(repo["description"]):
        return False
    
    contributors_url = repo.get("contributors_url")
    if not contributors_url:
        return False

    response = await client.get(contributors_url)
    if response.status_code != 200:
        return False

    contributors = response.json()
    return len(contributors) > 0


async def main():

    found_repos: Dict[str, FoundRepo] = {}
    if Path("found_repos.json").exists():
        found_repos = json.loads(Path("found_repos.json").read_text(encoding="utf-8"))

    keywords = random.sample(KEYWORDS, 20)

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

    async with httpx.AsyncClient() as client:
        repo_valuable_results = [
            is_valuable_repo(client, repo["repo_data"]) for repo in new_repos_list
        ]
        new_repos_list = [
            repo
            for repo, is_repo_valuable in zip(new_repos_list, repo_valuable_results)
            if is_repo_valuable
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
        repos_content += f"**关键字** {repo['keyword']}\n\n"
        repos_content += f"**介绍:** {repo_data['description']}\n\n"
        repos_content += f"**地址:** {repo_data['html_url']}\n\n"
        repos_content += "---\n\n"

    with open("found_repos.json", "w", encoding="utf-8") as json_file:
        json.dump(found_repos, json_file, indent=4, ensure_ascii=False)

    await send_repo_messages(
        telegram.Bot(TELEGRAM_BOT_API),
        [
            repo
            for repo_id, repo in sorted_repos
            if datetime.strptime(repo_data["created_at"], "%Y-%m-%dT%H:%M:%SZ")
            < three_days_ago
        ],
    )

    readme_content = (
        Path("readme_template.md")
        .read_text(encoding="utf-8")
        .format(repos=repos_content)
    )

    Path("README.md").write_text(readme_content, encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
