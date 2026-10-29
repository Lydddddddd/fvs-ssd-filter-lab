#!/usr/bin/env python3
"""Check experiment coverage, provenance and raw exit statuses without rerunning ANN."""
import argparse
import collections
import csv
import hashlib
import json
import math
from pathlib import Path
import zipfile


def audit(root):
    root=Path(root)
    specs={('high','160'),('high','320'),('high','640'),('medium','320'),('low','320')}
    report={}
    for name,n,repeats,key in [('baseline',30,3,'system'),('optimization',70,7,'variant')]:
        rows=list(csv.DictReader((root/'data'/name/'results.csv').open()))
        assert len(rows)==n
        groups=collections.defaultdict(list)
        for r in rows:
            assert r['queries']=='200' and r['tier']=='formal_1000000'
            assert (r['k'],r['threads'],r['beamwidth'])==('10','1','8')
            groups[(r[key],r['bucket'],r['L'])].append(r)
            for m in ['qps','mean_latency_us','peak_rss_kb','index_bytes']:
                assert math.isfinite(float(r[m])) and float(r[m])>0
            assert 0<=float(r['recall_percent'])<=100
            assert math.isfinite(float(r['mean_ios'])) and float(r['mean_ios'])>=0
        assert len(groups)==10
        for group,values in groups.items():
            assert len(values)==repeats
            assert {r['repeat'] for r in values}=={str(i) for i in range(1,repeats+1)}
        report[name]={'rows':n,'configurations':len(groups),'repeats_per_configuration':repeats}
    checks=json.loads((root/'data/optimization/correctness.json').read_text())
    assert len(checks)==10
    for c in checks:
        for v in ['hash','bitmap']:
            assert c[v]['predicate_checks_passed']
            assert c[v]['unique_ids_and_distance_order_passed']
        assert abs(c['recall_delta_percentage_points'])<=.1000001
    metadata=json.loads((root/'data/optimization/metadata.json').read_text())
    patch=root/'patches/gateann_dense_visited.patch'
    assert hashlib.sha256(patch.read_bytes()).hexdigest()==metadata['patch_sha256']
    assert metadata['controlled_parameters']=={'K':10,'threads':1,'beamwidth':8,'mem_L':0,
        'cache_budget':0,'full_adj_neighbors':32,'io_backend':'aio'}
    raw_counts=collections.Counter()
    with zipfile.ZipFile(root/'data/raw_logs.zip') as z:
        assert z.testzip() is None
        for name in z.namelist():
            if name.endswith('command.json') and '/formal_1000000/' in name:
                command=json.loads(z.read(name));assert command['exit_code']==0
                raw_counts[name.split('/')[0]]+=1
    assert raw_counts=={'baseline':18,'optimization':42}
    report.update({'status':'PASS','formal_processes_with_exit_0':dict(raw_counts),
        'correctness_configurations':10,
        'binary_identical_top10_configurations':sum(c['ordered_top10_identical'] for c in checks),
        'max_recall_delta_pp':max(abs(c['recall_delta_percentage_points']) for c in checks),
        'patch_matches_measured_sha256':True})
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument('--output',type=Path)
    args=ap.parse_args();result=audit(args.root)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:args.output.write_text(text+'\n')
    print(text)
