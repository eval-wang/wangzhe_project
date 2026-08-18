# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 新增

- `LICENSE`：MIT 协议（首次发布遗漏，补充声明）

## [1.0.0] - 2026-08-17

首个可全链路运行的版本。

### 新增

- `pipeline.py` 一键调度入口（`--document` 指定对局）
- `stage1_extract.py`：阶段1 规范化副本——40s 起抽帧、3s 间隔、至视频结束，
  产物自动归入 `subproject1\`（子项目1 原脚本零改动）
- `stage2_detect.py`：英雄检测 + EM 归档
  - 多进程并行（默认 6 worker，0.3 → 1.9 帧/秒）
  - 断点续跑（逐条落盘，重跑自动跳过已检测帧）
- `stage3_locate_fill.py`：floor 网格映射 + 符号查表 + 时间格填表 + UN 归档
- 专用虚拟环境 `.venv`：opencv 4.10.0.84 / sklearn 1.6.1 / numpy 2.0.2
  （与模型训练版本对齐，规避 OpenCV 5.0 与 sklearn 1.9 兼容问题）
- 工程文档：ARCHITECTURE / TECHNICAL_DESIGN / DATA_CONTRACTS / DEVELOPMENT /
  ROADMAP / CONTRIBUTING / CHANGELOG

### 验证

- document2（13:45 / 60.4fps / 1280×582）全链路实跑：
  阶段1 263 帧（正常 251 / 异常 12）；阶段2 found 217 / EM 34；
  阶段3 填充 53 格 / UN 75。总耗时约 5 分钟。
- 检测链路冒烟测试：test1 已知帧输出 `(95, 143)`，与历史结果一致。
