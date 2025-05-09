import os
from datetime import datetime
import asyncio

import jsonschema
import httpx

from search_response_scheme import JSON_SCHEMA


# Replace with your GitHub personal access token
GITHUB_TOKEN = os.environ["GITHUB_API_TOKEN"]
GITHUB_API_URL = "https://api.github.com/search/repositories"


async def search_github_repositories(query, sort="stars", order="desc"):
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    params = {"q": query, "sort": sort, "order": order}
    async with httpx.AsyncClient() as client:
        resp = await client.get(GITHUB_API_URL, headers=headers, params=params)
        if resp.status_code == 200:
            data = resp.json()
            try:
                jsonschema.validate(instance=data, schema=JSON_SCHEMA)
                return data
            except jsonschema.ValidationError as e:
                print(f"JSON Schema validation error: {e}")
                return None
        else:
            print(f"Error: {resp.status_code}, {resp.text}")
            return None


async def main():
    query = input("Enter search query: ")
    results = await search_github_repositories(query)
    if results:
        for repo in results["items"]:
            created_at = datetime.strptime(repo["created_at"], "%Y-%m-%dT%H:%M:%SZ")
            print(
                f"Name: {repo['name']}, Author: {repo['owner']['login']}, "
                f"Stars: {repo['stargazers_count']}, Created At: {created_at}, "
                f"Description: {repo['description']}"
            )


if __name__ == "__main__":
    asyncio.run(main())
