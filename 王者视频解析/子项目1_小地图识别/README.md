# 子项目1 小地图自动识别

> **版本**：v1.1  
> **日期**：2026-08-06  
> **状态**：可用，持续改进中

---

## 一、快速开始（TL;DR）

```bash
cd "D:\wangzhe_project\王者视频解析\子项目1_小地图识别"
python extract_minimaps.py \
    --video "D:\视频路径.mp4" \
    --output "D:\输出目录" \
    --start 0 \
    --end 99999 \
    --interval 10
```

- `--start` / `--end`：截取时间范围（秒），设为 `0` / `99999` 可覆盖整个视频
- `--interval`：截取间隔（秒），默认 `10`
- 输出：`186×186` 小地图 + `extraction_log.csv` 记录文档

---

## 二、标准工作流

### 2.1 从视频提取小地图（主流程）

```
视频 (.mp4)
    │
    ▼
extract_minimaps.py       ← 每 N 秒截取一帧 → RF模型预测ROI → 裁切 → 缩放到186×186
    │
    ▼
输出目录/
├── frame_0000_0.0s.jpg   ← 186×186 小地图
├── frame_0001_10.0s.jpg
├── ...
└── extraction_log.csv     ← 记录文档（时间、尺寸、状态）
```

### 2.2 模型训练/更新流程

```
原始游戏截图
    │
    ▼
标注工具.py               ← 人工标注小地图 ROI → 生成 labels.json
    │
    ▼
core/train_model.py       ← 用 labels.json 训练 RandomForest 模型 → roi_model.pkl
    │
    ▼
extract_minimaps.py       ← 使用新模型提取小地图
```

### 2.3 批量预测（图片目录）

```bash
python core/predict.py --dir "D:\图片目录"
# 输出：_cropped/（裁切图）、_viz/（可视化）、_predictions.json（预测结果）
```

---

## 三、文件结构

```
子项目1_小地图识别/
├── README.md                 ← 本文档
│
├── extract_minimaps.py       ← 【主程序】从视频批量提取小地图
├── 标注工具.py               ← 【工具】人工标注 GUI（Tkinter）
│
├── roi_model.pkl             ← 训练好的 RandomForest 模型
├── labels.json               ← 38 条训练标注数据
│
├── core/                     ← 核心模块
│   ├── train_model.py        ← 训练脚本（233维特征 + RF回归）
│   ├── predict.py            ← 批量预测脚本
│   └── process_materials.py  ← 模板匹配自动标注
│
└── release/                  ← v1.0 发布备份（内容与根目录一致）
    ├── README.md
    ├── extract_minimaps.py
    ├── 标注工具.py
    ├── roi_model.pkl
    ├── labels.json
    └── core/
```

### 配套数据路径

```
D:\wangzhe_project\
├── screenshot_collection\          ← 训练数据
│   └── train_collection\
│       ├── train1\full\            ← 22 张 1280×582（已标注）
│       ├── train5\                 ← 11 张 1280×582（已标注）
│       └── preview_screens\full\   ← 5 张 1599×n（已标注）
│
├── selected_screenshot_collection\ ← 提取输出
│   └── train1\                     ← 本次提取结果（72张）
│
└── 相关素材\视频素材\              ← 源视频
```

---

## 四、技术方案

### 4.1 模型

| 项目 | 说明 |
|------|------|
| 模型类型 | RandomForestRegressor（300棵树, max_depth=14），MultiOutputRegressor 包装 |
| 特征维度 | 233维 |
| 特征组成 | 左上区域12×16网格(192维) + 灰度直方图(24维) + HSV统计(6维) + 梯度(2维) + 颜色比例(2维) + 密度(1维) + 全图参数(2维) + 边缘先验(4维) |
| 预测目标 | 归一化坐标 `(l/W, t/H, r/W, b/H)` |
| 交叉验证 IoU | ~0.972 |

### 4.2 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--video` | 训练营.mp4 | 视频文件路径 |
| `--output` | test/ | 输出目录 |
| `--start` | 300 | 起始时间（秒） |
| `--end` | 400 | 结束时间（秒） |
| `--interval` | 10 | 截取间隔（秒） |
| `--size` | 186 | 输出正方形尺寸 |
| `--max-deviation` | 0.03 | 尺寸偏差阈值（3%），超过则跳过 |

### 4.3 输出 CSV 格式

| 序号 | 时间(分:秒) | 时间戳(秒) | 文件名 | 原始尺寸 | 状态 |
|------|------------|-----------|--------|---------|------|
| 0 | 00:00 | 0.0 | frame_0000_0.0s.jpg | 188×190 | 正常 |
| 1 | 05:29 | 329.7 | | 194×199 | 跳过(尺寸异常) |

---

## 五、限定范围

### 5.1 当前支持

| 项目 | 限定 |
|------|------|
| 支持分辨率 | **1280×582**（训练集主要设备） |
| 小地图位置 | 画面左上角 |
| 裁切边界 | A 层（包含顶部状态栏和外圈装饰） |
| 输出尺寸 | 统一 186×186 正方形 |
| 异常检测 | 裁切尺寸与第一帧偏差 > 3% 时跳过 |

### 5.2 不支持场景

- 其他分辨率（如 1280×720、1599×n）→ 模型未充分训练
- 敌方视角（小地图翻转）→ 会误判位置
- 小地图被 UI 面板完全遮挡 → 触发异常检测跳过
- 竖屏设备 → 未训练

---

## 六、环境要求

```bash
pip install opencv-python numpy scikit-learn joblib
```

标注工具额外需要：
```bash
pip install pillow
```

---

## 七、历史版本

| 版本 | 日期 | 变更 |
|------|------|------|
| v0.1 ~ v0.7 | 2026-07~08 | 从 HoughCircles → 模板匹配 → RF，逐步迭代 |
| **v1.0** | 2026-08-05 | 3%阈值、186×186统一输出、CSV记录 |
| **v1.1** | 2026-08-06 | 文档优化、修复路径拼写、添加标准工作流说明 |
