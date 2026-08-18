# 王者视频解析 Pipeline

> 将王者荣耀对局录像一键转化为结构化时空数据：从原始 MP4 到带语义符号的轨迹表格。

[![Python](https://img.shields.io/badge/python-3.13-blue)]() [![OpenCV](https://img.shields.io/badge/opencv-4.10-green)]() [![scikit--learn](https://img.shields.io/badge/sklearn-1.6.1-orange)]()

## 这是什么

本仓库是"王者荣耀打野轨迹自动提取系统"的**全链路调度层**，把三个独立子项目串联为一条一键流水线：

```
原始视频 (MP4)
    │
    ▼  阶段1：抽帧 + ROI 裁切（RF 回归模型定位小地图）
186×186 小地图帧序列
    │
    ▼  阶段2：英雄头像检测（双掩膜环形模板 + 融合打分）
(px, py) 像素坐标序列 + EM 归档（未识别帧）
    │
    ▼  阶段3：网格映射 + 符号查表 + 时间格填表
基础表格_填充结果.xlsx + UN 归档（未标注点）
```

最终产出一张 **15 秒 × 90 秒时间格表格**，每个格子记录该时间窗内英雄在小地图上的语义位置
（如 `b0` 己方蓝 buff、`r1` 己方红区、`EM` 未识别、`UN` 未标注点），用于复盘打野路线与刷野效率。

## 特性

- **一键全链路**：`python pipeline.py --document document2`，约 5 分钟处理一局 14 分钟录像
- **断点续跑**：检测阶段逐条落盘，中断后重跑自动跳过已完成帧
- **多进程加速**：CPU 密集的检测阶段 6 进程并行（单进程 0.3 帧/秒 → 并行 1.9 帧/秒）
- **产物可追踪**：按 `产物根目录 + 阶段名` 组织，每局录像一个 document，路径即可复盘
- **问题帧自动归档**：未识别帧（EM）与未标注点（UN）自动导出 CSV + 截图，支撑地图持续补标
- **零侵入集成**：只读调用三个子项目的模型与代码，原项目文件不做任何修改

## 快速开始

### 环境准备

```bash
cd pipeline
python -m venv .venv
.venv\Scripts\python.exe -m pip install opencv-python-headless==4.10.0.84 scikit-learn==1.6.1 numpy==2.0.2 joblib openpyxl
```

> 版本必须锁定，原因见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

### 准备一局录像

```
apply\document2\
└── video_footage\
    └── SVID_20260813_154004_1.mp4    ← 每个 document 恰好一个 mp4
```

### 运行

```bash
.venv\Scripts\python.exe pipeline.py --document document2
```

### 产物

```
apply\document2\
├── video_footage\       原始视频（输入）
├── subproject1\         小地图帧 + extraction_log.csv
├── subproject2\         hero_position.csv + EM\（未识别帧归档）
└── subproject3\         hero_grid_result.csv + 基础表格_填充结果.xlsx + UN\（未标注点归档）
```

填充表格示例（单元格 = 15 秒时间窗内的位置事件序列）：

| | 0:40 | 2:10 | 3:40 |
|---|---|---|---|
| 0:15 | `r2_r2_r0_r0_r1` | `b2_b2_b1_UN_UN` | `a0_a1_b2_b2_b0` |
| 0:30 | `r1_UN_UN_b0_b3` | `m0_UN_B0_B0_B0` | … |

## 文档

| 文档 | 内容 |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构设计：分层、数据流、关键设计决策 |
| [docs/TECHNICAL_DESIGN.md](docs/TECHNICAL_DESIGN.md) | 技术路径：三阶段算法原理与参数 |
| [docs/DATA_CONTRACTS.md](docs/DATA_CONTRACTS.md) | 数据契约：CSV schema、目录与命名约定 |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 开发环境、版本锁定原因、调试指南 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 已知限制与路线图 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 分支工作流与贡献规范 |
| [CHANGELOG.md](CHANGELOG.md) | 版本历史 |
| [pipeline串联_问答记录.md](pipeline串联_问答记录.md) | 需求对齐决策全过程 |

## 性能参考

荣耀 MagicBook Pro 14，13:45 对局（60.4fps / 1280×582）：

| 阶段 | 耗时 | 产出 |
|---|---|---|
| 阶段1 抽帧裁切 | ~2.5 min | 263 帧（正常 251 / 异常 12） |
| 阶段2 英雄检测（6 进程） | ~2 min | found 217 / EM 34 |
| 阶段3 定位填表 | 秒级 | 填充 53 格 / UN 75 |

## 当前限制

- 仅支持 **1280×582** 分辨率录像（阶段1 模型训练集限定）
- 仅识别 **露娜·绿框**（阶段2 模型当前标注范围）
- 时间基准固定为视频 00:40，未做开局自动校准
- 单一阵营视角，红蓝方地图差异问题待解决

详见 [docs/ROADMAP.md](docs/ROADMAP.md)。

## License

本项目采用 [MIT License](LICENSE)。
