#!/usr/bin/env python3
"""Repeat the unchanged hash program to check intrinsic ANN output variation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def parse_recall(text):
    for line in text.splitlines():
        if re.match(r'^\s*160\s+\d+\s+\d+\.\d+',line):
            return float(line.split()[2])*100
    raise ValueError('Missing L=160 result row')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--experiment',type=Path,required=True)
    ap.add_argument('--repeats',type=int,default=10)
    args=ap.parse_args()
    if args.repeats<2:ap.error('Use at least two repeats')
    root=args.experiment.resolve()
    metadata=json.loads((root/'metadata.json').read_text())
    source=next(item['command'] for item in metadata['commands']
                if item['phase']=='correctness' and '/debug_100000/' in ' '.join(item['command'])
                and '/high/' in ' '.join(item['command']))
    assert source[-3:]==['160','320','640']
    command=source[:-3]+['160']
    out=root/'async-control'
    out.mkdir(exist_ok=False)
    results=[]
    for i in range(1,args.repeats+1):
        prefix=out/f'hash-{i}'
        env=dict(os.environ,GATEANN_VISITED_MODE='hash',GATEANN_RESULT_DUMP=str(prefix),
                 OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
        proc=subprocess.run(command,capture_output=True,text=True,env=env,check=True)
        text=proc.stdout+proc.stderr
        (out/f'hash-{i}.log').write_text(text)
        ids=Path(f'{prefix}.L160.u32')
        results.append({'run':i,'recall_percent':parse_recall(text),
                        'output_sha256':hashlib.sha256(ids.read_bytes()).hexdigest()})
    values=[r['recall_percent'] for r in results]
    report={'variant':'hash (unchanged between runs)','tier':'debug_100000','bucket':'high','L':160,
            'runs':results,'distinct_output_hashes':len({r['output_sha256'] for r in results}),
            'recall_range_pp':[min(values),max(values)]}
    (root/'async_control.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
