"""Markdown table of every region-driven follow-up question, for clinician review.
Usage: .venv/bin/python scripts/list_region_followups.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intake.models import load_graph  # noqa: E402

g = load_graph()
rows = []
for n in g.nodes:
    for r in n.next.rules:
        if r.goto.split("_")[0] in ("cpx", "abx", "hdx"):
            (op, (site, regions)), = r.if_.items()
            rows.append((r.goto, f"{op} {site} in [{', '.join(regions)}]"))
nodes = {}
for goto, cond in rows:
    nodes[goto] = cond
print("| node id | English text | options | condition (asked after the associated-symptoms question) | source | checked |")
print("|---|---|---|---|---|---|")
for nid, cond in nodes.items():
    n = g.node(nid)
    opts = "; ".join(o.en for o in n.options)
    print(f"| {nid} | {n.text.en} | {opts} | {cond} | {n.source} | {n.sourceChecked} |")
