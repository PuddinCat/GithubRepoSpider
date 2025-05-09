import os
from datetime import datetime, timedelta
import asyncio

import jsonschema
import httpx

from search_response_scheme import JSON_SCHEMA


# Replace with your GitHub personal access token
GITHUB_TOKEN = os.environ["GITHUB_API_TOKEN"]
GITHUB_API_URL = "https://api.github.com/search/repositories"


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
    keywords = [
        "CVE-2025",
    ]
    created_time_since = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    search_results = await asyncio.gather(
        *[
            search_github_repositories(f"{keyword} created:>{created_time_since}")
            for keyword in keywords
        ]
    )
    for keyword, repos in zip(keywords, search_results):
        if not repos:
            print(f"Search {keyword} failed")
            continue
        for repo in repos:
            created_at = datetime.strptime(repo["created_at"], "%Y-%m-%dT%H:%M:%SZ")
            print(
                f"Name: {repo['name']}, Author: {repo['owner']['login']}, "
                f"Stars: {repo['stargazers_count']}, Created At: {created_at}, "
                f"Description: {repo['description']}"
            )


if __name__ == "__main__":
    asyncio.run(main())
