#!/usr/bin/env python3
"""Build the course report from its retained DOCX layout and measured data."""
import argparse
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import statistics
import zipfile

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.shared import Cm, Pt, RGBColor

TITLE = '基于SSD的过滤向量检索系统性能比较与优化'
REPO = 'https://github.com/Lydddddddd/fvs-ssd-filter-lab'
FONT = 'SimSun'


def set_font(run, size=10.5, bold=False):
    run.font.name=FONT;run.font.size=Pt(size);run.font.bold=bold
    run.font.color.rgb=RGBColor(0,0,0)
    pr=run._element.get_or_add_rPr()
    rf=pr.find(qn('w:rFonts'))
    if rf is None:rf=OxmlElement('w:rFonts');pr.insert(0,rf)
    for k in ['ascii','hAnsi','eastAsia','cs']:rf.set(qn('w:'+k),FONT)
    for k in ['asciiTheme','hAnsiTheme','eastAsiaTheme','cstheme']:
        rf.attrib.pop(qn('w:'+k),None)


def format_paragraph(p, indent=True, before=0, after=4, keep=False):
    f=p.paragraph_format;f.line_spacing=1.25
    f.space_before=Pt(before);f.space_after=Pt(after)
    f.first_line_indent=Pt(21 if indent else 0)
    f.left_indent=Pt(0);f.right_indent=Pt(0)
    f.keep_with_next=keep;f.widow_control=True
    pr=p._p.get_or_add_pPr()
    ind=pr.find(qn('w:ind'))
    if ind is not None:
        ind.set(qn('w:firstLineChars'),'200' if indent else '0')
        ind.set(qn('w:leftChars'),'0');ind.set(qn('w:rightChars'),'0')
        ind.attrib.pop(qn('w:hangingChars'),None)
    for name in ['numPr','pBdr']:
        x=pr.find(qn('w:'+name))
        if x is not None:pr.remove(x)
    numbering=OxmlElement('w:numPr')
    numid=OxmlElement('w:numId');numid.set(qn('w:val'),'0')
    numbering.append(numid);pr.append(numbering)
    snap=pr.find(qn('w:snapToGrid'))
    if snap is None:snap=OxmlElement('w:snapToGrid');pr.append(snap)
    snap.set(qn('w:val'),'0')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--template',type=Path,required=True)
    ap.add_argument('--project',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--identity',type=Path,required=True,
                    help='Private JSON with name, student_id, class and department; do not publish it')
    ap.add_argument('--toc',type=Path)
    args=ap.parse_args();root=args.project
    identity=json.loads(args.identity.read_text())
    data=json.loads((root/'figures/analysis.json').read_text())
    checks=json.loads((root/'data/optimization/correctness.json').read_text())
    meta=json.loads((root/'data/optimization/metadata.json').read_text())
    control=json.loads((root/'data/optimization/async_control.json').read_text())
    rows=list(csv.DictReader((root/'data/baseline/results.csv').open()))
    bs={(r['system'],r['bucket'],r['L']):r for r in data['baseline_summary']}
    os={(r['variant'],r['bucket'],r['L']):r for r in data['optimization_summary']}
    toc=json.loads(args.toc.read_text()) if args.toc and args.toc.exists() else {}
    doc=Document(args.template)
    original=list(doc._element.body)
    breaks=[deepcopy(original[i]) for i in [20,34,39]]
    end=deepcopy(original[-1])
    # Content replaces the short sample. Keep its four sections and page
    # geometry, but let the body sections flow to avoid nearly empty pages.
    for container in [breaks[1],breaks[2],end]:
        sect=container if container.tag==qn('w:sectPr') else container.find('.//'+qn('w:sectPr'))
        typ=sect.find(qn('w:type'))
        if typ is None:typ=OxmlElement('w:type');sect.insert(0,typ)
        typ.set(qn('w:val'),'continuous')
    for child in list(doc._element.body):doc._element.body.remove(child)
    for child in original[:17]:doc._element.body.append(deepcopy(child))
    doc._element.body.append(end)
    for style in doc.styles:
        if style.type==1:
            style.font.name=FONT;style.font.size=Pt(10.5)
            style.font.color.rgb=RGBColor(0,0,0)
            style.paragraph_format.line_spacing=1.25
            pr=style.element.get_or_add_rPr()
            rf=pr.find(qn('w:rFonts'))
            if rf is None:rf=OxmlElement('w:rFonts');pr.append(rf)
            for k in ['ascii','hAnsi','eastAsia','cs']:rf.set(qn('w:'+k),FONT)
            for k in ['asciiTheme','hAnsiTheme','eastAsiaTheme','cstheme']:rf.attrib.pop(qn('w:'+k),None)
    for name,size in [('Title',18),('Heading 1',14),('Heading 2',12),('Heading 3',10.5)]:
        st=doc.styles[name];st.font.size=Pt(size);st.font.bold=True
        st.paragraph_format.page_break_before=False
        st.paragraph_format.keep_with_next=True
    # Fill the original cover's explicitly editable title and identity slots.
    doc.tables[0].cell(0,0).text=TITLE
    cover_values=[identity['department'],identity['class'],identity['name'],identity['student_id']]
    for row,value in zip(doc.tables[1].rows,cover_values):row.cells[1].text=value
    for i,t in enumerate(doc.tables):
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    format_paragraph(p,False,after=2)
                    p.alignment=WD_ALIGN_PARAGRAPH.CENTER
                    for run in p.runs:set_font(run,16 if i==0 else 10.5,i==0)
    for p in doc.paragraphs:
        if p.text.strip():
            for run in p.runs:set_font(run,16 if p.text.strip()=='计算机系统设计' else 10.5)

    headings=[]
    def p(text='',indent=True,keep=False):
        obj=doc.add_paragraph();format_paragraph(obj,indent,keep=keep)
        if REPO in text:
            before,_,after=text.partition(REPO)
            set_font(obj.add_run(before))
            run=obj.add_run(REPO);set_font(run)
            link=OxmlElement('w:hyperlink')
            link.set(qn('r:id'),doc.part.relate_to(REPO,RT.HYPERLINK,is_external=True))
            link.append(run._r);obj._p.append(link)
            set_font(obj.add_run(after))
        else:set_font(obj.add_run(text))
        return obj
    def h(text,level=1,newpage=False):
        obj=doc.add_paragraph(text,style=f'Heading {level}')
        format_paragraph(obj,False,before=9 if level==1 else 6,after=5,keep=True)
        obj.paragraph_format.page_break_before=newpage
        for run in obj.runs:set_font(run,14 if level==1 else 12,True)
        if level==1:headings.append(text)
        return obj
    def caption(text):
        obj=p(text,False);obj.alignment=WD_ALIGN_PARAGRAPH.CENTER
        obj.paragraph_format.space_before=Pt(4);obj.paragraph_format.space_after=Pt(6)
        return obj
    def table(title,headers,values,widths=None):
        cap=caption(title);cap.paragraph_format.keep_with_next=True
        t=doc.add_table(rows=1,cols=len(headers));t.alignment=WD_TABLE_ALIGNMENT.CENTER
        t.autofit=False
        if widths is None:widths=[14.4/len(headers)]*len(headers)
        for c,w in zip(t.columns,widths):c.width=Cm(w)
        for cell,txt in zip(t.rows[0].cells,headers):cell.text=str(txt)
        for row in values:
            cells=t.add_row().cells
            for cell,txt in zip(cells,row):cell.text=str(txt)
        for ir,row in enumerate(t.rows):
            trpr=row._tr.get_or_add_trPr()
            cant=OxmlElement('w:cantSplit');trpr.append(cant)
            if ir==0:
                repeat=OxmlElement('w:tblHeader');trpr.append(repeat)
            for j,cell in enumerate(row.cells):
                cell.width=Cm(widths[j]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
                pr=cell._tc.get_or_add_tcPr()
                borders=OxmlElement('w:tcBorders')
                for side in ['top','left','bottom','right']:
                    el=OxmlElement('w:'+side);el.set(qn('w:val'),'single');el.set(qn('w:sz'),'4');el.set(qn('w:color'),'D9D9D9');borders.append(el)
                old=pr.find(qn('w:tcBorders'))
                if old is not None:pr.remove(old)
                pr.append(borders)
                margins=OxmlElement('w:tcMar')
                for side,val in [('top','65'),('bottom','65'),('left','65'),('right','65')]:
                    el=OxmlElement('w:'+side);el.set(qn('w:w'),val);el.set(qn('w:type'),'dxa');margins.append(el)
                pr.append(margins)
                if ir==0:
                    fill=OxmlElement('w:shd');fill.set(qn('w:fill'),'E8EDF2');pr.append(fill)
                for para in cell.paragraphs:
                    format_paragraph(para,False,after=0)
                    if len(values)<=7:
                        para.paragraph_format.keep_with_next=ir<len(t.rows)-1
                    para.alignment=WD_ALIGN_PARAGRAPH.LEFT if j==0 else WD_ALIGN_PARAGRAPH.CENTER
                    for run in para.runs:set_font(run,10.5,ir==0)
        p('',False).paragraph_format.space_after=Pt(1)
        return t
    def figure(name,label):
        obj=p('',False,True);obj.alignment=WD_ALIGN_PARAGRAPH.CENTER
        obj.add_run().add_picture(str(root/'figures'/name),width=Cm(14.4))
        caption(label)
    def code(lines):
        obj=p('\n'.join(lines),False)
        obj.alignment=WD_ALIGN_PARAGRAPH.LEFT
        obj.paragraph_format.keep_together=True
        obj.paragraph_format.left_indent=Cm(.3)
        return obj
    def section_break(i):
        b=deepcopy(breaks[i])
        for mark in list(b.iter(qn('w:bookmarkStart'))):mark.getparent().remove(mark)
        for mark in list(b.iter(qn('w:bookmarkEnd'))):mark.getparent().remove(mark)
        doc._element.body.insert(len(doc._element.body)-1,b)
    def f(r,m,d=2):return f"{r[m+'_median']:.{d}f}"

    toc_title=p('目  录',False);toc_title.paragraph_format.page_break_before=True
    toc_title.alignment=WD_ALIGN_PARAGRAPH.CENTER
    for run in toc_title.runs:set_font(run,16,True)
    contents=['1 实验环境与复现信息','2 系统设计理解与比较','3 测试方案与负载选择',
              '4 实验结果与机制分析','5 优化设计实现与验证','6 调试记录','7 实验总结','参考文献']
    for text in contents:
        obj=p(text+'\t'+str(toc.get(text,'')),False)
        obj.paragraph_format.tab_stops.add_tab_stop(Cm(14.1),WD_TAB_ALIGNMENT.RIGHT,WD_TAB_LEADER.DOTS)
        obj.paragraph_format.space_after=Pt(8)
    p('实验日期：2026年10月28日至29日。基础数据与补充实验均保留原始日志、运行命令和统计脚本。',False)
    section_break(0)

    h('1 实验环境与复现信息',newpage=True)
    p('本实验在统一的 YFCC 多标签向量负载上，比较 PipeANN-Filter 与 GateANN 的召回率、查询时延、逻辑 I/O 和内存代价，并实现 GateANN 的访问位图优化。基础测试表明两套系统对过滤强度的反应明显不同；补充测试中，位图将 Low 桶查询时延中位数降低 14.18%，同时保留 34.30% 的 Recall@10。该优化改善遍历开销，未消除低搜索预算下的召回率限制。')
    table('表1 实验平台与固定软件版本',['项目','实际配置'],[
      ['CPU','2 × AMD EPYC 7542；64个物理核、128个逻辑CPU'],
      ['内存','宿主机可见约251 GiB；共享资源，不代表独占配额'],
      ['SSD与文件系统','Samsung 990 EVO Plus 4TB，NVMe；/workspace位于nvme0n1p1，ext4'],
      ['操作系统','Ubuntu 22.04.4 LTS，x86-64；内核5.15.0-139-generic'],
      ['编译环境','GCC/G++ 11.4.0，CMake Release，Linux AIO'],
      ['PipeANN提交','2ec84fe20c37dc3cc236b66f7eba31c0cc80bf1e'],
      ['GateANN提交','71e87cbf0e25c0400c0109dd25a64a7c4dccc9dd'],
      ['基础实验编号','20261029-083358；每组3次独立进程运行'],
      ['公共查询参数','threads=1，beamwidth=8，K=10，mem_L=0，cache_budget=0'],
      ['GateANN结构','FullAdj邻居上限32；不使用GPU'],
    ],[3.0,11.4])
    p('根据 findmnt，实验工作目录使用 990 EVO Plus 所在分区；机器另有 990 PRO，但后者不是本次工作目录对应设备。课程脚本固定源码版本，GateANN 先应用课程提供的 AIO control block 兼容补丁。两套 Debug 索引均成功构建，运行编号 debug-check-20261028-135003 的 High 验证分别得到 96.20% 和 95.85% Recall@10，检查器通过。')
    p('基础结果保存在 course_runs/experiments/20261029-083358/。补充实验保留固定上游提交，在独立工作树中增加访问位图与结果导出功能，未改写原始基线或预构建索引。优化补丁 SHA-256 为 '+meta['patch_sha256']+'。')

    h('2 系统设计理解与比较')
    h('2.1 PipeANN与PipeANN Filter',2)
    p('PipeANN 将图搜索的计算与 SSD 访问流水化，通过在候选处理、距离计算和异步读取之间安排重叠，降低严格串行依赖带来的等待。PipeANN-Filter 在这一框架中加入过滤：DRAM 中保存 PQ 近似表示和概率过滤摘要，SSD 保存完整向量、图及属性相关索引。搜索先允许探索满足摘要判断的候选超集，再验证真实属性，以少量误判换取较少的属性读取[2,3]。')
    p('课程固定版本的 spec_filter_search.cpp 会估计选择率及过滤精度，比较 Pre、In、Post 三种路径的读取和距离计算代价后选择路线。Pre 路径先缩小标签候选集合；In 路径在图搜索过程中利用过滤结构；Post 路径扩大近邻搜索后再筛选。概率过滤中的假阳性表示候选多通过了一次中间判断，不等于最终答案允许违反标签谓词。路径选择依赖成本估计与索引组织，其收益和空间开销须由真实负载验证[1,3]。')
    h('2.2 GateANN',2)
    p('GateANN 将图遍历与完整向量获取分开：DRAM 中的标签 CSR 用于检查过滤条件，PQ 表示用于估计距离，FullAdj 提供节点邻接表；完整向量及磁盘图位于 SSD。Pre-I/O Filtering 在发起 SSD 请求前判断候选是否满足标签条件。对不匹配的节点，Graph Tunneling 仍读取其内存邻接表并计算近似距离，从而穿过无效节点到达有效区域，避免因为直接剪除无效节点而破坏搜索可达性[4,5]。')
    p('这一设计省去了许多无效向量的 SSD 读取，但保留了邻居去重、PQ 距离计算和候选池更新。课程 Formal FullAdj 文件为 132000024 字节，约 125.89 MiB，此外还需标签和 PQ 结构。减少 I/O 后，遍历中的 CPU 与内存访问可能成为主要开销；内存邻接表也会随向量规模和邻居数量增长。这正是本实验选择访问集合为优化对象的背景。')
    table('表2 两种设计的主要差异',['系统','过滤位置与可达性','主要资源与潜在代价'],[
      ['PipeANN-Filter','成本模型选择Pre/In/Post；概率摘要允许候选超集，最终验证属性','DRAM摘要与PQ；SSD向量、图、属性索引；可能增加误判探索和磁盘索引空间'],
      ['GateANN','发起I/O前检查；FullAdj和PQ支持穿过不匹配节点','DRAM标签CSR、PQ、FullAdj；省向量读取，仍付遍历与内存代价'],
    ],[3.0,5.7,5.7])
    p('PipeANN-Filter以路由和摘要控制候选；GateANN在I/O前过滤，并借FullAdj保留图可达性。前者偏重SSD索引，后者付出DRAM代价，比较时需同时看Recall与时延。')
    section_break(1)

    h('3 测试方案与负载选择')
    h('3.1 数据与过滤查询',2)
    p('使用课程 dataset-v1.0 的 YFCC 真实多标签数据。向量为192维 uint8，距离为 L2；过滤语义是查询标签属于数据点的标签集合。Debug 为10万向量，仅用于构建和排错；Formal 为100万向量，使用预构建索引。两层共享查询向量，但分别使用对应规模的精确 Ground Truth，未混用。Recall@10 为每次查询返回结果与过滤后精确 top-10 的交集占比，再对200次查询求均值。')
    table('表3 Formal测试负载及选择理由',['桶','选择率范围','选择率中位数','过滤强度与查询数'],[
      ['Low','0.250%～0.851%','0.545%','强过滤；200'],
      ['Medium','1.765%～4.995%','2.958%','中等过滤；200'],
      ['High','7.074%～17.089%','12.323%','弱过滤；200'],
    ],[2.0,4.2,3.2,5.0])
    p('每桶包含5个真实标签，每标签40个查询。三档负载覆盖候选极少到候选较多的情形，可观察路由选择和无效遍历的变化。标签的语义和向量分布也随桶变化，因此桶间差异不能全部归因于选择率；本实验没有把它当作严格的单变量干预。')
    h('3.2 参数控制与统计方法',2)
    p('基础实验固定 AIO、单查询线程、beamwidth=8、K=10、mem_L=0、缓存预算0，GateANN FullAdj邻居上限32。High 桶分别运行 PipeANN 的 L=20/40/80 和 GateANN 的 L=160/320/640；Medium、Low 使用代表性 L=40 和320。L 是内部搜索预算，不是固定访问节点数或 I/O 次数，也不能跨系统直接比较数值。性能比较优先考察 Recall 相近的配置。')
    p('每系统每轮5个唯一配置，两系统共10条；独立重复3轮，得到30行。按 system、bucket、L 分组，报告每组中位数，并在图中标出实际最小值至最大值；不挑选最快一轮，不把不同 L 合并，也不把三轮 QPS 相加。不同系统缺失的专用字段保持缺失，不填0。')
    p('Mean Latency 使用查询阶段指标，PipeANN 取程序报告均值，GateANN 按适配器由整数 QPS 的倒数换算，存在少量量化误差。elapsed_seconds 包含索引加载和初始化，不能代替查询时延。peak_rss_kb 的单位为 KiB，覆盖整个查询子进程，换算 MiB 时除以1024。逻辑 I/O 来源于系统内部计数，不能直接等同物理块读次数；GateANN 的 IO_us 主要计量轮询处理代码，不是完整的单次设备服务时间。')
    p('运行环境是共享服务器，基础实验未清空操作系统页面缓存，也未逐轮记录后台负载，不能声称冷缓存或独占环境。补充实验开始、结束的一分钟 load average 分别约22.32、23.27；负载统计是整机值，不能证明目标 CPU 或 SSD 无竞争。正式测试和补充测试在不同时间段完成，优化效果只在补充实验内部的配对对照中计算。')
    h('3.3 主要执行命令',2)
    code(['bash scripts/prepare_pipeann.sh','bash scripts/prepare_gateann.sh',
          'bash scripts/run_debug_validation.sh','bash scripts/download_indexes.sh',
          'bash scripts/check_indexes.sh','bash scripts/run_formal_experiments.sh'])
    p('Debug 阶段还分别调用两个适配器的 build 子命令，tier=debug、构建线程8；构建线程与正式查询线程1不同。正式运行脚本自身执行3轮，不需要手工重复调用3次。2026年10月29日复查时，两套正式索引的 SHA-256 文件校验与 manifest 检查均通过，18个原始查询进程日志齐全，聚合CSV与原始30条记录一致。')
    section_break(2)

    h('4 实验结果与机制分析')
    h('4.1 High负载下的召回率与时延',2)
    figure('01_recall_latency.png','图1 High负载的Recall与时延（3轮中位数及范围）')
    values=[]
    for s,ls in [('pipeann',['20','40','80']),('gateann',['160','320','640'])]:
        for L in ls:
            r=bs[(s,'high',L)]
            values.append(['PipeANN-Filter' if s=='pipeann' else 'GateANN',L,f(r,'recall_percent'),f"{r['mean_latency_us_median']/1000:.3f}",f(r,'qps',1),f(r,'mean_ios')])
    table('表4 High负载的性能中位数',['系统','L','Recall %','时延 ms','QPS','逻辑I/O'],values,[3.4,.8,2.0,2.1,2.2,1.9])
    p('搜索预算增大时，两系统 Recall 和逻辑 I/O 总体上升。PipeANN 的逻辑 I/O 从94.60增至134.00、222.40；GateANN 从24.64增至46.74、88.89。约81% Recall 时，GateANN L=160 的0.624 ms低于 PipeANN L=20 的2.291 ms，中位数约快3.67倍；但两者 Recall 为81.40%与80.90%，并非精确等质量点，且 PipeANN L=20 的时延范围为1.077～2.331 ms，差异的倍数受波动影响。')
    p('在另一组相近质量点，GateANN L=320 的Recall为93.25%、时延1.125 ms，PipeANN L=40为92.20%、1.257 ms，差距已明显缩小。不能仅凭低预算点推断整个精度区间的固定加速比。High L=640 时 GateANN 达98.65% Recall和2.119 ms；PipeANN L=80为97.30%和2.302 ms，这两个点同样需要同时注明精度差异。')
    p('PipeANN 的 L=20 中位数反而高于 L=40，说明当前三轮数据不支持“L增大时延必然单调增加”。L=20的范围很宽，L=40则约1.256～1.346 ms。I/O量随预算增长的趋势仍然清晰；缓存状态、设备竞争或调度均可能影响时延，但缺少设备级追踪，不能把这个异常确定归因于其中某一个因素。原始异常值完整保留。')
    h('4.2 过滤强度与执行路径',2)
    figure('02_selectivity_performance.png','图2 代表性预算下的选择率与性能（3轮中位数及范围）')
    values=[]
    for s,L in [('pipeann','40'),('gateann','320')]:
        for b in ['low','medium','high']:
            r=bs[(s,b,L)]
            values.append(['PipeANN-Filter' if s=='pipeann' else 'GateANN',b.title(),f(r,'recall_percent'),f"{r['mean_latency_us_median']/1000:.3f}",f(r,'mean_ios')])
    table('表5 代表性预算下的性能中位数',['系统','桶','Recall %','时延 ms','逻辑I/O'],values,[3.4,2.3,2.9,2.9,2.9])
    table('表6 查询路径和内部行为的中位数',['桶','PipeANN Pre/In/Post','Gate跳过数','Gate IO/Tunnel/Process μs'],[
      [b.title(),'/'.join(f(bs[('pipeann',b,'40')],m,0) for m in ['pre_filter_queries','in_filter_queries','post_filter_queries']),
       f(bs[('gateann',b,'320')],'filter_skips'),
       '/'.join(f(bs[('gateann',b,'320')],m,0) for m in ['io_time_us','tunnel_time_us','process_time_us'])]
      for b in ['low','medium','high']],[2.0,4.0,2.7,5.7])
    p('PipeANN 在 Low 的200个查询全部选择 Pre 路径，在 Medium 和 High 全部选择 In 路径，Post 均未被采用。Low 在98.60% Recall下耗时0.542 ms，Medium则为91.20%和2.676 ms；这与先利用标签缩小候选集合、避免在稀疏有效区域维持图探索的机制相符。该解释得到路由计数支持，但不是对“选择率导致时延”的单变量因果证明。')
    p('GateANN 的 Low 逻辑 I/O 仅4.38次/查询，时延仍为0.747 ms，Tunnel计时中位数529 μs；其Recall只有34.30%。High L=320 的46.74次I/O对应93.25% Recall和1.125 ms。因此，强过滤确实减少了有效向量读取，却没有自动提高检索质量；内存中仍要穿过大量无效节点。Tunnel、IO和Process是部分代码区间的墙钟计时，不是完整且互斥的总时延分解，也不能直接解释为CPU利用率。')
    p('为检验低Recall的原因，补充实验记录 pipe_search 的真实返回数量，避免把驱动填充的0当成有效结果。Formal Low、L=320的200个查询实际只返回757个ID，平均3.785个；仅25个查询凑齐10个，22个查询无结果。在K=10的口径下，即使所有实际返回均命中Ground Truth，平均Recall上限也只有757/2000=37.85%，接近实测34.30%。这直接表明“返回不足”是低召回的重要来源；哪些图结构和终止条件造成不足，仍需进一步实验区分。')
    h('4.3 空间与内存代价',2)
    resource=[]
    for s,label,extra in [('pipeann','PipeANN-Filter','过滤属性索引及较大的磁盘图'),('gateann','GateANN','标签CSR、PQ、约125.89 MiB FullAdj')]:
        rr=[r for r in rows if r['system']==s]
        resource.append([label,f"{float(rr[0]['index_bytes'])/1024**3:.3f}",f"{min(float(r['peak_rss_kb']) for r in rr)/1024:.2f}～{max(float(r['peak_rss_kb']) for r in rr)/1024:.2f}",extra])
    table('表7 原始正式实验的资源代价',['系统','索引 GiB','进程峰值RSS MiB','主要结构'],resource,[3.0,2.0,4.0,5.4])
    p('在适配器的索引文件统计口径下，PipeANN 约8.425 GiB，GateANN约0.475 GiB。GateANN的磁盘索引更紧凑，但查询进程峰值RSS约411～415 MiB，高于PipeANN约147～149 MiB。表中的索引大小未把公共数据集源文件重复计入，不能理解成完整部署所需的全部磁盘空间。').paragraph_format.keep_together=True
    p('FullAdj和标签CSR可以解释GateANN为何需要更多常驻结构，但不能把两进程RSS差额全部归到FullAdj。RSS覆盖加载、临时CSR数组和查询，编译库、分配器及初始化也会贡献峰值。跨系统逻辑I/O的页面与计数实现不同，因此本报告不把24.64对94.60简单解释为同倍数的物理读流量节省。')
    h('4.4 关键现象与瓶颈判断',2)
    p('现象一是PipeANN在Low比Medium更准且更快。测量证据为98.60%/0.542 ms对91.20%/2.676 ms，机制证据是200次Pre对200次In。可判断执行路线与有效候选规模共同影响代价，潜在瓶颈是In路径的图探索与过滤开销；当前未将其进一步拆分为CPU和设备等待。')
    p('现象二是GateANN在Low读取很少但仍耗时，且只能返回少量有效结果。4.38次逻辑I/O、529 μs Tunnel和平均3.785个真实返回结果指向两个不同问题：内存遍历成本，以及固定预算下的答案不足。本次实现只优化前者；调整预算或搜索终止条件属于另一个可能改变Recall与I/O的设计，不与本次位图收益混在一起。')

    h('5 优化设计实现与验证')
    h('5.1 观察与机制',2)
    p('Observation：沿用第4节数据，Low中的无效节点跳过数中位数为320.69，Tunnel计时529 μs。Mechanism：GateANN的src/search/pipe_search.cpp在普通邻居扩展和Graph Tunneling中，均先对visited执行find，未命中后再insert；节点ID恰好位于连续的[0,N)空间。Bottleneck：重复哈希探测是可避免的CPU/内存访问开销候选，但没有硬件性能计数器证据，不能直接声称其占据了全部Tunnel时间[5]。')
    h('5.2 优化方案与代码实现',2)
    p('Optimization：增加精确的查询内位图，每个节点对应1 bit。访问时计算64位字编号和位掩码，返回该位此前是否为0，再置1；保持原来的“首次发现才加入候选”语义。开关GATEANN_VISITED_MODE=bitmap仅在filter-precheck模式启用，hash模式保留哈希路径。每次查询独立分配并清零位图，没有跨查询共享标记，因此不增加并发查询间的共享写冲突。')
    code(['auto &word = words_[id >> 6];',
          'const uint64_t mask = uint64_t{1} << (id & 63);',
          'const bool fresh = (word & mask) == 0;',
          'word |= mask;',
          'return fresh;'])
    p('实现位于optimization/dense_visited.h，完整上游修改位于patches/gateann_dense_visited.patch，覆盖普通扩展、tunneling和初始节点标记，并增加可选的实际返回数量导出。非法ID会抛出异常，避免越界访问。查询驱动的外层墙钟计时包含位图分配、初始化和释放；性能运行关闭结果导出。所有代码与复现入口：'+REPO+'。')
    h('5.3 验证方案与正确性',2)
    p('Validation Plan：以同一个Release+AIO构建的hash路径为对照，以bitmap为唯一自变量；两组共享新增的计数代码。固定同一CPU 127、数据、预构建索引、L、K、beamwidth、FullAdj和零缓存预算。每配置各运行7个独立进程，桶顺序按种子20261029打乱，模式按轮次交替AB/BA。补充测量共70行，与原基础30行分开保存。固定CPU减少迁移，但不代表该核心独占。')
    p('首先用AddressSanitizer和UndefinedBehaviorSanitizer编译独立集合测试，完成1200030次与std::unordered_set的随机差分，并覆盖0、1、63、64、65、10万和100万节点规模、查询间隔离及非法ID。随后对Debug/Formal共10组配置的所有实际返回ID，独立核验标签谓词、去重、精确L2顺序，并用对应Ground Truth重算Recall。全部语义检查通过；占位0不参与真实返回结果检查。')
    p('最终正确性对照有9组配置的有序top-10文件逐字节一致，另一组Recall仅差0.05个百分点。为检验固定程序自身的波动，对完全相同的hash程序和Debug High L=160连续运行10次，得到85.75%和85.80%两种Recall及两个输出哈希。该控制支持“固定近似系统存在输出波动”的判断；它不能证明所有差异只来自I/O时序。正式对照中五组配置的Recall中位数相同，因此本报告不把0.05个百分点波动当成优化的精度收益。')
    h('5.4 性能结果与预期检验',2)
    figure('03_optimization.png','图3 同构建hash与bitmap对照（7轮中位数及范围）')
    values=[]
    for b,L in [('high','160'),('high','320'),('high','640'),('medium','320'),('low','320')]:
        a,z=os[('hash',b,L)],os[('bitmap',b,L)]
        imp=next(x for x in data['improvements'] if (x['bucket'],x['L'])==(b,L))
        values.append([b.title()+'/'+L,f"{a['mean_latency_us_median']:.2f}",f"{z['mean_latency_us_median']:.2f}",f"{imp['latency_reduction_percent']:.2f}%",f"{z['recall_percent_median']:.2f}"])
    table('表8 优化实验的查询时延中位数',['配置','hash μs','bitmap μs','时延降幅','两组Recall %'],values,[3.1,2.8,2.8,2.6,3.1])
    p('Expected Benefit是减少内存遍历中的集合开销，尤其在强过滤、无效节点多而SSD读取少时受益。Low的中位数从851.79 μs降到730.99 μs，降低14.18%，加速比1.165；Tunnel从606 μs降至533 μs，降低12.05%，逻辑I/O仍为4.38，Recall仍为34.30%。Medium时延降低13.01%。这两个桶的7组配对均更快，且实测范围没有交叠，支持该局部优化改善典型查询成本。')
    p('High L=160/320/640的时延中位数分别降低9.45%、9.95%、10.49%，但L=320和640各有一轮bitmap更慢。其中bitmap最大时延分别达到3.484 ms和6.452 ms，高于hash的对应最大值。因此结论限定为本次测量的中位数改善，不声称尾部、最坏情况或SLA得到改善。图3保留完整范围，没有剔除异常，也没有在共享服务器上推导统计显著性。')
    h('5.5 代价与适用范围',2)
    p('Trade-off：位图占ceil(N/64)×8字节。100万节点时为125000字节，即122.07 KiB；每查询清零成本为O(N/64)，并增加分配与释放。Low中两组进程峰值RSS中位数约402.24/402.26 MiB，差额远小于加载阶段的整体内存，不能据此声称位图无内存成本。该方案没有增加磁盘索引、FullAdj邻居数或结果缓存，也没有修改过滤语义与搜索预算。')
    p('当N很大而单次查询只访问极少节点时，清零整个ID空间可能抵消哈希查找节省，多查询并发还会使位图内存按并发数增长；超大规模或稀疏ID需要分段位图、代际标记或保留哈希路径。当前只在课程数据、单线程和一台共享机器上验证。优化没有解决Low平均返回不足4个答案的质量问题；后续若设计按实际返回数量自适应增加预算，必须把新增I/O和时延作为单独代价重新测量。')

    h('6 调试记录')
    table('表9 关键问题及处理记录',['现象','定位与处理','验证或保留的限制'],[
      ['SSH断开、下载中断','连接路径含Tailscale和本机代理；修复本地服务资源异常并调整SSH保活；利用下载脚本断点续传','正式索引最终通过校验；外部网络稳定性不作为系统性能结论'],
      ['GateANN编译兼容','课程AIO兼容补丁将control block数组访问修正为逐项访问','固定commit、Release+AIO，Debug正确性检查通过'],
      ['补丁初次无法应用','上游YFCC驱动使用CRLF；保留原文件换行后重新生成统一差分','完整补丁反向apply检查通过；源码diff检查通过'],
      ['top-10比对有细小差异','增加实际返回计数与标签/L2独立检查；重复同一hash程序10次','观察到固定程序本身0.05个百分点Recall波动；未声称输出恒等'],
      ['High偶发明显慢轮次','保留全部7轮与范围，不裁剪数据','尚无设备级或调度跟踪，不能确定异常根因'],
    ],[3.0,6.2,5.2])
    p('环境调试与算法修改分别记录。SSH断开可以终止前台下载或脚本，不能根据终端关闭推断任务完成；实际检查文件哈希、进程、命令退出状态及结果行数。最终基础18个查询调用和补充42个性能调用均正常退出，基础结果与补充结果都有对应原始日志。课程提供的一行AIO兼容补丁与本次位图优化分别保存，避免将环境修复误认为算法收益。')

    h('7 实验总结')
    p('实验显示，过滤向量检索的关键在于有效候选的获取方式及其资源代价。PipeANN-Filter通过成本估计选择过滤路径，Low中切换Pre路径后取得98.60% Recall与0.542 ms时延；GateANN利用预I/O判断和内存tunneling减少无效向量读取，在High相近Recall区间表现较快，但Strong-filter Low在固定L=320下只有34.30% Recall。两者并不存在脱离精度和负载的统一优劣排序。')
    p('实测GateANN低I/O场景中的遍历时间后，本实验实现查询内访问位图，在不增加L或改变谓词的前提下，将Low的时延中位数降低14.18%，其余四组中位数也改善；正确性检查与同程序重复实验明确了近似输出的微小波动。优化结果支持降低集合访问成本的方向，但没有提升低选择率下的答案数量。')
    p('基础测试仅3次重复、每桶仅200个查询，真实标签分桶包含分布差异，运行期间存在共享资源竞争且未控制OS冷缓存。RSS为进程生命周期峰值，逻辑I/O也不是物理设备流量。后续若要形成更强的系统结论，应在更多标签、不同规模和受控后台负载下扩展测量，并同时验证精度、典型时延与尾部波动。')

    h('参考文献',newpage=True)
    references=[
      '[1] 课程实验仓库. 基于SSD的过滤向量检索系统课程实验及报告模板. '+
      'https://gitee.com/wei-fangyu/fvs-course-lab （访问日期：2026-10-29）.',
      '[2] Guo H, Lu Y. Achieving Low-Latency Graph-Based Vector Search via Aligning Best-First Search Algorithm with SSD. OSDI 2025:171–186. https://www.usenix.org/conference/osdi25/presentation/guo.',
      '[3] Guo H, Shu J, Lu Y. PipeANN-Filter: An Efficient Filtered Vector Search System on SSD. arXiv:2605.17992, 2026. https://arxiv.org/abs/2605.17992.',
      '[4] Lee N, Cho S, Park J, Kim G. GateANN: I/O-Efficient Filtered Vector Search on SSDs. arXiv:2603.21466v2, 2026. https://arxiv.org/abs/2603.21466v2.',
      '[5] GateANN Authors. GateANN-public源码，固定提交71e87cb. https://github.com/GyuyeongKim/GateANN-public/tree/71e87cbf0e25c0400c0109dd25a64a7c4dccc9dd.',
      '[6] 李耀东. 本实验优化代码、原始结果与统计脚本. '+REPO+' （公开仓库）.',
    ]
    for ref in references:p(ref,False).alignment=WD_ALIGN_PARAGRAPH.LEFT
    p('复现文件：data/baseline/results.csv为30条原始正式数据；data/optimization/results.csv为70条优化对照数据；metadata.json记录命令、开关、CPU亲和性与二进制哈希；correctness.json和async_control.json保存正确性证据。data/raw_logs.zip包含原始日志与逐查询输出。详见仓库README。',False).alignment=WD_ALIGN_PARAGRAPH.LEFT

    doc.core_properties.title=TITLE;doc.core_properties.author=identity['name']
    doc.core_properties.subject='计算机系统设计课程实验'
    doc.core_properties.keywords='SSD; filtered vector search; PipeANN-Filter; GateANN; bitmap'
    # Keep the original header/footer/theme/numbering parts byte-for-byte.
    args.output.parent.mkdir(parents=True,exist_ok=True)
    temp=args.output.with_suffix('.working.docx');doc.save(temp)
    allowed={'[Content_Types].xml','word/document.xml','word/styles.xml',
             'word/_rels/document.xml.rels','docProps/core.xml'}
    with zipfile.ZipFile(args.template) as source,zipfile.ZipFile(temp) as created:
        with zipfile.ZipFile(args.output,'w',compression=zipfile.ZIP_DEFLATED) as final:
            for name in created.namelist():
                payload=source.read(name) if name in source.namelist() and name not in allowed else created.read(name)
                final.writestr(name,payload)
    temp.unlink()
    audit={'template_sha256':hashlib.sha256(args.template.read_bytes()).hexdigest(),
           'docx_sha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),
           'section_count':len(Document(args.output).sections),'body_font':FONT,
           'body_font_pt':10.5,'line_spacing_multiple':1.25,'headings':headings,
           'tables':len(Document(args.output).tables),'figures':3,
           'source_rows':{'baseline':len(rows),'optimization':70},
           'preserved_package_parts':'all original parts except explicitly editable body/styles/relationships/content types/core properties'}
    args.output.with_suffix('.audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    print(json.dumps(audit,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
