#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Generate the cd2.arthurlin.dev payload from the cloned repo:
  out/index.html   (copied from this folder)
  out/data.json    (grouped: series + version families)
  out/files/*.cd2.json (raw, for copy/download)

Grouping:
  - version family: strip a trailing version token (v1.20 / _v2.3 / [B11] / v0.2)
    to get a `base`; difficulties sharing a base collapse into one card with a
    version selector.
  - series: a family tag (DL / Death / Hazard / ...) for the top filter chips.
A small OVERRIDE map fixes names the heuristics guess wrong.
"""
import json, os, sys, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
repo = sys.argv[1]
out  = sys.argv[2]
diff_dir  = os.path.join(repo, 'difficulties')
files_out = os.path.join(out, 'files')
os.makedirs(files_out, exist_ok=True)

# --- per-name overrides (exact full name -> {"series":..,"base":..,"version":..}) ---
OVERRIDE = {}

# --- series rules (first match wins); matched against the base name ---
SERIES_RULES = [
    (r'(?i)^DL\b',                         'DL'),
    (r'(?i)^Death\b',                      'Death'),
    (r'(?i)^ENND',                         'ENND'),
    (r'(?i)interstellar',                  'Interstellar'),
    (r'(?i)myriad',                        'Myriad'),
    (r'(?i)(爬山|mountain climbing|climbing)', 'Climbing'),
    (r'(?i)^send\s*it',                    'Send It'),
    (r'(?i)^(hazard|ハザード)',             'Hazard'),
    (r'^ND($|[\s\-])',                     'ND'),
    (r'(?i)^FC[_\s]',                      'FC'),
    (r'(?i)^EX_',                          'EX'),
]

# trailing version tokens -> (base, version_label)
VER_PATTERNS = [
    re.compile(r'^(.*?)[\s_]*\[([0-9A-Za-z]+)\]\s*$'),          # [B11] [A21]
    re.compile(r'^(.*?)[\s_]+[vV](\d+(?:\.\d+)+)\s*$'),         # v1.20  _v2.3  v0.2
]

def split_version(name):
    for i, pat in enumerate(VER_PATTERNS):
        m = pat.match(name)
        if m and m.group(1).strip():
            label = m.group(2) if i == 0 else 'v' + m.group(2)   # [B11] vs v1.69
            return m.group(1).strip(), label
    return name, None

def series_of(base):
    for pat, tag in SERIES_RULES:
        if re.search(pat, base):
            return tag
    return 'Other'

def ver_key(v):
    if not v:
        return (0,)
    nums = re.findall(r'\d+', v)
    return tuple(int(x) for x in nums) if nums else (0,)

def stat(obj, *keys):
    for k in keys:
        if isinstance(obj, dict) and obj.get(k) not in (None, ''):
            return obj[k]
    return None

# --- read difficulties ---
families = {}   # base -> {series, versions:[entry,...]}
keep = set()
for fn in sorted(os.listdir(diff_dir)):
    if not fn.endswith('.cd2.json'):
        continue
    raw = open(os.path.join(diff_dir, fn), encoding='utf-8').read()
    try:
        obj = json.loads(raw, strict=False)
    except Exception:
        obj = {}
    name = stat(obj, 'Name') or fn[:-9]

    ov = OVERRIDE.get(name, {})
    if 'base' in ov:
        base, ver = ov['base'], ov.get('version')
    else:
        base, ver = split_version(name)
    series = ov.get('series') or series_of(base)

    entry = {
        'version': ver or '原版 base',
        'vkey': ver_key(ver),
        'name': name,
        'file': fn,
        'description': (stat(obj, 'Description') or '').strip(),
        'resupply': stat(obj, 'ResupplyCost', 'Resupply'),
        'enemyCount': stat(obj, 'EnemyCountModifier'),
        'enemyDamage': stat(obj, 'EnemyDamageModifier'),
    }
    fam = families.setdefault(base, {'series': series, 'versions': []})
    fam['versions'].append(entry)

    dst = os.path.join(files_out, fn); keep.add(fn)
    if not (os.path.exists(dst) and open(dst, encoding='utf-8').read() == raw):
        open(dst, 'w', encoding='utf-8', newline='\n').write(raw)

for f in os.listdir(files_out):
    if f not in keep:
        os.remove(os.path.join(files_out, f))

# --- build groups (newest version first) ---
groups = []
for base, fam in families.items():
    vers = sorted(fam['versions'], key=lambda e: e['vkey'], reverse=True)
    for e in vers:
        e.pop('vkey', None)
    groups.append({'base': base, 'series': fam['series'], 'versions': vers})
groups.sort(key=lambda g: g['base'].lower())

# --- series chips: count by total difficulties; singletons -> Other ---
total_by_series = {}
for g in groups:
    total_by_series[g['series']] = total_by_series.get(g['series'], 0) + len(g['versions'])
for g in groups:
    if g['series'] != 'Other' and total_by_series[g['series']] < 2:
        g['series'] = 'Other'
counts = {}
for g in groups:
    counts[g['series']] = counts.get(g['series'], 0) + len(g['versions'])
series = sorted([{'name': s, 'count': c} for s, c in counts.items() if s != 'Other'],
                key=lambda x: (-x['count'], x['name']))
if 'Other' in counts:
    series.append({'name': 'Other', 'count': counts['Other']})

try:
    updated = subprocess.check_output(
        ['git', '-C', repo, 'log', '-1', '--date=format:%Y-%m-%d %H:%M', '--format=%cd'],
        text=True).strip()
except Exception:
    updated = ''

total = sum(len(g['versions']) for g in groups)
data = {'updated': updated, 'count': total, 'groupCount': len(groups),
        'series': series, 'groups': groups}
open(os.path.join(out, 'data.json'), 'w', encoding='utf-8', newline='\n').write(
    json.dumps(data, ensure_ascii=False, indent=1))

# copy static index.html from this folder
import shutil
shutil.copyfile(os.path.join(HERE, 'index.html'), os.path.join(out, 'index.html'))

print(f"built {total} difficulties in {len(groups)} cards, "
      f"{len(series)} series chips (updated {updated})")
