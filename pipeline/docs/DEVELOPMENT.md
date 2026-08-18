# 开发指南

> 环境搭建、运行调试、常见问题。新贡献者从这里开始。

## 1. 环境搭建

```bash
cd D:\wangzhe_project\pipeline
python -m venv .venv
.venv\Scripts\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple ^
    opencv-python-headless==4.10.0.84 scikit-learn==1.6.1 numpy==2.0.2 joblib openpyxl
```

**必须使用 `.venv` 运行**，系统/托管 Python 缺少 cv2 与 sklearn。
版本锁定原因见 [TECHNICAL_DESIGN.md](TECHNICAL_DESIGN.md#版本锁定决策重要)。

环境自检：

```bash
.venv\Scripts\python.exe -c "import cv2, sklearn, numpy, joblib, openpyxl; print(cv2.__version__, sklearn.__version__, numpy.__version__)"
# 期望输出：4.10.0 1.6.1 2.0.2
```

## 2. 运行方式

### 2.1 全链路

```bash
.venv\Scripts\python.exe pipeline.py --document document2
```

### 2.2 分阶段运行（调试常用）

```bash
# 阶段1（约 2.5 分钟）
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); import stage1_extract; \
  stage1_extract.extract(r'<视频路径>', r'apply\document2\subproject1')"

# 阶段2（断点续跑；--limit 控制本轮帧数，--workers 控制并行度）
.venv\Scripts\python.exe stage2_detect.py apply\document2\subproject1 apply\document2\subproject2 --limit 50 --workers 6

# 阶段3（秒级）
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); import stage3_locate_fill; \
  stage3_locate_fill.locate_and_fill(r'apply\document2\subproject2\hero_position.csv', \
  r'apply\document2\subproject1', r'apply\document2\subproject3')"
```

### 2.3 冒烟测试（改代码后必跑）

```bash
# 用已知答案的测试帧验证检测链路未被破坏
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); sys.path.insert(0, r'D:\wangzhe_project\王者视频解析\子项目2_英雄头像识别'); \
  from hero_detect import detect, imread_safe; \
  print(detect(imread_safe(r'D:\wangzhe_project\screenshot_collection\test_collection\test1\frame_0000_0.0s.jpg'))[0])"
# 期望输出：(95, 143)
```

## 3. 代码结构速览

| 文件 | 关键入口 | 说明 |
|---|---|---|
| `pipeline.py` | `run(document, apply_root)` | 调度：定位视频 → 三阶段串联 |
| `stage1_extract.py` | `extract(video, out_dir, ...)` | 函数级复用，参数均有默认值 |
| `stage2_detect.py` | `detect_frames(frames_dir, out_dir, limit, workers)` | 并行 + 断点续跑 |
| `stage3_locate_fill.py` | `locate_and_fill(pos_csv, frames_dir, out_dir)` | 纯计算，秒级 |

## 4. 常见问题（FAQ）

**Q：Windows 上多进程报错 / 卡死？**
A：worker 函数必须定义在模块顶层（`_detect_one`），且入口有
`if __name__ == "__main__"` 保护。新增 worker 函数时遵守同样规则。

**Q：阶段2 跑到一半被杀，结果丢了？**
A：不会。CSV 逐条落盘，直接重跑同一命令即可自动续跑。

**Q：EM 归档里的截图和 CSV 对不上？**
A：EM/UN 归档每次依据最新 CSV 全量重建，重跑阶段2/3 后自动一致。

**Q：加载模型时报一堆 unpickle 警告？**
A：sklearn 版本不对。确认 `pip show scikit-learn` 为 1.6.1。

**Q：`cv2 has no attribute HOGDescriptor`？**
A：装成了 OpenCV 5.x。降级到 `opencv-python-headless==4.10.0.84`。

**Q：想处理非 1280×582 的视频 / 非露娜英雄？**
A：这属于子项目1/2 的模型能力范围，需要在对应子项目中标注训练。
本仓库通过"修改建议"机制提出需求（见 CONTRIBUTING.md 第 4 节）。

## 5. 只读依赖清单

以下路径**严禁修改**（本仓库只读引用）：

- `王者视频解析\子项目1_小地图识别\`（roi_model.pkl、core/）
- `王者视频解析\子项目2_英雄头像识别\`（hero_detect.py、release/hero_model.pkl）
- `王者视频解析\子项目3_数据定位\小地图位置.md`
- `相关素材\表格\基础表格.xlsx`

## 6. 发布前检查单

- [ ] `.venv/` 已在 .gitignore 中（默认已配置）
- [ ] 冒烟测试通过（输出 `(95, 143)`）
- [ ] CHANGELOG.md 已更新
- [ ] 文档中的性能数据/限制与最新实测一致
- [ ] 已选择开源协议并添加 LICENSE 文件
