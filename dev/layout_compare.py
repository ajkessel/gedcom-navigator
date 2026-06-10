#!/usr/bin/env python3
"""Render old-vs-new family-tree layouts for debug fixtures side by side.

Usage:
    .venv/bin/python dev/layout_compare.py [fixture ...]

Without arguments, all family-tree fixtures in debug/*.json are rendered.
Output PNGs land in debug/layout-compare/<name>.png with the old layout on
top and the unit-based layout below.
"""

import glob
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gedcom_family_tree import layout_family_tree_legacy  # noqa: E402
from gedcom_family_tree_layout import layout_family_tree_units  # noqa: E402

CELL_W = 46
CELL_H = 64
BOX_W = 38
BOX_H = 18
MARGIN = 24


def _draw_layout(layout, edges, buses, title, center_id):
    pos = {n['id']: (n['generation'], n['column']) for n in layout}
    if not pos:
        return Image.new('RGB', (200, 80), 'white')
    min_gen = min(g for g, _c in pos.values())
    min_col = min(c for _g, c in pos.values())
    max_col = max(c for _g, c in pos.values())
    max_gen = max(g for g, _c in pos.values())

    def xy(person_id):
        gen, col = pos[person_id]
        x = MARGIN + (col - min_col) * CELL_W + BOX_W / 2
        y = MARGIN + 14 + (gen - min_gen) * CELL_H + BOX_H / 2
        return x, y

    width = int(MARGIN * 2 + (max_col - min_col) * CELL_W + BOX_W)
    height = int(MARGIN * 2 + 14 + (max_gen - min_gen) * CELL_H + BOX_H)
    img = Image.new('RGB', (max(width, 240), height), 'white')
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 9)
        tfont = ImageFont.truetype(
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 12)
    except OSError:
        font = tfont = ImageFont.load_default()
    draw.text((MARGIN, 4), title, fill='black', font=tfont)

    # Spouse connectors.
    for s, t, cat in edges:
        if cat != 'spouses' or s not in pos or t not in pos:
            continue
        x1, y1 = xy(s)
        x2, y2 = xy(t)
        draw.line((x1, y1 - 3, x2, y2 - 3), fill='#c08020', width=2)
        draw.line((x1, y1, x2, y2), fill='#c08020', width=2)

    if buses is not None:
        for bus in buses:
            child_points = [xy(c) for c in bus['children']]
            parent_points = [xy(p) for p in bus['parent_ids'] if p in pos]
            bus_y = min(cy for _cx, cy in child_points) - BOX_H / 2 - 8
            xs = [cx for cx, _cy in child_points]
            if parent_points:
                px = sum(x for x, _y in parent_points) / len(parent_points)
                py = max(y for _x, y in parent_points) + BOX_H / 2
                draw.line((px, py, px, bus_y), fill='#3070c0', width=2)
                xs.append(px)
            draw.line((min(xs), bus_y, max(xs), bus_y),
                      fill='#3070c0', width=2)
            for cx, cy in child_points:
                draw.line((cx, bus_y, cx, cy - BOX_H / 2),
                          fill='#3070c0', width=2)
    else:
        # Old layout: draw parent-child edges directly.
        for s, t, cat in edges:
            if s not in pos or t not in pos:
                continue
            if cat == 'children':
                parent, child = s, t
            elif cat == 'parents':
                parent, child = t, s
            else:
                continue
            x1, y1 = xy(parent)
            x2, y2 = xy(child)
            draw.line((x1, y1 + BOX_H / 2, x2, y2 - BOX_H / 2),
                      fill='#3070c0', width=1)

    for person_id in pos:
        x, y = xy(person_id)
        color = '#e0e8ff' if person_id != center_id else '#ffd0d0'
        draw.rectangle((x - BOX_W / 2, y - BOX_H / 2,
                        x + BOX_W / 2, y + BOX_H / 2),
                       fill=color, outline='black')
        label = person_id.strip('@').replace('I', '')[-6:]
        draw.text((x - BOX_W / 2 + 2, y - 6), label, fill='black', font=font)
    return img


def compare(path, out_dir):
    with open(path, encoding='utf-8') as handle:
        d = json.load(handle)
    if d.get('graph_type') and d['graph_type'] != 'family_tree':
        return None
    edges = [(e['source'], e['target'], e['category']) for e in d['edges']]
    center_id = d['center_id']
    visible_ids = d['visible_ids']

    kinds = {}
    for edge in d['edges']:
        kind = edge.get('relationship_kind')
        if not kind:
            continue
        if edge['category'] == 'parents':
            kinds[(edge['target'], edge['source'])] = kind
        elif edge['category'] == 'children':
            kinds[(edge['source'], edge['target'])] = kind

    old_layout = layout_family_tree_legacy(center_id, visible_ids, edges)
    new_layout = layout_family_tree_units(
        center_id, visible_ids, edges, d.get('family_members'),
        lambda parent_id, child_id: kinds.get(
            (parent_id, child_id), 'birth'))

    name = os.path.splitext(os.path.basename(path))[0]
    img_old = _draw_layout(old_layout, edges, None,
                           f'{name} old (pass-based)', center_id)
    img_new = _draw_layout(new_layout, edges, new_layout.child_buses,
                           f'{name} new (unit-based)', center_id)
    width = max(img_old.width, img_new.width)
    combined = Image.new(
        'RGB', (width, img_old.height + img_new.height + 8), '#888888')
    combined.paste(img_old, (0, 0))
    combined.paste(img_new, (0, img_old.height + 8))
    out_path = os.path.join(out_dir, f'{name}.png')
    combined.save(out_path)
    return out_path


def main():
    out_dir = os.path.join('debug', 'layout-compare')
    os.makedirs(out_dir, exist_ok=True)
    paths = sys.argv[1:] or sorted(glob.glob('debug/*.json'))
    for path in paths:
        try:
            out_path = compare(path, out_dir)
        except Exception as exc:  # pragma: no cover - diagnostic tool
            print(f'{path}: ERROR {exc}')
            continue
        if out_path:
            print(out_path)


if __name__ == '__main__':
    main()
