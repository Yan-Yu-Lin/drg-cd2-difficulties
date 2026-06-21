#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Decode Deep Rock Galactic "Custom Difficulty 2" save (CD2.sav, an Unreal GVAS
save) into one human/LLM-readable .cd2.json file per difficulty, plus a README
index. Output is deterministic so git diffs only show what actually changed.

Usage:
    decode_cd2.py <CD2.sav path> <repo root>
"""
import struct, json, os, sys, re, hashlib

def read_fstring(data, o):
    n = struct.unpack_from('<i', data, o)[0]; o += 4
    if n == 0:
        return "", o
    if n > 0:
        return data[o:o+n-1].decode('utf-8', 'replace'), o + n
    n = -n
    return data[o:o+2*n-2].decode('utf-16le', 'replace'), o + 2*n

def parse_difficulties(data):
    # locate the `Difficulties` MapProperty by its exact FString encoding
    needle = struct.pack('<i', 13) + b'Difficulties\x00'
    idx = data.find(needle)
    if idx < 0:
        raise SystemExit("ERROR: 'Difficulties' MapProperty not found — is this a CD2.sav?")
    o = idx
    _key, o = read_fstring(data, o)        # "Difficulties"
    typ, o  = read_fstring(data, o)        # "MapProperty"
    if typ != "MapProperty":
        raise SystemExit(f"ERROR: expected MapProperty, got {typ!r}")
    o += 8                                  # int64 size (skip)
    _kt, o = read_fstring(data, o)          # "StrProperty"
    _vt, o = read_fstring(data, o)          # "StrProperty"
    o += 1                                   # has-guid byte
    o += 4                                   # NumKeysRemoved (int32)
    count = struct.unpack_from('<i', data, o)[0]; o += 4
    out = {}
    for _ in range(count):
        k, o = read_fstring(data, o)
        v, o = read_fstring(data, o)
        out[k] = v
    return out

def safe_filename(name):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    s = s.rstrip(' .')
    return (s or 'unnamed')[:120]

def main():
    save_path = sys.argv[1] if len(sys.argv) > 1 else \
        r"C:\Program Files (x86)\Steam\steamapps\common\Deep Rock Galactic\FSD\Saved\SaveGames\Mods\CD2.sav"
    repo = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
    data = open(save_path, 'rb').read()
    raw = parse_difficulties(data)

    diff_dir = os.path.join(repo, 'difficulties')
    os.makedirs(diff_dir, exist_ok=True)

    # collisions: append short hash of original name
    used = {}
    parsed = {}   # original name -> (filename, json-obj-or-None, raw-text)
    for name, val in raw.items():
        fn = safe_filename(name)
        if fn in used and used[fn] != name:
            fn = f"{fn}_{hashlib.sha1(name.encode()).hexdigest()[:6]}"
        used[fn] = name
        try:
            obj = json.loads(val, strict=False)
        except Exception:
            obj = None
        parsed[name] = (fn + '.cd2.json', obj, val)

    wanted = set()
    for name, (fname, obj, val) in parsed.items():
        wanted.add(fname)
        text = (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
                if obj is not None else val) + "\n"
        path = os.path.join(diff_dir, fname)
        # write only if changed (keeps mtimes stable)
        if not (os.path.exists(path) and open(path, encoding='utf-8').read() == text):
            open(path, 'w', encoding='utf-8', newline='\n').write(text)

    # remove difficulties no longer in the save
    removed = []
    for existing in os.listdir(diff_dir):
        if existing.endswith('.cd2.json') and existing not in wanted:
            os.remove(os.path.join(diff_dir, existing)); removed.append(existing)

    # README index (sorted by name for stable diffs)
    cd2_hash = hashlib.sha256(data).hexdigest()[:8]
    lines = [
        "# DRG — Custom Difficulty 2 library",
        "",
        f"Auto-exported from `CD2.sav` ({len(parsed)} difficulties). "
        "Each `.cd2.json` in `difficulties/` is one difficulty you can paste/import into the "
        "Custom Difficulty 2 mod in Deep Rock Galactic.",
        "",
        "> This repo is updated automatically by a watcher on the gaming PC: every time a "
        "difficulty is added/edited/removed in-game, a new commit is made. Do not edit by hand.",
        "",
        "| Difficulty | Description | Resupply | EnemyCountModifier |",
        "|---|---|---|---|",
    ]
    for name in sorted(parsed, key=str.lower):
        _fn, obj, _val = parsed[name]
        desc = ""
        resup = ecm = ""
        if obj:
            desc = (obj.get('Description') or "").replace("\n", " ").strip()
            desc = re.sub(r'\s+', ' ', desc)[:80]
            resup = obj.get('ResupplyCost', obj.get('Resupply', ''))
            ecm = obj.get('EnemyCountModifier', '')
        nm = name.replace("|", "\\|")
        lines.append(f"| {nm} | {desc} | {resup} | {ecm} |")
    lines.append("")
    open(os.path.join(repo, 'README.md'), 'w', encoding='utf-8', newline='\n').write("\n".join(lines))

    print(f"OK: {len(parsed)} difficulties written, {len(removed)} removed, cd2={cd2_hash}")

if __name__ == "__main__":
    main()
