# GitHub organization contributions

This repository contains scripts to determine who is contributing to the repositories in a given GitHub organization.
It works by using the GitHub GraphQL query interface to fetch all of the commits and reviews done by all users to all repositories in an organization.
It then displays that information in human-readable or machine-readable form (see the Usage below for more details).
Because it uses the GraphQL query interface, it is very query-efficient even in the face of large numbers of repositories and commits.

# Requirements

* Python 3
* python3-keyring
* python3-requests

# Setup

For this script to work, you must setup a GitHub API token and use the 'keyring' package to store it locally.
The script will then fetch the token when it runs.

In the GitHub "Developer settings", create a new Personal Access Token that has the `read:org` permissions (and nothing else) enabled.
Make sure to copy the hash that is given to you when you create the token.
Locally, run:

```
keyring set github-read-org may-read-org
```

When it asks for a password, paste in the hash that was given above.

# Usage

```
usage: github-org-contributions.py [-h] [--show-totals] [--csv] org

positional arguments:
  org            Which GitHub organization to collect statistics for

optional arguments:
  -h, --help     show this help message and exit
  --show-totals  Show the all time stats along with the last year
  --csv          Output the data in CSV format
```

The one required argument is the GitHub organization from which to collect statistics.
This is just the name of the org; for instance, to query the https://github.com/ament organization, you would pass 'ament' here.

When run without any additional arguments, the script will collect all of the data from all of the repositories and print out who committed or reviewed to each repository in the last year.

If the `--show-totals` option is given, then the script will print out information about anyone who has ever contributed.

If the `--csv` option is given, then the script will print the data in a Comma-Separated-Value format, useful for importing into a spreadsheet.

# Potential issues

* The "number of reviews" metric is calculated by counting *every* review comment a username made in the last year.  This number may give a skewed impression of someone's contributions if they commented heavily on one issue/pull request, but never touched any others.
* Currently the amount of time to look into the past is hard-coded at one year; it might be nice to make this configurable.
