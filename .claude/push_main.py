#!/usr/bin/env python3
"""Pousse les fichiers modifiés vers main via l'API MCP GitHub."""
import glob, json, os, subprocess, sys, urllib.request

REPO_DIR = '/home/user/A-app'
OWNER    = 'skoow'
REPO     = 'a-app'
BRANCH   = 'main'

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_DIR).stdout.strip()

# Rien à pousser ?
if int(run(['git', 'rev-list', 'origin/main..HEAD', '--count']) or '0') == 0:
    sys.exit(0)

# Fichiers modifiés entre origin/main et HEAD
changed = [f for f in run(['git', 'diff', '--name-only', 'origin/main..HEAD']).split('\n') if f]
if not changed:
    sys.exit(0)

files = []
for path in changed:
    full = os.path.join(REPO_DIR, path)
    if os.path.exists(full):
        files.append({'path': path, 'content': open(full, encoding='utf-8').read()})

if not files:
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

tok = open('/home/claude/.claude/remote/.session_ingress_token').read().strip()

payload = json.dumps({
    'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
    'params': {
        'name': 'push_files',
        'arguments': {
            'owner': OWNER, 'repo': REPO, 'branch': BRANCH,
            'message': commit_msg, 'files': files
        }
    }
}).encode()

req = urllib.request.Request(mcp_url, data=payload)
req.add_header('Content-Type', 'application/json')
for k, v in headers.items():
    req.add_header(k, v)
req.add_header('Authorization', f'Bearer {tok}')

try:
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read())
        if resp.get('result') or 'error' not in resp:
            # Sync local avec le remote mis à jour
            subprocess.run(['git', 'fetch', 'origin', 'main'], cwd=REPO_DIR)
            subprocess.run(['git', 'reset', '--hard', 'origin/main'], cwd=REPO_DIR)
            print(f'Poussé {len(files)} fichier(s) vers main via MCP')
        else:
            print(f'Erreur MCP: {resp}', file=sys.stderr)
            sys.exit(1)
except Exception as e:
    print(f'Erreur: {e}', file=sys.stderr)
    sys.exit(1)
