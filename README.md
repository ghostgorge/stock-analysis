# Serenity 三闸门 · 确定性选股管线 —— 分步实施指南

> **架构一句话**:阶段0~2和闸门1全部是Python确定性代码,参数被git看管;
> Claude Code只做两件事——闸门3证据检索、写终榜报告。LLM没有修改规则和提名股票的入口。
>
> **本指南按顺序做完即可上线。标注【必做】的不能跳,标注【可选】的看需要。**

---

## 第0步【必做】准备环境(约15分钟)

需要的东西:一台能上网的电脑(Win/Mac/Linux均可)、Python 3.10+、git、Claude Code。

```bash
# 0.1 检查Python(低于3.10去 python.org 装新版)
python --version        # Windows
python3 --version       # Mac/Linux

# 0.2 检查git(没有则 git-scm.com 下载安装)
git --version

# 0.3 安装Claude Code(任选其一)
npm install -g @anthropic-ai/claude-code     # 有Node.js的话
# 或去 claude.com/claude-code 下载原生安装包

# 0.4 验证
claude --version
```

> Windows用户建议全程使用 PowerShell 或 Windows Terminal,下文命令通用。

---

## 第1步【必做】部署项目并建立git基线(约5分钟)

**git基线不是可有可无的仪式——合规自检的sha256比对、参数修订流程,全部依赖它。**

```bash
# 1.1 解压 serenity_pipeline.zip 到你的工作目录,例如:
#     Windows: D:\quant\serenity    Mac/Linux: ~/quant/serenity
cd ~/quant/serenity

# 1.2 初始化git并提交基线
git init
git add -A
git commit -m "baseline: Serenity管线初始版本,参数与判定逻辑冻结起点"

# 1.3 (强烈建议)推到私有远程仓库,防本地误删
# git remote add origin <你的私有仓库地址> && git push -u origin master
```

目录结构确认:

```
serenity/
├── CLAUDE.md              # Claude Code的角色约束(自动加载,不用手动喂)
├── config/params.yaml     # 全部冻结参数——修改必须走第10步流程
├── data/calendar_ipo.csv  # 大额IPO日历(R6抽血窗口),第7步维护
├── src/                   # 7个模块:数据层/指标/阶段0-3/编排器
└── output/                # 每日产物:candidates_*.json 和 report_*.md
```

---

## 第2步【必做】安装Python依赖(约3分钟)

```bash
pip install akshare pandas pyyaml pyarrow
# 国内网络慢可加清华源:
# pip install akshare pandas pyyaml pyarrow -i https://pypi.tuna.tsinghua.edu.cn/simple
```

冒烟测试(验证所有模块能正常导入):

```bash
python -c "import sys; sys.path.insert(0,'src'); import indicators, datasource, stage0_gate, stage1_screen, stage2_structure, stage3_risk; print('全部模块 OK')"
```

---

## 第3步【必做】首次运行与读懂输出(约10分钟)

```bash
python src/runner.py --source akshare
```

首次运行可能要几分钟(akshare逐票拉日线)。完成后看 `output/candidates_YYYYMMDD.json`,四个关键块:

| 块 | 含义 | 你要看什么 |
|---|---|---|
| `mood` / `calendar_gate` | 情绪档位 + 抽血窗口 | `calendar_gate.hit=true` 时同链板块已被排除 |
| `candidates` | 通过全部代码闸门的候选 | 每只带止损价、风险%、建议仓位、`source`来源审计字段 |
| `watchlist` | 观察清单 | A=风险%>8 / B=回踩未走完 / C=多项压线,各自写明差在哪 |
| `compliance` | 合规自检 | `params_sha256`、`stage2_code_sha256`、扩池轮数 |

**candidates为空是正常且常见的结果**——右侧三买结构本来就不是天天有。json里的 `verdict` 会写明"今日无Serenity信号"。

---

## 第4步【必做】接入Claude Code,跑通完整闭环(约10分钟)

```bash
cd ~/quant/serenity
claude          # 在项目根目录启动,CLAUDE.md自动生效
```

然后对Claude Code说(每天同一句,建议存成文本模板):

```
读取 output/ 下今天的 candidates json,按 CLAUDE.md 执行:
对每只候选做闸门3检索(每只≤2次搜索),打分,产出终榜报告存为
output/report_今日日期.md。空信号照空信号格式输出。
```

Claude Code会:检索业绩预告/研报/订单硬证据 → 无证据的移观察清单 → 打分≥70入终榜 → 报告末尾附合规自检块并核对sha256。**它不能加名单外的票、不能改参数、不能重跑放宽条件——CLAUDE.md和json的来源审计双重锁死。**

第一次跑通后,检查 report 里的合规自检四项是否全绿,闭环就算建立了。

---

## 第5步【可选】接入你的通达信MCP替换akshare数据

akshare够用但有限速和字段变动风险;你已有通达信MCP,可以这样接:

```bash
# 5.1 把MCP注册进Claude Code(命令换成你的MCP实际启动方式)
claude mcp add tdx -- <你的通达信MCP启动命令>
claude mcp list          # 确认已挂载

# 5.2 让Claude Code做"取数落地"(它只搬运数据,不做筛选):
```

对Claude Code说:

```
用tdx MCP取当日全市场快照和候选池120日前复权日线,
按 src/datasource.py 顶部注释的数据契约写入 data/cache/
(snapshot.parquet / daily_代码.parquet / hot_boards.txt),不要做任何筛选。
```

之后运行改为 `python src/runner.py --source tdx`。策略代码零改动。

---

## 第6步【必做·上线前唯一的硬门槛】回测校准阶段2参数(约1~2个下午)

**当前stage2的阈值(1.8倍量比、3%击穿容忍、回踩量50%等)是v0启发式,没经过你的案例校准前,整个系统只能纸面运行,不能实盘。** 这一步同时终结上次"2%阈值到底严不严"那类争论——从此参数争议用数据裁决,不靠盘中感觉。

```bash
# 6.1 建立案例库:凭你的缠论功底,人工挑选并标注
#     正例20~30个:你认可的历史三买(股票代码+回踩确认日),
#     反例10~20个:形似三买但随后失败的结构。
#     存为 backtest/cases.csv: code,confirm_date,label(1/0)
mkdir backtest
```

然后把校准脚本交给Claude Code写(这是它擅长且被允许的工作):

```
写 backtest/calibrate.py:读取cases.csv,对每个案例取确认日前120日日线,
用 stage2_structure.stage2_check 判定,输出混淆矩阵(命中率/误杀率/放行率);
再对 breakout_vol_ratio∈[1.5,2.2]、platform_pierce_tolerance_pct∈[2,5]
做网格扫描,输出各组合的查准/查全,推荐帕累托最优参数组。
```

拿到推荐参数后,走第10步的正式流程改params.yaml。**误杀率(把真三买拒之门外)和放行率(放进假三买)的取舍由你定——Serenity哲学下宁可误杀。**

---

## 第7步【必做】维护IPO日历(每周5分钟)

`data/calendar_ipo.csv` 驱动R6抽血闸门,格式:

```csv
name,code,raise_amount,subscribe_date,payment_date,chain_boards
长鑫科技,688825,29500000000,2026-07-16,2026-07-20,半导体|存储器|封测|半导体材料
```

- 只需录入**募资>100亿**的项目(阈值在params.yaml可查)
- `chain_boards` 用 `|` 分隔,窗口期内这些板块整体不入池
- 每周一花5分钟对照交易所新股日历更新;后续可让Claude Code写个
  `ak.stock_xgsglb_em()` 自动更新脚本(README待办)
- **长江存储、紫光展锐进入发行阶段时,第一时间录入——这是你用真金白银换来的规则**

---

## 第8步【必做】固化每日工作流(每天约15分钟)

```
16:00 收盘后
  │ python src/runner.py --source akshare     (~5分钟)
  ▼
16:10 打开Claude Code,发送第4步的固定指令      (~5分钟)
  ▼
16:20 阅读 output/report_*.md
  ├─ 有信号 → 对照你的纪律卡片,决定次日是否挂单(止损价、仓位报告里都有)
  └─ 空信号 → 看观察清单的"次日复扫触发条件",收工
```

三条铁律:
1. **只在盘后运行**——盘中跑一次就会想跑第二次,那是横跳的温床
2. **报告里的止损价即下单时的条件单价格**,下单和止损同时设置,不存在"先买再说"
3. 报告合规自检任何一项异常(hash不符/轮数超限)→ 当日报告作废,先查原因

---

## 第9步【可选】自动化定时运行

```bash
# Mac/Linux: crontab -e 加一行(交易日16:05自动跑数据层)
5 16 * * 1-5 cd ~/quant/serenity && python src/runner.py --source akshare >> output/cron.log 2>&1

# Windows: 任务计划程序 → 创建基本任务 → 每天16:05 →
#   程序: python  参数: src\runner.py --source akshare  起始于: D:\quant\serenity
```

闸门3检索仍建议手动触发——那15分钟里你顺便复核了市况,值得留着。

---

## 第10步【必做】参数修订的唯一合法流程

任何人(包括你、包括Claude)想改 params.yaml 或 stage2_structure.py:

```bash
# 盘后进行,四步缺一不可
git checkout -b param-revision-YYYYMMDD          # 1. 开分支
# 2. 修改参数,并运行 backtest/calibrate.py,把结果存入 backtest/
git add -A
git commit -m "param: 击穿容忍3%→4%;依据:回测误杀率18%→9%,放行率+2%,详见backtest/20260801.md"
git checkout master && git merge param-revision-YYYYMMDD   # 3. 合并
# 4. 次日生效(当日已产出的报告不重跑)
```

**盘中改参数在技术上拦不住你,但runner的sha256审计会让它在报告里留下永久记录。**
这套流程的意义和你的纪律卡片相同:不是消灭违规,是让违规变得可见、有摩擦、要签名。

---

## 常见问题

| 症状 | 处置 |
|---|---|
| akshare报错/字段变动 | `pip install -U akshare`;仍不行则切第5步的tdx数据源 |
| 拉日线很慢或被限速 | 正常,数据层可挂后台;或改用tdx MCP本地数据 |
| 连续多日candidates为空 | 大概率是市况事实(60日普跌/无三买结构),不是bug;去看watchlist差在哪条 |
| 报告hash与git不符 | 有人盘中改过参数或判定代码,`git diff` 查明,当日报告作废 |
| 想加新判据(如筹码锁仓量化) | 合法途径:开分支实现+案例回测+合并,同第10步 |

---

## 风险声明

本系统输出为概率优势筛选,不构成投资建议;突发基本面利空优先于一切技术信号;
所有交易决策及其结果由使用者本人承担。参数未经第6步回测校准前,仅供纸面跟踪。
