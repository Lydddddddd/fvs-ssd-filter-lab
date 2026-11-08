# SSD 过滤向量检索系统性能比较与 GateANN 访问位图优化

计算机系统设计课程实验。基础实验使用统一的 YFCC 数据、查询负载和预构建索引，比较 PipeANN-Filter 与 GateANN 的 Recall@10、平均查询时延、逻辑 I/O 和峰值内存。优化实验将 GateANN 查询过程中的 visited 哈希集合替换为稠密位图，测量节点访问标记开销的变化。

## 代码结构

| 文件 | 功能 |
| --- | --- |
| [optimization/dense_visited.h](optimization/dense_visited.h) | 查询内精确访问位图的 C++ 实现 |
| [patches/gateann_dense_visited.patch](patches/gateann_dense_visited.patch) | GateANN 集成补丁，包含 hash/bitmap 切换和查询结果导出 |
| [patches/gateann_aio_compat.patch](patches/gateann_aio_compat.patch) | 课程提供的 AIO 编译兼容补丁 |
| [scripts/prepare_optimization.sh](scripts/prepare_optimization.sh) | 准备固定版本的 GateANN 源码、应用补丁并编译 |
| [scripts/run_optimization_experiment.py](scripts/run_optimization_experiment.py) | 检查查询正确性并执行交替顺序的对照实验 |
| [scripts/validate_query_outputs.py](scripts/validate_query_outputs.py) | 检查实际返回数量、过滤条件、ID 去重、L2 排序和 Recall |
| [scripts/run_async_control.py](scripts/run_async_control.py) | 重复 hash 模式，测量异步查询输出的波动 |
| [scripts/analyze_results.py](scripts/analyze_results.py) | 汇总测量 CSV，绘制性能比较和优化结果图 |
| [tests/test_dense_visited.cpp](tests/test_dense_visited.cpp) | 位图差分、边界、查询隔离及非法 ID 测试 |

## 优化方法

节点 ID 位于 `[0,N)` 时，位图用一个二进制位记录节点是否已访问。`insert(id)` 首次访问返回 `true`，重复访问返回 `false`，供图遍历代码判断是否继续处理节点。

存储量为 `ceil(N/64) × 8` 字节。Formal 数据的 N 为 1000000，位图占用 125000 字节，约 122.07 KiB。每条查询创建独立位图，初始化和释放成本计入查询阶段的墙钟时延。

补丁在 GateANN 的 filter-precheck 路径中接入位图。通过环境变量选择访问集合实现。

```bash
GATEANN_VISITED_MODE=hash
GATEANN_VISITED_MODE=bitmap
```

`GATEANN_RESULT_DUMP=/path/prefix` 在查询计时结束后导出结果 ID 和实际返回数量，用于正确性检查。实验运行脚本分别配置正确性验证和性能测量阶段。

## 实验设置与结果

实验平台为 Ubuntu 22.04.4 x86-64、AMD EPYC 7542 和 Samsung 990 EVO Plus NVMe SSD。查询使用单个 CPU 线程。优化对照固定 CPU 127，按固定随机种子打乱负载桶顺序，逐轮交替 hash/bitmap 的执行顺序。

| 项目 | 设置 |
| --- | --- |
| 数据 | YFCC，uint8，192 维，L2 距离 |
| 数据规模 | Debug 10 万条，Formal 100 万条 |
| 查询负载 | Low、Medium、High，每桶 200 条查询 |
| 查询参数 | AIO，K=10，threads=1，beamwidth=8，mem_L=0，cache_budget=0 |
| GateANN FullAdj | R=32 |
| High 的搜索预算 | PipeANN L=20/40/80，GateANN L=160/320/640 |
| Medium/Low 的搜索预算 | PipeANN L=40，GateANN L=320 |
| 重复次数 | 基础实验每组 3 次，优化对照每组 7 次 |
| 汇总方式 | 中位数及观测最小值、最大值 |

基础实验共有 30 条测量结果，优化对照共有 70 条。优化批次的五组结果如下，两个模式的 Recall 中位数相同。

| 负载 | L | hash 时延中位数（μs） | bitmap 时延中位数（μs） | 时延下降 |
| --- | ---: | ---: | ---: | ---: |
| High | 160 | 668.90 | 605.69 | 9.45% |
| High | 320 | 1162.79 | 1047.12 | 9.95% |
| High | 640 | 2392.34 | 2141.33 | 10.49% |
| Medium | 320 | 965.25 | 839.63 | 13.01% |
| Low | 320 | 851.79 | 730.99 | 14.18% |

Low、Medium、High L=160 的 7 轮配对中，bitmap 均更快。High L=320 和 L=640 各有 6 轮更快。测量在共享服务器上完成，统计脚本使用全部轮次展示波动。

`mean_ios` 使用各系统内部的逻辑读取计数，两套系统的页组织和计数口径需结合时延一起解释。`peak_rss_kb` 以 KiB 记录查询子进程加载、初始化和查询期间的峰值 RSS。GateANN 平均查询时延按 `1000000 / QPS` 换算，操作系统页面缓存采用默认状态。

## 正确性验证

- 位图测试包含 1200030 次差分插入，并检查字边界、查询隔离及非法 ID。
- Debug/Formal 共 10 组配置通过过滤条件、实际 ID 唯一性和精确 L2 排序检查。9 组配置的 hash/bitmap 有序 top-10 输出逐字节一致，另 1 组 Recall 相差 0.05 个百分点。
- 对同一个 hash 程序重复 10 次，Debug High L=160 的 Recall 出现 85.75% 和 85.80% 两种结果，作为异步查询输出波动的对照。
- 结果检查使用 `pipe_search` 的实际返回数量，分别统计有效 ID 和填充位置。Formal Low 的 200 条查询共返回 757 个有效 ID，25 条查询返回满 10 个，22 条查询返回 0 个。

## 复现步骤

运行环境使用 Linux、Python 3、CMake、支持 C++17 的编译器和 `taskset`。按照课程 README 准备数据集、依赖和预构建索引，并完成 Debug 验证。课程入口为 <https://gitee.com/wei-fangyu/fvs-course-lab>。

固定源码版本如下。

| 仓库 | 提交 |
| --- | --- |
| 课程仓库 | `e44eab5d1b040ffdebc80374a13b304a9c4d37de` |
| PipeANN-Filter | `2ec84fe20c37dc3cc236b66f7eba31c0cc80bf1e` |
| GateANN | `71e87cbf0e25c0400c0109dd25a64a7c4dccc9dd` |

### 1. 基础实验

在已准备好的课程仓库中运行三轮正式实验。以下路径中的 `/path/to/fvs-course-lab` 替换为课程仓库的实际路径。

```bash
cd /path/to/fvs-course-lab
FVS_EXPERIMENT_ID=baseline FVS_REPEATS=3 bash scripts/run_formal_experiments.sh
```

汇总 CSV 位于课程仓库的 `course_runs/experiments/baseline/results.csv`。

### 2. 编译并运行优化实验

```bash
git clone https://github.com/Lydddddddd/fvs-ssd-filter-lab.git
cd fvs-ssd-filter-lab

bash scripts/prepare_optimization.sh /path/to/fvs-course-lab

python3 scripts/run_optimization_experiment.py \
  --course-root /path/to/fvs-course-lab \
  --optimized-repo /path/to/fvs-course-lab/systems/GateANN-dense-opt \
  --output results/bitmap \
  --repeats 7

python3 scripts/run_async_control.py \
  --experiment results/bitmap \
  --repeats 10
```

`--output` 指向新建的实验目录。脚本默认从当前进程允许的 CPU 中选取一个，也可通过 `--cpu` 指定。运行结果、命令、正确性检查和日志保存在该目录，性能 CSV 为 `results/bitmap/results.csv`。

### 3. 汇总与绘图

将 `--font` 替换为本机可用的中文字体文件路径。

```bash
python3 -m pip install -r requirements.txt
python3 scripts/analyze_results.py \
  --baseline /path/to/fvs-course-lab/course_runs/experiments/baseline/results.csv \
  --optimization results/bitmap/results.csv \
  --output results/figures \
  --font /path/to/SimSun.ttf
```

程序生成三组 PNG/PDF/SVG 图表及汇总 CSV，分别比较 Recall 与时延、不同选择率下的性能、hash/bitmap 优化效果。

### 4. 单独运行位图测试

```bash
mkdir -p build
c++ -std=c++17 -O1 -g \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  -I optimization tests/test_dense_visited.cpp \
  -o build/test_dense_visited
./build/test_dense_visited
```
