#!/usr/bin/env python3
"""Run correctness checks and paired GateANN hash/bitmap experiments."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import time
from validate_query_outputs import DatasetValidator


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, log, env):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('w') as handle:
        proc = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, env=env)
    if proc.returncode:
        raise RuntimeError(f'Command failed ({proc.returncode}), see {log}')


def query_command(course, repo, tier, bucket, budgets):
    data = course / 'datasets/yfcc_course_v1' / tier
    work = data / 'workloads' / bucket
    return [str(repo / 'build/tests/search_disk_index_yfcc'), 'uint8',
            str(course / 'course_runs/indices/gateann' / tier / 'yfcc'),
            '1', '8', str(work / 'query.u8bin'), str(data / 'base.metadata.spmat'),
            str(work / 'query.metadata.spmat'), str(work / 'ground_truth.ids.ibin'),
            '10', 'l2', 'pq', '8', '0', '0', '32', *map(str, budgets)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--course-root', type=Path, required=True)
    ap.add_argument('--optimized-repo', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--repeats', type=int, default=7)
    ap.add_argument('--cpu', type=int)
    ap.add_argument('--correctness-only', action='store_true')
    args = ap.parse_args()
    if args.repeats < 3:
        ap.error('Use at least three repeats')
    course, repo, out = args.course_root.resolve(), args.optimized_repo.resolve(), args.output.resolve()
    if out.exists():
        raise RuntimeError(f'Refusing to overwrite an existing experiment: {out}')
    out.mkdir(parents=True)
    cpus = sorted(os.sched_getaffinity(0))
    cpu = args.cpu if args.cpu is not None else cpus[-1]
    if cpu not in cpus:
        raise RuntimeError(f'CPU {cpu} not available')
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    env.pop('GATEANN_RESULT_DUMP', None)
    metadata = {'start_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'upstream_commit': subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(),
                'binary_sha256': sha256(repo / 'build/tests/search_disk_index_yfcc'),
                'patch_sha256': sha256(Path(__file__).resolve().parents[1] / 'patches/gateann_dense_visited.patch'),
                'cpu_affinity': cpu, 'repeats': args.repeats,
                'controlled_parameters': {'K':10, 'threads':1, 'beamwidth':8, 'mem_L':0,
                                          'cache_budget':0, 'full_adj_neighbors':32, 'io_backend':'aio'},
                'order': 'buckets shuffled with seed 20261029; variants alternate AB/BA each round',
                'cache_policy': 'No OS page-cache drop; FullAdj MAP_POPULATE; same existing indexes; no result cache',
                'host_load_before': os.getloadavg(), 'commands': []}
    budgets = {'high':[160,320,640], 'medium':[320], 'low':[320]}
    checks = []
    for tier in ['debug_100000', 'formal_1000000']:
        validator = DatasetValidator(course / 'datasets/yfcc_course_v1' / tier)
        for bucket, ls in budgets.items():
            files = {}
            for variant in ['hash', 'bitmap']:
                folder = out / 'correctness' / tier / bucket / variant
                folder.mkdir(parents=True)
                dump = folder / 'results'
                local_env = dict(env, GATEANN_VISITED_MODE=variant, GATEANN_RESULT_DUMP=str(dump))
                command = ['taskset','-c',str(cpu),*query_command(course,repo,tier,bucket,ls)]
                run(command, folder / 'run.log', local_env)
                metadata['commands'].append({'phase':'correctness','variant':variant,'command':command})
                files[variant] = {L:Path(f'{dump}.L{L}.u32') for L in ls}
            for L in ls:
                left, right = files['hash'][L], files['bitmap'][L]
                a, b = left.read_bytes(), right.read_bytes()
                assert len(a) == len(b) == 200*10*4
                check = {'tier':tier,'bucket':bucket,'L':L,'queries':200,'ids_compared':2000,
                         'hash_sha256':sha256(left),'bitmap_sha256':sha256(right),
                         'ordered_top10_identical': a == b}
                for variant in ['hash','bitmap']:
                    check[variant] = validator.validate(bucket,
                        out/'correctness'/tier/bucket/variant/'results', L)
                check['recall_delta_percentage_points'] = (
                    check['bitmap']['recall_percent_recomputed'] -
                    check['hash']['recall_percent_recomputed'])
                # Asynchronous I/O can change the candidate traversal order.
                # Inspect predicate/order correctness independently; predeclare
                # a 0.1 percentage-point Recall tolerance after the pilot run.
                assert abs(check['recall_delta_percentage_points']) <= 0.1000001
                checks.append(check)
                print('CORRECTNESS',json.dumps(check),flush=True)
        validator.close()
    (out / 'correctness.json').write_text(json.dumps(checks,indent=2))
    metadata['correctness_policy'] = ('Exact membership unit differential tests; independently validate actual '
        'returned IDs, predicates, uniqueness and L2 ordering; Recall delta <= 0.1 percentage point. '
        'Binary identity recorded but not required because I/O completion changes traversal timing.')
    if not args.correctness_only:
        run_root = out / 'runs'
        run_root.mkdir()
        (run_root / 'indices').symlink_to(course / 'course_runs/indices', target_is_directory=True)
        aggregate = []
        rng = random.Random(20261029)
        for repeat in range(1,args.repeats+1):
            buckets = list(budgets)
            rng.shuffle(buckets)
            variants = ['hash','bitmap'] if repeat % 2 else ['bitmap','hash']
            for bucket in buckets:
                for variant in variants:
                    run_id = f'dense-{variant}-r{repeat}'
                    command = ['taskset','-c',str(cpu),sys.executable,
                               str(course / 'adapters/gateann_adapter.py'),'search',
                               '--repo',str(repo),'--dataset-root',str(course/'datasets/yfcc_course_v1'),
                               '--tier','formal','--run-root',str(run_root),'--threads','1',
                               '--beamwidth','8','--k','10','--bucket',bucket,
                               '--L',*map(str,budgets[bucket]),'--full-adj-neighbors','32',
                               '--run-id',run_id]
                    local_env = dict(env,GATEANN_VISITED_MODE=variant)
                    log = out / 'driver_logs' / f'{run_id}-{bucket}.log'
                    run(command,log,local_env)
                    source = run_root / 'results/gateann/formal_1000000' / bucket / run_id / 'results.csv'
                    with source.open(newline='') as f:
                        rows = list(csv.DictReader(f))
                    for row in rows:
                        aggregate.append({'variant':variant,'repeat':str(repeat),**row})
                    metadata['commands'].append({'phase':'performance','variant':variant,'repeat':repeat,
                                                 'command':command,'environment':{'GATEANN_VISITED_MODE':variant,
                                                 'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}})
                    print(f'PERFORMANCE repeat={repeat}/{args.repeats} bucket={bucket} variant={variant}',flush=True)
        assert len(aggregate) == 10*args.repeats
        with (out / 'results.csv').open('w',newline='') as f:
            writer = csv.DictWriter(f,fieldnames=list(aggregate[0]))
            writer.writeheader();writer.writerows(aggregate)
    metadata['end_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    metadata['host_load_after'] = os.getloadavg()
    (out / 'metadata.json').write_text(json.dumps(metadata,indent=2))
    print('EXPERIMENT COMPLETE',out,flush=True)


if __name__ == '__main__':
    main()
