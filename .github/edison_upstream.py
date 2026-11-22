"""Stage a reviewed set of upstream paths without running or merging upstream workflows."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

UPSTREAM = 'Thronior/ygo-rogue-duelist'
BASE = 'edison/android-three-acts'
BASE_TAG = 'v0.2.40'
BASE_SHA = '65eae023ea95b26ea0cc57be8b2d4ce80dc6908f'
STATE = 'docs/edison-upstream-state.json'
REVIEW = 'docs/edison-upstream-review.md'
SAFE_GROUPS = (
    ('tools/pwa/pwa-storage.js', 'tools/pwa/test_storage_quota.mjs'),
    ('android/web/card-search.js', 'android/web/i18n.js', 'android/test_translated_search.mjs'),
    ('android/web/deck_policy.js',),
)


def run(*args, cwd=None, payload=None, check=True):
    return subprocess.run(args, cwd=cwd, input=payload, capture_output=True, check=check)


def out(*args, cwd=None):
    return run(*args, cwd=cwd).stdout.decode('utf8').strip()


def numeric(tag):
    if not re.fullmatch(r'v(0|[1-9][0-9]{0,4})(\.(0|[1-9][0-9]{0,4})){2}', tag):
        raise ValueError(f'Unexpected upstream tag {tag!r}')
    return tuple(map(int, tag[1:].split('.')))


def emit(branch='', pr='', commit=''):
    print(f'Candidate branch: {branch or "none"}')
    print(f'Draft PR: {pr or "none"}')
    if output := os.environ.get('GITHUB_OUTPUT'):
        with open(output, 'a', encoding='utf8') as file:
            file.write(f'branch={branch}\npr={pr}\ncommit={commit}\n')


def stage(repo, tag=None):
    release_path = f'tags/{tag}' if tag else 'latest'
    release = json.loads(out('gh', 'api', f'repos/{UPSTREAM}/releases/{release_path}'))
    if release['draft'] or release['prerelease']:
        raise ValueError('Only published stable upstream releases can be staged.')
    tag = release['tag_name']
    target_version = numeric(tag)
    base_ref = f'refs/remotes/origin/{BASE}'
    out('git', 'fetch', '--no-tags', 'origin', f'refs/heads/{BASE}:{base_ref}')
    existing = run('git', 'show', f'{base_ref}:{STATE}', check=False)
    baseline = json.loads(existing.stdout) if existing.returncode == 0 else {
        'lastIncorporatedTag': BASE_TAG, 'lastIncorporatedCommit': BASE_SHA
    }
    last_tag, last_sha = baseline['lastIncorporatedTag'], baseline['lastIncorporatedCommit']
    if target_version <= numeric(last_tag):
        print(f'{tag} is already covered by {last_tag}.')
        emit()
        return
    if not re.fullmatch('[0-9a-f]{40}', last_sha):
        raise ValueError('Invalid upstream baseline commit.')
    target_ref = f'refs/edison-upstream/{tag}'
    upstream_url = f'https://github.com/{UPSTREAM}.git'
    out('git', 'fetch', '--no-tags', upstream_url, f'refs/tags/{tag}:{target_ref}')
    target_sha = out('git', 'rev-parse', target_ref + '^{commit}')
    if run('git', 'cat-file', '-e', last_sha, check=False).returncode:
        out('git', 'fetch', '--no-tags', upstream_url, last_sha)
    if run('git', 'merge-base', '--is-ancestor', last_sha, target_sha, check=False).returncode:
        raise ValueError('The upstream release does not descend from the recorded baseline.')
    branch = f'edison/upstream/{tag}'
    candidate_ref = f'refs/remotes/origin/{branch}'
    if out('git', 'ls-remote', '--heads', 'origin', f'refs/heads/{branch}'):
        out('git', 'fetch', '--no-tags', 'origin', f'refs/heads/{branch}:{candidate_ref}')
        saved = json.loads(out('git', 'show', f'{candidate_ref}:{STATE}'))
        if saved['lastIncorporatedCommit'] != target_sha:
            raise ValueError('Existing candidate points at a different upstream commit.')
    else:
        with tempfile.TemporaryDirectory(prefix='edison-stage-') as directory:
            worktree = Path(directory)/'candidate'
            out('git', 'worktree', 'add', '--detach', str(worktree), base_ref)
            try:
                make_candidate(worktree, tag, target_sha, last_tag, last_sha)
                out('git', 'push', 'origin', f'HEAD:refs/heads/{branch}', cwd=worktree)
            finally:
                out('git', 'worktree', 'remove', '--force', str(worktree))

    prs = json.loads(out('gh', 'pr', 'list', '-R', repo, '--state', 'all', '--base', BASE,
                         '--head', branch, '--json', 'url,state'))
    pr = prs[0]['url'] if prs else out(
        'gh', 'pr', 'create', '-R', repo, '--base', BASE, '--head', branch, '--draft',
        '--title', f'Review Thronior {tag} for Edison',
        '--body', f'Review the candidate and regression run before merging. The changes and remaining upstream paths are listed in `{REVIEW}`. This work never publishes an APK.')
    commit = out('git', 'ls-remote', '--heads', 'origin', f'refs/heads/{branch}').split()[0]
    emit(branch, pr, commit)


def make_candidate(worktree, tag, target, last_tag, baseline):
    changed = set(out('git', 'diff', '--name-only', baseline, target).splitlines())
    applied = set()
    conflicts = set()
    for group in SAFE_GROUPS:
        paths = sorted(changed.intersection(group))
        if not paths:
            continue
        types = [out('git', 'ls-tree', target, '--', path).split()[:2] for path in paths]
        patch = run('git', 'diff', '--no-ext-diff', '--binary', baseline, target, '--', *paths).stdout
        if any(entry != ['100644', 'blob'] for entry in types) or not patch or run(
                'git', 'apply', '--index', '--check', cwd=worktree, payload=patch, check=False).returncode:
            conflicts.update(paths)
            continue
        run('git', 'apply', '--index', cwd=worktree, payload=patch)
        applied.update(paths)

    state = {'lastIncorporatedTag': tag, 'lastIncorporatedCommit': target,
             'previousTag': last_tag, 'appliedPaths': sorted(applied)}
    path = worktree/STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + '\n', encoding='utf8')
    sections = [f'# Review of Thronior {tag}', '',
                f'[Upstream release](https://github.com/{UPSTREAM}/releases/tag/{tag})',
                '', f'Compared {last_tag} with upstream commit `{target}`. '
                'The candidate retains Edison’s campaign, roster, saves, app identity, and release process.', '']
    for title, paths in [('Compatible candidates', applied), ('Patch conflicts', conflicts),
                         ('Deferred for review', changed - applied - conflicts)]:
        sections.extend((f'## {title}', ''))
        sections.extend([f'- `{path}`' for path in sorted(paths)] or ['None.'])
        sections.append('')
    (worktree/REVIEW).write_text('\n'.join(sections), encoding='utf8')
    out('git', 'add', '--', STATE, REVIEW, cwd=worktree)
    out('git', '-c', 'user.name=Edison release monitor', '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
        'commit', '-m', f'Stage compatible changes from Thronior {tag}', cwd=worktree)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True)
    parser.add_argument('--tag')
    args = parser.parse_args()
    if args.tag:
        numeric(args.tag)
    try:
        stage(args.repo, args.tag)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr.decode('utf8', errors='replace') or f'Command exited {error.returncode}') from None
