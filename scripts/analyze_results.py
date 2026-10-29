#!/usr/bin/env python3
"""Audit measurements and draw publication-ready figures from measured CSVs."""
import argparse
import collections
import csv
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

METRICS = ['recall_percent','mean_latency_us','qps','mean_ios','peak_rss_kb',
           'index_bytes','filter_skips','io_time_us','tunnel_time_us','process_time_us',
           'pre_filter_queries','in_filter_queries','post_filter_queries','filter_false_positives']
COLORS = {'pipeann':'#285f8b','gateann':'#b15a2c','hash':'#566678','bitmap':'#267b59'}
NAMES = {'pipeann':'PipeANN-Filter','gateann':'GateANN','hash':'哈希集合','bitmap':'访问位图'}


def load(path):
    with Path(path).open(newline='') as f:
        rows=list(csv.DictReader(f))
    for r in rows:
        assert (r['queries'],r['k'],r['threads'],r['beamwidth']) == ('200','10','1','8')
        assert r['tier'] == 'formal_1000000'
        assert 0 <= float(r['recall_percent']) <= 100
    return rows


def summarize(rows, keys):
    groups=collections.defaultdict(list)
    for r in rows: groups[tuple(r[k] for k in keys)].append(r)
    summary=[]
    for key,values in sorted(groups.items()):
        row=dict(zip(keys,key));row['n']=len(values)
        for m in METRICS:
            vals=[float(r[m]) for r in values if r.get(m,'')!='']
            if vals:
                row.update({m+'_median':statistics.median(vals),m+'_min':min(vals),m+'_max':max(vals)})
        summary.append(row)
    return summary


def write_csv(path,rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)


def point(row,metric,scale=1):
    mid=row[metric+'_median']/scale
    return mid, np.array([[mid-row[metric+'_min']/scale],[row[metric+'_max']/scale-mid]])


def prettify(ax):
    ax.grid(axis='y',color='#dddddd',linewidth=.6)
    ax.set_axisbelow(True)
    for side in ['top','right']: ax.spines[side].set_visible(False)


def save(fig,out,name):
    for ext in ['png','pdf','svg']:
        fig.savefig(out/f'{name}.{ext}',dpi=220,bbox_inches='tight',facecolor='white')
    plt.close(fig)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--baseline',type=Path,required=True)
    ap.add_argument('--optimization',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--font',type=Path)
    args=ap.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    if args.font:
        font_manager.fontManager.addfont(str(args.font))
        plt.rcParams['font.family']=font_manager.FontProperties(fname=args.font).get_name()
    else:plt.rcParams['font.family']='DejaVu Sans'
    plt.rcParams.update({'font.size':12,'axes.labelsize':12,'legend.fontsize':11,
                         'xtick.labelsize':11,'ytick.labelsize':11,'pdf.fonttype':42,
                         'svg.fonttype':'none','axes.unicode_minus':False})
    base=load(args.baseline);opt=load(args.optimization)
    assert len(base)==30
    bs=summarize(base,['system','bucket','L']);os=summarize(opt,['variant','bucket','L'])
    assert len(bs)==10 and all(r['n']==3 for r in bs)
    assert len(os)==10 and all(r['n']==7 for r in os)
    write_csv(out/'baseline_summary.csv',bs);write_csv(out/'optimization_summary.csv',os)
    lookup={(r['system'],r['bucket'],r['L']):r for r in bs}
    ol={(r['variant'],r['bucket'],r['L']):r for r in os}

    fig,ax=plt.subplots(figsize=(6.8,3.9),layout='constrained')
    for system,ls in [('pipeann',['20','40','80']),('gateann',['160','320','640'])]:
        values=[lookup[(system,'high',L)] for L in ls]
        x=[r['recall_percent_median'] for r in values]
        y=[r['mean_latency_us_median']/1000 for r in values]
        xe=np.array([[r['recall_percent_median']-r['recall_percent_min'] for r in values],
                     [r['recall_percent_max']-r['recall_percent_median'] for r in values]])
        ye=np.array([[r['mean_latency_us_median']/1000-r['mean_latency_us_min']/1000 for r in values],
                     [r['mean_latency_us_max']/1000-r['mean_latency_us_median']/1000 for r in values]])
        ax.errorbar(x,y,xerr=xe,yerr=ye,marker='o' if system=='pipeann' else 's',
                    color=COLORS[system],label=NAMES[system],capsize=4,linewidth=1.7)
        for xx,yy,L in zip(x,y,ls):
            ax.annotate('L='+L,(xx,yy),xytext=(5,8 if system=='pipeann' else -18),textcoords='offset points',fontsize=10)
    ax.set(xlabel='Recall@10 (%)',ylabel='平均查询时延 (ms)',xlim=(78,101),ylim=(0,3.3))
    prettify(ax);ax.legend(loc='upper left',frameon=False)
    save(fig,out,'01_recall_latency')

    fig,axes=plt.subplots(3,1,figsize=(6.8,6.8),sharex=True,layout='constrained')
    for system,L in [('pipeann','40'),('gateann','320')]:
        values=[lookup[(system,b,L)] for b in ['low','medium','high']]
        for ax,metric,scale,label in zip(axes,['recall_percent','mean_latency_us','mean_ios'],
                                      [1,1000,1],['Recall@10 (%)','平均查询时延 (ms)','逻辑 I/O (次/查询)']):
            y=[point(r,metric,scale)[0] for r in values]
            e=np.concatenate([point(r,metric,scale)[1] for r in values],axis=1)
            ax.errorbar(range(3),y,yerr=e,color=COLORS[system],label=NAMES[system],
                        marker='o' if system=='pipeann' else 's',capsize=4,linewidth=1.7)
            ax.set_ylabel(label);prettify(ax)
    axes[0].set_ylim(0,105);axes[1].set_ylim(bottom=0);axes[2].set_ylim(bottom=0)
    axes[0].legend(frameon=False,loc='lower right')
    axes[-1].set_xticks(range(3),['Low\n0.545%','Medium\n2.958%','High\n12.323%'])
    axes[-1].set_xlabel('Workload 桶及选择率中位数')
    save(fig,out,'02_selectivity_performance')

    configs=[('high','160'),('high','320'),('high','640'),('medium','320'),('low','320')]
    labels=['High\nL=160','High\nL=320','High\nL=640','Medium\nL=320','Low\nL=320']
    fig,axes=plt.subplots(2,1,figsize=(6.8,5.3),sharex=True,layout='constrained')
    for i,variant in enumerate(['hash','bitmap']):
        values=[ol[(variant,b,L)] for b,L in configs]
        for ax,metric,scale,label in zip(axes,['mean_latency_us','tunnel_time_us'],[1000,1],
                                      ['平均查询时延 (ms)','Tunneling 时间 (μs/查询)']):
            y=[point(r,metric,scale)[0] for r in values]
            e=np.concatenate([point(r,metric,scale)[1] for r in values],axis=1)
            ax.bar(np.arange(5)+(i-.5)*.34,y,width=.32,yerr=e,capsize=3,
                   color=COLORS[variant],label=NAMES[variant],error_kw={'linewidth':.8})
            ax.set_ylabel(label);prettify(ax)
    axes[0].legend(frameon=False);axes[-1].set_xticks(range(5),labels)
    save(fig,out,'03_optimization')
    improvements=[]
    for b,L in configs:
        h,z=ol[('hash',b,L)],ol[('bitmap',b,L)]
        improvement={'bucket':b,'L':L,
          'latency_reduction_percent':100*(1-z['mean_latency_us_median']/h['mean_latency_us_median']),
          'speedup':h['mean_latency_us_median']/z['mean_latency_us_median'],
          'tunnel_reduction_percent':100*(1-z['tunnel_time_us_median']/h['tunnel_time_us_median']),
          'recall_delta_pp':z['recall_percent_median']-h['recall_percent_median'],
          'rss_delta_mib':(z['peak_rss_kb_median']-h['peak_rss_kb_median'])/1024}
        improvements.append(improvement)
    write_csv(out/'improvements.csv',improvements)
    audit={'baseline_rows':len(base),'baseline_groups':len(bs),'optimization_rows':len(opt),
           'optimization_repeats':7,'baseline_summary':bs,'optimization_summary':os,
           'improvements':improvements,
           'statistic':'median and observed min/max across independent process runs; no confidence interval claim',
           'latency_source':'PipeANN reported query-phase mean; GateANN 1e6 / rounded integer QPS'}
    (out/'analysis.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    print(json.dumps({'baseline_rows':len(base),'optimization_rows':len(opt),'improvements':improvements},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
