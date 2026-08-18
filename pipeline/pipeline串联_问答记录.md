# Pipeline 串联 —— 需求对齐问答记录

> 记录日期：2026-08-17
> 背景：将子项目1（小地图识别）、子项目2（英雄头像识别）、子项目3（数据定位）串联为
> 一键全链路 pipeline：视频 → 抽帧裁切 → 检测 → 网格+符号 → 填充基础表格 + UN/EM 归档。
> 通用产物规范见 `D:\wangzhe_project\项目思路\产物目录命名规范.md`。

## 第一轮提问与回答

### A. 流程与职责划分

1. **子项目2/3 脚本职责重叠**（batch_detect_to_csv.py / add_symbol_to_csv.py / hero_locate.py 功能交叉）？
   → **子项目2 只出 (px, py)；子项目3 的 `hero_locate.py` 负责网格 + 符号。**
   → 补充：**EM（无法识别）的归档由子项目2 实现**，无法识别的素材放入子项目2 对应产物文件夹。

2. **串联形态**？
   → **写一个 `pipeline.py` 一键跑完全链路**（视频→抽帧裁切→检测→符号→填充表格）。
   → **中间产物（小地图帧）跑完后保留**——现阶段不成熟，需要用来复盘。

3. **每局录像 = 一个 document？**
   → **是。一个 doc 对应一个视频。** 视频素材放在
   `D:\wangzhe_project\apply\document2\video_footage\SVID_20260813_154004_1.mp4`
   （视频已就位，835MB）。

### B. 时间基准

4. **开局时刻如何确定**？
   → **pipeline 中时间基准固定从 40s 开始。**

5. **抽帧间隔**？
   → **每 3 秒抽帧一次**（与总纲验收口径一致：15 分钟 ≈ 300 采样点）。

6. **网格换算公式不一致**（总纲 round vs 代码 floor）？
   → **维持代码的 floor（`col = int(px // 9.3)`，`row = int(py // 9.3)`），修改总纲。** ✅ 已改

### C. 数据与配置

7. **符号映射表唯一源**？
   → **用 `D:\wangzhe_project\王者视频解析\子项目3_数据定位\小地图位置.md`。** ✅ 总纲引用已改

8. **英雄模板如何传入**？
   → 子项目2 已定型为**"双掩膜环形模板 + 融合打分"**方案
   （参照 `子项目2_英雄头像识别\release\README.md`），模型为 `release\hero_model.pkl`
   （当前仅标注露娜·绿框）。

9. **红蓝方 / 双地图问题**？
   → **现阶段先固定处理，地图问题之后再解决。**

### D. 验收与边界

10. **端到端验收标准**？
    → **15 分钟视频 → 300 采样点 → CSV 完整输出，一路到 `基础表格_填充结果.xlsx` + UN/EM 归档。
    现阶段所有过程中的素材全部保留，方便查询路径问题。**

## 待确认问题（第二轮）—— 已全部确认（2026-08-17）

1. **EM 归档目录名**：
   → **确认：`apply\documentN\subproject2\EM\`（CSV + 截图，与子项目3 的 UN/EM 同风格）；
   UN 归档仍留在 `subproject3\UN\`。**

2. **每个 document 内的三阶段布局**：
   → **确认：**
   - `documentN\video_footage\`：原始视频（输入）
   - `documentN\subproject1\`：抽帧+裁切后的小地图帧 + extraction_log.csv
   - `documentN\subproject2\`：(px, py) 坐标 CSV + EM 归档
   - `documentN\subproject3\`：符号 CSV + 基础表格_填充结果.xlsx + UN 归档

3. **pipeline.py 位置**：
   → **确认：`D:\wangzhe_project\pipeline\pipeline.py`，作为跨子项目调度入口。**

4. **目标英雄**：
   → **确认：document2 这局是露娜，沿用现有 `hero_model.pkl`。**

5. **40s 时间基准与超长处理**：
   → **确认：抽帧从视频 00:40 开始（前 40 秒不抽），直到视频结束；
   超出基础表格 17 列（26:10）的部分丢弃。**

6. **3 秒抽帧下的格子拼接**：
   → **确认：维持不去重，接受 `b0_b0_b1_b1_b1` 这类长串。**

7. **子项目1 接入方式**：
   → **确认：参照 `子项目1_小地图识别\README.md`；子项目1 按新规范重写输出逻辑，
   但不改动原脚本——在 `D:\wangzhe_project\pipeline` 中创建新的副本。**

## 实施记录（2026-08-17）

- 已实现 `pipeline\pipeline.py` + `stage1_extract.py` + `stage2_detect.py` + `stage3_locate_fill.py`，
  详见 `pipeline\README.md`。
- 专用环境 `pipeline\.venv`：opencv 4.10 / sklearn 1.6.1 / numpy 2.0.2（与模型训练版本对齐）。
- 约束遵守：只修改 pipeline 目录；子项目1/2/3 与原素材均为只读引用，未做任何改动。
- document2 实跑结果：阶段1 263 帧（正常 251 / 异常 12）；阶段2 found 217 / EM 34；
  阶段3 填充 53 格 / UN 75。产物在 `apply\document2\subproject1~3\`。
- 性能问题与对策：阶段2 检测单进程约 0.3 帧/秒，已加 6 进程并行 + 断点续跑。

