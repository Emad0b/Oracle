"""Audit Git's staged tree / HEAD and export source only, never the working folder.

This is a release guard, not a substitute for reviewing the diff before publishing.
"""
import argparse
import io
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile


ROOT_FILES = {'.env.example', '.gitignore', 'README.md', 'BACKLOG.md', 'oracle.py', 'requirements.txt', 'LICENSE'}
FOLDERS = {'app', 'tests', 'static', 'scripts', 'docs'}
EXTENSIONS = {'.py', '.md', '.txt', '.js', '.css', '.html'}
PATTERNS = {
    'API credential': r'(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|GOCSPX-[A-Za-z0-9_-]{15,}|ya29\.[A-Za-z0-9_-]{20,})',
    'private key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'Google client ID': r'\d{8,}-[a-z0-9]+\.apps\.googleusercontent\.com',
    'personal email': r'[\w.+-]+@(?:gmail|hotmail|outlook|yahoo|icloud)\.[a-z]+',
    'personal Windows path': r'[A-Za-z]:[\\/]+Users[\\/]+(?!Public\b|<)[A-Za-z0-9_.-]+',
}


def git(*args):
    return subprocess.check_output(['git', *args])


def validate(files):
    problems = []
    for name, data in files.items():
        path = PurePosixPath(name)
        if name not in ROOT_FILES and not (len(path.parts) >= 2 and path.parts[0] in FOLDERS and path.suffix in EXTENSIONS):
            problems.append(f'{name}: not in source allowlist')
            continue
        if any(part.startswith('.') for part in path.parts) and name not in {'.env.example', '.gitignore'}:
            problems.append(f'{name}: hidden file')
        try:
            source = data.decode('utf-8')
        except UnicodeDecodeError:
            problems.append(f'{name}: non-text content')
            continue
        for label, pattern in PATTERNS.items():
            if re.search(pattern, source, re.IGNORECASE):
                problems.append(f'{name}: possible {label}')
    if problems:
        raise ValueError('\n'.join(problems))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--index', action='store_true', help='Audit exactly the staged tree.')
    parser.add_argument('--output', type=Path, help='Write a reviewed HEAD source zip to a NEW file.')
    args = parser.parse_args()
    if args.index:
        names = git('ls-files', '-z').decode().split('\0')
        files = {name: git('show', ':' + name) for name in names if name}
    else:
        archive = git('archive', '--format=zip', 'HEAD')
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            files = {name: bundle.read(name) for name in bundle.namelist() if not name.endswith('/')}
    validate(files)
    print(f'Privacy guard passed: {len(files)} allowlisted source files; no matching secret or personal-data patterns.')
    if args.output:
        if args.index:
            parser.error('Export committed HEAD only, not the index.')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.output, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
            for name, data in sorted(files.items()):
                bundle.writestr('Oracle/' + name, data)
        print(f'Source-only release written: {args.output}')


if __name__ == '__main__':
    main()
