# Copyright 2020 Open Source Robotics Foundation, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import datetime
import json
import sys

import keyring
import requests


class AuthorCounts:
    def __init__(self):
        self.total_commits = 0
        self.commits_in_last_year = 0
        self.total_reviews = 0
        self.reviews_in_last_year = 0


def get_commits(key, organization, repo_name, branch_name):
    history_args = ''

    bearer = 'Bearer %s' % key
    headers = {'Authorization': bearer}

    commits = []
    while True:
        query = '''
{
  repository(name: "%s", owner: "%s") {
    ref(qualifiedName: "%s") {
      target {
        ... on Commit {
          id
          history(first: 100%s) {
            pageInfo {
              hasNextPage
              endCursor
            }
            edges {
              node {
                author {
                  name
                  user {
                    login
                  }
                }
                authoredDate
              }
            }
          }
        }
      }
    }
  }
}''' % (repo_name, organization, branch_name, history_args)

        request = requests.post('https://api.github.com/graphql', json={'query': query}, headers=headers)
        if request.status_code != 200:
            raise Exception('GitHub GraphQL query failed with code {}.'.format(request.status_code))
        result = request.json()
        if not 'data' in result:
            raise Exception('GraphQL query returned unexpected data: %s' % (result))
        if not 'repository' in result['data'] or result['data']['repository'] is None:
            raise Exception('Repo https://github.com/{}/{} does not exist'.format(organization, repo_name))
        if not 'ref' in result['data']['repository'] or result['data']['repository']['ref'] is None:
            raise Exception('Repo https://github.com/{}/{} does not exist'.format(organization, repo_name))
        history = result['data']['repository']['ref']['target']['history']

        for edge in history['edges']:
            node = edge['node']
            if node['author']['user'] is not None:
                author = node['author']['user']['login']
            else:
                # It may be the case that GitHub can't match the author name
                # back to a GitHub account.  This can happen if the email
                # address in the commit doesn't match one that they have on
                # file for that committer.  In these cases, just take the author
                # name on the commit and use that.
                author = node['author']['name']
            commits.append({
                'author': author,
                'authoredDate': datetime.datetime.strptime(
                    node['authoredDate'], '%Y-%m-%dT%H:%M:%SZ').timestamp(),
            })

        if not history['pageInfo']['hasNextPage']:
            break
        history_args = ', after: "%s"' % history['pageInfo']['endCursor']

    return commits


def get_reviews(key, org_name, repo_name):
    pr_history_args = ''
    review_history_args = ''

    reviewers = []

    bearer = 'Bearer %s' % key
    headers = {'Authorization': bearer}

    while True:
        while True:
            query = '''
{
  repository(owner: "%s", name: "%s") {
    pullRequests(first:100%s) {
      pageInfo {
        hasNextPage,
        endCursor
      },
      nodes {
        id,
        number,
        author {
          login
        },
        reviews(first:100%s) {
          pageInfo {
            hasNextPage,
            endCursor
          },
          nodes {
            author {
              login
            },
            submittedAt,
          }
        },
      },
    },
  }
}''' % (org_name, repo_name, pr_history_args, review_history_args)

            request = requests.post('https://api.github.com/graphql', json={'query': query}, headers=headers)
            if request.status_code != 200:
                raise Exception('GitHub GraphQL query failed with code {}.'.format(request.status_code))
            result = request.json()
            prs = result['data']['repository']['pullRequests']['nodes']
            review_history_args = ''
            for pr in prs:
                # A PR author can be None if the account was deleted.
                if pr['author'] is None:
                    pr_author = ''
                else:
                    pr_author = pr['author']['login']
                reviews = pr['reviews']
                for review in reviews['nodes']:
                    # A review author can be None if the account was deleted.
                    if review['author'] is None:
                        continue

                    review_author = review['author']['login']
                    # Skip the review if it was by the author (this can happen
                    # if they either do their own review, or if they are
                    # responding to review comments).
                    if pr_author == review_author:
                        continue

                    # If the login you are using happens to have a started, but
                    # uncompleted review, then it shows up in the list of reviews
                    # with a "submittedAt" as "None".  Just skip these.
                    if review['submittedAt'] is None:
                        continue

                    reviewers.append({
                        'author': review_author,
                        'reviewDate': datetime.datetime.strptime(
                            review['submittedAt'], '%Y-%m-%dT%H:%M:%SZ').timestamp(),
                    })

                if reviews['pageInfo']['hasNextPage']:
                    review_history_args = ', after: "%s"' % pr['reviews']['pageInfo']['endCursor']
                    break

            if review_history_args == '':
                break

        pr_history = result['data']['repository']['pullRequests']
        if not pr_history['pageInfo']['hasNextPage']:
            break
        pr_history_args = ', after: "%s"' % pr_history['pageInfo']['endCursor']

    return reviewers

def get_org_repos_from_name(key, org_name):
    history_args = ''

    bearer = 'Bearer %s' % key
    headers = {'Authorization': bearer}

    repos = {}
    while True:
        query = '''
{
  organization(login: "%s") {
    repositories(first:100%s) {
      pageInfo {
        hasNextPage,
        endCursor
      },
      nodes {
        defaultBranchRef {
          name
        },
        name,
        isArchived
      }
    }
  }
}''' % (org_name, history_args)

        request = requests.post('https://api.github.com/graphql', json={'query': query}, headers=headers)
        if request.status_code != 200:
            raise Exception('GitHub GraphQL query failed with code {}.'.format(request.status_code))
        result = request.json()
        for repo in result['data']['organization']['repositories']['nodes']:
            repo_name = repo['name']
            if repo['defaultBranchRef'] is None:
                # This is likely an empty repository, so just skip it
                continue

            if repo['isArchived']:
                continue

            repos[repo_name] = repo['defaultBranchRef']['name']

        if not result['data']['organization']['repositories']['pageInfo']['hasNextPage']:
            break
        history_args = ', after: "%s"' % result['data']['organization']['repositories']['pageInfo']['endCursor']
    return repos

def print_authors(authors, print_totals):
    sorted_authors = {key: value for key, value in sorted(authors.items(), key=lambda item: item[1].commits_in_last_year + item[1].reviews_in_last_year, reverse=True)}

    author_with_space = 'Author                    '
    commits_with_space = 'Commits in last year  '
    total_commits_with_space = 'Total commits  '
    reviews_with_space = 'Reviews in last year  '
    total_reviews = 'Total reviews'

    print()

    if print_totals:
        print('%s%s%s%s%s' % (author_with_space, commits_with_space, total_commits_with_space, reviews_with_space, total_reviews))
        print('-'*(len(author_with_space) + len(commits_with_space) + len(total_commits_with_space) + len(reviews_with_space) + len(total_reviews)))
        for author,counts in sorted_authors.items():
            print('%s%s%d%s%d%s%d%s%d' % (author, ' '*(len(author_with_space) - len(author)), counts.commits_in_last_year, ' '*(len(commits_with_space) - len(str(counts.commits_in_last_year))), counts.total_commits, ' '*(len(total_commits_with_space) - len(str(counts.total_commits))), counts.reviews_in_last_year, ' '*(len(reviews_with_space) - len(str(counts.reviews_in_last_year))), counts.total_reviews))
    else:
        reviews_with_space = reviews_with_space.strip()
        print('%s%s%s' % (author_with_space, commits_with_space, reviews_with_space))
        print('-'*(len(author_with_space) + len(commits_with_space) + len(reviews_with_space)))
        for author,counts in sorted_authors.items():
            if counts.commits_in_last_year == 0 and counts.reviews_in_last_year == 0:
                continue
            print('%s%s%d%s%d' % (author, ' '*(len(author_with_space) - len(author)), counts.commits_in_last_year, ' '*(len(commits_with_space) - len(str(counts.commits_in_last_year))), counts.reviews_in_last_year))

    print()

def print_csv(authors, print_totals):
    sorted_authors = {key: value for key, value in sorted(authors.items(), key=lambda item: item[1].commits_in_last_year + item[1].reviews_in_last_year, reverse=True)}

    if print_totals:
        print('Author,Commits in last year,Total commits,Reviews in last year,Total reviews')
        for author,counts in sorted_authors.items():
            print('%s,%d,%d,%d,%d' % (author, counts.commits_in_last_year, counts.total_commits, counts.reviews_in_last_year, counts.total_reviews))
    else:
        print('Author,Commits in last year,Reviews in last year')
        for author,counts in sorted_authors.items():
            if counts.commits_in_last_year == 0 and counts.reviews_in_last_year == 0:
                continue
            print('%s,%d,%d' % (author, counts.commits_in_last_year, counts.reviews_in_last_year))
    print()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--show-totals', help='Show the all time stats along with the last year', action='store_true', default=False)
    parser.add_argument('--csv', help='Output the data in CSV format', action='store_true', default=False)
    parser.add_argument('org', nargs=1, help='Which GitHub organization to collect statistics for', action='store')
    args = parser.parse_args()

    key = keyring.get_password('github-read-org', 'may-read-org')
    if key is None:
        raise RuntimeError('Failed to get GitHub API key')

    today = datetime.datetime.now()
    one_year_ago_timestamp = (today - datetime.timedelta(days=365)).timestamp()

    org_name = args.org[0]
    org_repos = get_org_repos_from_name(key, org_name)
    print('Data as of', today)
    for repo_name, branch in org_repos.items():
        print(repo_name)
        authors = {}
        reviews = get_reviews(key, org_name, repo_name)
        for review in reviews:
            if not review['author'] in authors:
                authors[review['author']] = AuthorCounts()

            authors[review['author']].total_reviews += 1
            if review['reviewDate'] >= one_year_ago_timestamp:
                authors[review['author']].reviews_in_last_year += 1

        commits = get_commits(key, org_name, repo_name, branch)
        for commit in commits:
            if not commit['author'] in authors:
                authors[commit['author']] = AuthorCounts()

            authors[commit['author']].total_commits += 1
            if commit['authoredDate'] >= one_year_ago_timestamp:
                authors[commit['author']].commits_in_last_year += 1

        if args.csv:
            print_csv(authors, args.show_totals)
        else:
            print_authors(authors, args.show_totals)


if __name__ == '__main__':
    sys.exit(main())
