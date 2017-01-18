import logging
from github3 import GitHub
from goodtablesio import models, settings
from goodtablesio.celery_app import celery_app
from goodtablesio.utils.jobtask import JobTask
from goodtablesio.utils.jobconf import create_validation_conf
log = logging.getLogger(__name__)


# Module API

@celery_app.task(name='goodtablesio.github.get_validation_conf', base=JobTask)
def get_validation_conf(owner, repo, sha, job_id):
    """Celery tast to get validation conf.
    """

    # Update job
    models.job.update({
        'id': job_id,
        'status': 'running'
    })

    # Get validation conf
    job_base = _get_job_base(owner, repo, sha)
    job_files = _get_job_files(owner, repo, sha)
    validation_conf = create_validation_conf(job_base, job_files)

    return validation_conf


# Internal


def _get_job_base(owner, repo, sha):
    """Get job's base url.
    """
    template = '{base}/{owner}/{repo}/{sha}'
    baseurl = template.format(
        base='https://raw.githubusercontent.com',
        owner=owner, repo=repo, sha=sha)
    return baseurl


def _get_job_files(owner, repo, sha):
    """Get job's files.
    """
    github_api = GitHub(token=settings.GITHUB_API_TOKEN)
    repo_api = github_api.repository(owner, repo)
    # First attempt - use GitHub Tree API
    files = _get_job_files_tree_api(repo_api, sha)
    if files is None:
        # Tree is trancated - use GitHub Contents API
        files = _get_job_files_contents_api(repo_api, sha)
    log.debug(
        'Remaining GitHub API calls: %s',
        github_api.rate_limit()['rate']['remaining'])
    return files


def _get_job_files_tree_api(repo_api, sha):
    """Get job's files using GitHub Tree API.
    """
    files = []
    # https://github.com/sigmavirus24/github3.py/issues/656
    tree = repo_api.tree('%s?recursive=1' % sha).to_json()
    if tree['truncated']:
        return None
    for item in tree['tree']:
        if item['type'] == 'blob':
            files.append(item['path'])
    return files


def _get_job_files_contents_api(repo_api, sha, contents=None):
    """Get job's files using GitHub Contents API.
    """
    files = []
    if not contents:
        contents = repo_api.contents('', sha)
    for key in sorted(contents):
        item = contents[key]
        if item.type == 'file':
            files.append(item.path)
        elif item.type == 'dir':
            dir_contents = repo_api.contents(item.path, sha)
            files.extend(_get_job_files_contents_api(repo_api, sha, dir_contents))
    return files