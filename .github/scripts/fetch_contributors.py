import os
import requests
import json
import re
from collections import defaultdict

# --- Configuration ---
ORG_NAME = os.getenv('ORG_NAME', 'open-simples') # Default org
INDEX_FILE_PATH = 'index.html'
CONTRIBUTORS_START_MARKER = '<!-- CONTRIBUTORS START -->'
CONTRIBUTORS_END_MARKER = '<!-- CONTRIBUTORS END -->'
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
# Get addon repos from environment variable (passed as JSON string)
try:
    ADDON_REPOS = json.loads(os.getenv('ADDON_REPOS', '[]'))
except json.JSONDecodeError:
    ADDON_REPOS = []
# Get hidden repos from environment variable
try:
    HIDDEN_REPOS = json.loads(os.getenv('HIDDEN_REPOS', '[]'))
except json.JSONDecodeError:
    HIDDEN_REPOS = []

GITHUB_API_URL = 'https://api.github.com'
HEADERS = {
    'Accept': 'application/vnd.github.v3+json',
    'Authorization': f'token {GITHUB_TOKEN}'
}

# Helper to check if a repo should be hidden
def is_hidden(repo_owner, repo_name, hidden_list):
    for hidden in hidden_list:
        if (repo_owner.lower() == hidden['user'].lower() and
                repo_name.lower() == hidden['repo'].lower()):
            return True
    return False

# --- Fetching Functions ---
def fetch_paginated_data(url):
    """Fetches all pages for a given GitHub API endpoint."""
    results = []
    while url:
        print(f"Fetching: {url}")
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            results.extend(response.json())
            # Check for next page link
            url = response.links.get('next', {}).get('url')
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}")
            break # Stop pagination on error
        except json.JSONDecodeError as e:
             print(f"Error decoding JSON from {url}: {e}")
             break
    return results

def get_all_repos(org_name, addon_repos_list, hidden_repos_list):
    """Gets all repos from the org and addons, filtering hidden ones."""
    all_repo_urls = set()
    repos_data = {} # Store owner/name

    # 1. Fetch Org Repos
    org_repos_url = f"{GITHUB_API_URL}/orgs/{org_name}/repos?type=public&per_page=100"
    org_repos = fetch_paginated_data(org_repos_url)
    for repo in org_repos:
        owner = repo['owner']['login']
        name = repo['name']
        if not is_hidden(owner, name, hidden_repos_list):
             contributors_url = repo.get('contributors_url')
             if contributors_url:
                 all_repo_urls.add(contributors_url)
                 repos_data[contributors_url] = {'owner': owner, 'name': name}


    # 2. Fetch Addon Repos
    for repo_info in addon_repos_list:
        user = repo_info['user']
        repo_name = repo_info['repo']
        if not is_hidden(user, repo_name, hidden_repos_list):
            repo_url = f"{GITHUB_API_URL}/repos/{user}/{repo_name}"
            print(f"Fetching addon repo info: {repo_url}")
            try:
                response = requests.get(repo_url, headers=HEADERS, timeout=10)
                response.raise_for_status()
                repo_data = response.json()
                contributors_url = repo_data.get('contributors_url')
                if contributors_url and contributors_url not in all_repo_urls: # Avoid duplicates
                    all_repo_urls.add(contributors_url)
                    repos_data[contributors_url] = {'owner': user, 'name': repo_name}
            except requests.exceptions.RequestException as e:
                print(f"Error fetching addon repo {user}/{repo_name}: {e}")
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON for addon repo {user}/{repo_name}: {e}")


    print(f"Found {len(all_repo_urls)} unique repos to check for contributors.")
    return list(all_repo_urls) # Return list of contributor URLs

def get_contributors(repo_contributors_urls):
    """Fetches contributors from a list of repo contributor URLs."""
    contributors = set()
    for url in repo_contributors_urls:
        print(f"Fetching contributors from: {url}")
        repo_contributors = fetch_paginated_data(url)
        for contributor in repo_contributors:
            login = contributor.get('login')
            # Exclude bots like github-actions[bot] or dependabot[bot]
            if login and not login.endswith('[bot]'):
                contributors.add(login)
    return sorted(list(contributors), key=str.lower) # Sort case-insensitively

# --- File Update Function ---
def update_index_file(contributors):
    """Updates the index.html file with the contributor list."""
    try:
        with open(INDEX_FILE_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: {INDEX_FILE_PATH} not found.")
        return

    # Create the HTML string for contributors
    if contributors:
        # Simple comma-separated list with links for this example
        contributors_html = ' '.join(
            f'<a href="https://github.com/{login}" target="_blank" rel="noopener noreferrer">{login}</a>'
            for login in contributors
        )
        # Add separators (e.g., ·)
        contributors_html = contributors_html.replace('</a> <a', '</a> · <a')
    else:
        contributors_html = "No contributors found or error fetching data."

    # Use regex to replace content between markers
    # re.DOTALL makes '.' match newline characters
    pattern = re.compile(f"({re.escape(CONTRIBUTORS_START_MARKER)}).*?({re.escape(CONTRIBUTORS_END_MARKER)})", re.DOTALL)

    # Check if markers exist
    if not pattern.search(content):
        print(f"Error: Markers {CONTRIBUTORS_START_MARKER} and {CONTRIBUTORS_END_MARKER} not found in {INDEX_FILE_PATH}.")
        return

    new_content = pattern.sub(f"\\1\n{contributors_html}\n\\2", content, count=1) # Replace only the first occurrence

    if new_content != content:
        print("Updating contributors section in index.html...")
        try:
            with open(INDEX_FILE_PATH, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print("index.html updated successfully.")
        except IOError as e:
            print(f"Error writing to {INDEX_FILE_PATH}: {e}")
    else:
        print("No changes detected in contributor list.")


# --- Main Execution ---
if __name__ == "__main__":
    if not GITHUB_TOKEN:
        print("Error: GITHUB_TOKEN environment variable not set.")
    else:
        repo_urls = get_all_repos(ORG_NAME, ADDON_REPOS, HIDDEN_REPOS)
        if repo_urls:
            unique_contributors = get_contributors(repo_urls)
            print(f"\nFound {len(unique_contributors)} unique contributors: {', '.join(unique_contributors)}")
            update_index_file(unique_contributors)
        else:
             print("No repositories found to fetch contributors from.") 