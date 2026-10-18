"""Print topic terms with size and composition. Run: uv run python analysis/show.py [sparse|dense_km|dense_hdb]"""
import json, sys
import pandas as pd
col = sys.argv[1] if len(sys.argv) > 1 else "sparse"
df = pd.read_json("analysis/out/topics.jsonl", lines=True)
terms = json.load(open("analysis/out/topic_terms.json", encoding="utf-8"))[col]
for c, g in df.groupby(col):
    mix = g.kind.value_counts().head(3).to_dict()
    print(f"[{c:>2}] n={len(g):<4} docs={g.doc_id.nunique():<3} {' '.join(terms[str(c)][:8])}\n      {mix}")
