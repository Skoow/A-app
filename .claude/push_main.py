#!/usr/bin/env python3
"""Pousse les fichiers modifiés vers main via l'API MCP GitHub."""
import glob, json, os, subprocess, sys, urllib.request

REPO_DIR = '/home/user/A-app'
OWNER    = 'skoow'
REPO     = 'a-app'
BRANCH   = 'main'

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_DIR).stdout.strip()

if int(run(['git', 'rev-list', 'origin/main..HEAD', '--count']) or '0') == 0:
    sys.exit(0)

# Fichiers modifiés avec leur statut (D=supprimé, autres=ajout/modif)
status_lines = [l for l in run(['git', 'diff', '--name-status', 'origin/main..HEAD']).split('\n') if l]
if not status_lines:
    sys.exit(0)

files   = []
deleted = []
for line in status_lines:
    parts = line.split('\t', 1)
    if len(parts) != 2:
        continue
    status, path = parts
    if status.startswith('D'):
        deleted.append(path)
    else:
        full = os.path.join(REPO_DIR, path)
        if os.path.exists(full):
            files.append({'path': path, 'content': open(full, encoding='utf-8').read()})

if not files and not deleted:
    sys.exit(0)

commit_msg = run(['git', 'log', '-1', '--pretty=%s']) or 'Update'

# Config MCP
cfg_files = sorted(glob.glob('/tmp/mcp-config-cse_*.json'))
if not cfg_files:
    print('Pas de config MCP trouvée', file=sys.stderr)
    sys.exit(1)

cfg     = json.load(open(cfg_files[-1]))
gh      = cfg['mcpServers']['github']
mcp_url = gh.get('url', '')
headers = gh.get('headers', {})
tok     = open('/home/claude/.claude/remote/.session_ingress_token').read().strip()

def mcp_call(name, arguments):
    payload = json.dumps({
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
        'params': {'name': name, 'arguments': arguments}
    }).encode()
    req = urllib.request.Request(mcp_url, data=payload)
    req.add_header('Content-Type', 'application/json')
    for k, v in headers.items():
        req.add_header(k, v)
    req.add_header('Authorization', f'Bearer {tok}')
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    for line in body.decode().splitlines():
        if line.startswith('data:'):
            try:
                return json.loads(line[5:].strip())
            except Exception:
                pass
    return json.loads(body)

try:
    if files:
        resp = mcp_call('push_files', {
            'owner': OWNER, 'repo': REPO, 'branch': BRANCH,
            'message': commit_msg, 'files': files
        })
        if 'error' in resp and not resp.get('result'):
            print(f'Erreur push_files: {resp}', file=sys.stderr)
            sys.exit(1)

    for path in deleted:
        resp = mcp_call('delete_file', {
            'owner': OWNER, 'repo': REPO, 'branch': BRANCH,
            'path': path, 'message': commit_msg
        })
        if 'error' in resp and not resp.get('result'):
            print(f'Erreur delete_file {path}: {resp}', file=sys.stderr)
            sys.exit(1)

    subprocess.run(['git', 'fetch', 'origin', 'main'], cwd=REPO_DIR)
    subprocess.run(['git', 'reset', '--hard', 'origin/main'], cwd=REPO_DIR)
    total = len(files) + len(deleted)
    print(f'Poussé {total} fichier(s) vers main via MCP ({len(deleted)} suppression(s))')
except Exception as e:
    print(f'Erreur: {e}', file=sys.stderr)
    sys.exit(1)
