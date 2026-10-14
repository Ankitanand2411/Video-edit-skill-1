#!/usr/bin/env python3
"""Read a storyboard spreadsheet (.xlsx) into <project>/storyboard.json and pull its pictures out untouched.

Usage:  PY storyboard.py <project_dir> <storyboard.xlsx>

Expected sheet (one row per scene, header row names the columns, any order):
  SCENE | STORYBOARD (text with VISUALS: / SUPER: / SCRIPT / VO: blocks) | REFERENCE (a picture anchored in the row)
  plus optional BRAND / TITLE and MOOD cells above the table (e.g. "Color, Music, Pace: Vibrant, Inspirational, Medium").

Writes:
  storyboard.json   {"title", "mood", "scenes": [{"scene", "visuals": [...], "super", "script", "image", "image_size"}]}
  assets/storyboard/<nn>-<scene>.<ext>   every embedded picture, byte-for-byte (no re-encode: full quality is kept;
                                         build.py makes exact-size display copies from these)
Standard library only (an .xlsx is a zip of XML parts).
"""
import json
import os
import posixpath
import re
import struct
import sys
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'rel': 'http://schemas.openxmlformats.org/package/2006/relationships'}


def col_index(ref):
    letters = re.match(r'[A-Z]+', ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def rels(z, part):
    """relationship id -> target path for an xlsx part"""
    rp = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')
    if rp not in z.namelist():
        return {}
    out = {}
    for r in ET.fromstring(z.read(rp)).findall('rel:Relationship', NS):
        out[r.get('Id')] = posixpath.normpath(posixpath.join(posixpath.dirname(part), r.get('Target')))
    return out


def image_size(data):
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return struct.unpack('>II', data[16:24])
    if data[:2] == b'\xff\xd8':   # walk JPEG markers to the first SOFn
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1; continue
            marker, seg = data[i + 1], struct.unpack('>H', data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack('>HH', data[i + 5:i + 9])
                return w, h
            i += 2 + seg
    return None


def blocks(text):
    """'VISUALS: ... SUPER: ... SCRIPT / VO: ...' -> dict of the three blocks"""
    keys = {'VISUALS': 'visuals', 'SUPER': 'super', 'SCRIPT / VO': 'script', 'SCRIPT/VO': 'script', 'SCRIPT': 'script', 'VO': 'script'}
    out, cur = {}, None
    for line in text.replace('\r', '').split('\n'):
        m = re.match(r'\s*(VISUALS|SUPER|SCRIPT\s*/\s*VO|SCRIPT|VO)\s*:\s*(.*)$', line, re.I)
        if m:
            cur = keys.get(re.sub(r'\s+', ' ', m.group(1).upper()).replace(' / ', ' / '), 'script')
            out.setdefault(cur, [])
            if m.group(2).strip():
                out[cur].append(m.group(2).strip())
        elif cur and line.strip():
            out[cur].append(line.strip())
    return {'visuals': out.get('visuals', []), 'super': ' '.join(out.get('super', [])).strip(),
            'script': ' '.join(out.get('script', [])).strip()}


def main():
    skillenv.utf8_stdio()
    proj, src = skillenv.path_arg(sys.argv[1]), skillenv.path_arg(sys.argv[2])
    z = zipfile.ZipFile(src)
    strings = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', NS):
            strings.append(''.join(t.text or '' for t in si.iter('{%s}t' % NS['m'])))
    wb_rels = rels(z, 'xl/workbook.xml')
    first = ET.fromstring(z.read('xl/workbook.xml')).find('m:sheets/m:sheet', NS)
    sheet = wb_rels[first.get('{%s}id' % NS['r'])]
    root = ET.fromstring(z.read(sheet))
    cells = {}   # (row, col) -> text, 0-based
    for c in root.iter('{%s}c' % NS['m']):
        ref, t = c.get('r'), c.get('t')
        r, col = int(re.search(r'\d+', ref).group(0)) - 1, col_index(ref)
        v = c.find('m:v', NS)
        if t == 's' and v is not None:
            val = strings[int(v.text)]
        elif t == 'inlineStr':
            val = ''.join(x.text or '' for x in c.iter('{%s}t' % NS['m']))
        elif v is not None:
            val = v.text or ''
        else:
            continue
        cells[(r, col)] = val
    # pictures anchored per row (drawing part linked from the sheet)
    pics = {}
    for rid, target in rels(z, sheet).items():
        if 'drawing' not in target:
            continue
        drels = rels(z, target)
        for anchor in ET.fromstring(z.read(target)):
            frm = anchor.find('xdr:from', NS)
            blip = anchor.find('.//a:blip', NS)
            if frm is None or blip is None:
                continue
            row = int(frm.find('xdr:row', NS).text)
            pics.setdefault(row, []).append(drels[blip.get('{%s}embed' % NS['r'])])
    # header row: the one that names SCENE and STORYBOARD
    header = next(r for r in sorted({r for r, _ in cells})
                  if any(cells.get((r, c), '').strip().upper() == 'SCENE' for c in range(30))
                  and any('STORYBOARD' in cells.get((r, c), '').upper() for c in range(30)))
    col = {}
    for (r, c), v in cells.items():
        if r == header:
            u = v.strip().upper()
            col['scene' if u == 'SCENE' else 'board' if 'STORYBOARD' in u else 'ref' if 'REFERENCE' in u else u.lower()] = c
    title = mood = ''
    for (r, c), v in sorted(cells.items()):
        if r < header and 'BRAND' in v.upper() or r < header and 'TITLE' in v.upper():
            title = cells.get((r + 1, c), '').strip() or title
        if r < header and v.strip().upper() == 'MOOD':
            mood = re.sub(r'\n{2,}', '\n', cells.get((r + 1, c), '').strip())
    out_dir = os.path.join(proj, 'assets', 'storyboard')
    os.makedirs(out_dir, exist_ok=True)
    scenes = []
    for r in sorted({r for r, _ in cells if r > header}):
        name = cells.get((r, col.get('scene', 1)), '').strip()
        board = cells.get((r, col.get('board', 3)), '')
        if not name and not board.strip():
            continue
        sc = {'scene': name, **blocks(board), 'images': []}
        for k, part in enumerate(pics.get(r, [])):
            data = z.read(part)
            slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or f'row{r + 1}'
            fn = f'{len(scenes) + 1:02d}-{slug}{"-" + str(k + 1) if k else ""}{os.path.splitext(part)[1].lower()}'
            with open(os.path.join(out_dir, fn), 'wb') as fh:
                fh.write(data)   # untouched bytes: no quality lost
            sc['images'].append({'file': f'assets/storyboard/{fn}', 'size': image_size(data), 'source_part': part})
        scenes.append(sc)
    sb = {'source': os.path.abspath(src), 'title': title, 'mood': mood, 'scenes': scenes}
    with open(os.path.join(proj, 'storyboard.json'), 'w', encoding='utf-8') as fh:
        json.dump(sb, fh, indent=1, ensure_ascii=False)
    print(f"{title}  |  mood: {' / '.join(l.strip('- ') for l in mood.splitlines() if l.strip())}")
    for s in scenes:
        imgs = ', '.join(f"{i['file']} {i['size'][0]}x{i['size'][1]}" for i in s['images']) or 'no image'
        print(f"- {s['scene']}: super {s['super']!r} | {imgs}\n    script: {s['script'][:110]}")


if __name__ == '__main__':
    main()
