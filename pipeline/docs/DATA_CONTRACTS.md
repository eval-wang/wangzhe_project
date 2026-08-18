# 数据契约

> 本文件是阶段间接口与产物格式的**唯一权威定义**。
> 修改任何 schema 前必须先改本文档，并同步 CHANGELOG。

## 1. 目录与命名约定

### 1.1 document 组织

```
<APPLY_ROOT>\              产物根目录（当前：D:\wangzhe_project\apply）
└── documentN\             一局录像 = 一个 document（N 递增，人工分配）
    ├── video_footage\     输入：恰好一个 mp4
    ├── subproject1\       阶段1 产物（脚本自动创建）
    ├── subproject2\       阶段2 产物（脚本自动创建）
    └── subproject3\       阶段3 产物（脚本自动创建）
```

通用规范全文：`项目思路\产物目录命名规范.md`。

### 1.2 帧文件命名

```
frame_{序号:04d}_{时间戳:.1f}s.jpg
例：frame_0000_40.0s.jpg
```

时间戳 = 该帧在视频中的秒数（一位小数）。各阶段均用正则
`_(\d+\.?\d*)s\.jpg$` 从文件名解析时间，**不得更改此命名**。

## 2. 阶段间接口

### 2.1 阶段1 → 阶段2：帧目录

| 项 | 约定 |
|---|---|
| 内容 | `frame_*.jpg`（186×186，JPEG q95）+ `extraction_log.csv` |
| 阶段2 只读 | 阶段2 不得在 subproject1 目录写入任何内容 |

`extraction_log.csv`（utf-8-sig）：

| 列 | 类型 | 说明 |
|---|---|---|
| 序号 | int | 从 0 递增（含被跳过的帧） |
| 时间(分:秒) | string | `MM:SS` |
| 时间戳(秒) | float | 一位小数 |
| 文件名 | string | 异常跳过时为空 |
| 原始尺寸 | string | 如 `188×190` |
| 状态 | string | `正常` / `跳过(尺寸异常)` |

### 2.2 阶段2 → 阶段3：hero_position.csv

utf-8-sig，**阶段3 的唯一输入**（阶段3 不感知检测实现）：

| 列 | 类型 | 说明 |
|---|---|---|
| file | string | 帧文件名 |
| time_s | float | 秒 |
| status | enum | `found` / `empty` / `unreadable` |
| px | int | status=found 时有效，否则空 |
| py | int | 同上 |

行顺序不保证时间有序（多进程并行写入）；**消费方必须自行按 time_s 排序**。

## 3. 阶段3 产物

### 3.1 hero_grid_result.csv

utf-8-sig，按 time_s 升序：

| 列 | 类型 | 说明 |
|---|---|---|
| file | string | 帧文件名 |
| time_s | float | 秒 |
| row | int | 网格行 0-19（empty 时为空） |
| col | int | 网格列 0-19（empty 时为空） |
| status | enum | `found` / `empty` |
| px, py | int | 像素坐标（empty 时为空） |
| 符号 | string | 映射符号；found 但未标注时为空 |

### 3.2 基础表格_填充结果.xlsx

- 模板：`相关素材\表格\基础表格.xlsx`（**只读，永不改动**）
- Sheet1：第 1 行为列头（0:40 起，90 秒/列，17 列），A 列 2-7 行为行标签（6 行）
- 单元格 (行 r, 列 c) = 时间窗 `[40 + c×90 + r×15, +15s)`，左闭右开
- 单元格值：符号 / `EM` / `UN`，多事件按时间序 `_` 拼接不去重；无采样留空
- 单元格格式强制为文本（`@`），防止 Excel 误解析

### 3.3 标记语义

| 标记 | 含义 | 责任阶段 | 归档位置 |
|---|---|---|---|
| `EM` | 检测失败（empty/unreadable） | 阶段2 | `subproject2\EM\` |
| `UN` | 检测成功但 (row,col) 未标注 | 阶段3 | `subproject3\UN\` |

### 3.4 归档 CSV

`EM.csv`（utf-8-sig）：`file, time_s, count`（按 file 聚合）

`UN.csv`（utf-8-sig）：`file, time_s, row, col, count`（按 file+row+col 聚合）

归档目录（含截图）**每次运行先清空再重建**，不得放入手工内容。

## 4. 符号映射表

唯一正本：`王者视频解析\子项目3_数据定位\小地图位置.md`
（CSV 格式内容：`行,列,符号`，182 个点位，utf-8）。

网格换算：`col = floor(px / 9.3)`，`row = floor(py / 9.3)`，钳制 [0,19]。

## 5. 兼容性承诺

- 新增列只能追加到末尾，不得改变既有列顺序与含义；
- `frame_*_{t}s.jpg` 命名与 `EM`/`UN` 标记为跨阶段公共契约，变更需三阶段同步；
- 任何破坏性变更必须升级 CHANGELOG 主版本号。
