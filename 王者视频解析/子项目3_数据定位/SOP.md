# SOP —— 基础表格填充标准操作流程

> 适用脚本：`fill_base_table.py`（本目录下）
> 最近更新：2026-08-15

## 1. 目的

将小地图英雄定位的采样数据（`hero_grid_result.csv`）按 15 秒时间格填入基础表格，
并导出未标注点（UN）与空识别帧（EM）的明细及配套截图，供后续人工复核与地图补标。

## 2. 输入文件

| 文件 | 默认路径 | 说明 |
| --- | --- | --- |
| 采样数据 | `D:\wangzhe_project\screenshot_collection\test_collection\test1\hero_grid_result.csv` | 列：file, time_s, row, col, status, px, py, 符号 |
| 映射表 | `子项目3_数据定位\小地图位置.md` | CSV 格式内容，列：行,列,符号（20×20 网格） |
| 基础表格 | `D:\wangzhe_project\相关素材\表格\基础表格.xlsx` | 时间网格模板，**原件不会被修改** |
| 配套截图 | 与采样 CSV 同目录的 `frame_*.jpg` | 用于 UN/EM 文件夹归档 |

## 3. 操作步骤

1. 确认三个输入文件路径无误（如有变化，先改脚本头部的路径配置，见第 5 节）。
2. 运行脚本：

   ```bash
   python "D:\wangzhe_project\王者视频解析\子项目3_数据定位\fill_base_table.py"
   ```

3. 查看控制台输出，确认：
   - 映射表条目数、采样点数符合预期；
   - "填充格子"数量合理；
   - UN / EM 的事件数、图片复制数，有无"缺失图片"提示。
4. 打开 `apply\document1\subproject3\基础表格_填充结果.xlsx` 抽查若干格子。
5. 复核 `apply\document1\subproject3\` 下的 `UN/`、`EM/` 文件夹：
   - `UN/`：优先处理——对照截图确认英雄实际位置，决定是否在小地图位置.md 中补标该 (row, col)；
   - `EM/`：确认是否为画面遮挡/死亡等合理空帧。

## 4. 输出文件

**命名约定（可追踪、可复盘）**：产物按"产物根目录 + 阶段名"放置，即
`<APPLY_ROOT>\<STAGE_NAME>\`，当前为 `D:\wangzhe_project\apply\document1\subproject3`。
阶段文件夹（`subproject3`）由脚本**自动创建**，无需手动建立；本目录只保留核心文档与脚本。
通用规范全文见 `D:\wangzhe_project\项目思路\产物目录命名规范.md`。

| 输出 | 位置 | 说明 |
| --- | --- | --- |
| `基础表格_填充结果.xlsx` | `apply\document1\subproject3\` | 填充后的表格（每次运行覆盖） |
| `UN\UN.csv` + 截图 | `apply\document1\subproject3\UN\` | 未标注点明细：file, time_s, row, col, count |
| `EM\EM.csv` + 截图 | `apply\document1\subproject3\EM\` | 空识别帧明细：file, time_s, count |

注意：`UN\`、`EM\` 文件夹每次运行会先清空再生成，内有手动添加的内容请先备份。

## 5. 换数据时的配置修改

打开 `fill_base_table.py`，修改文件头部的路径常量：

- `CSV_PATH`：新的采样 CSV 路径（截图默认取其同目录，可用 `IMAGE_DIR` 另行指定）；
- `MAP_PATH`：映射表路径；
- `BASE_TABLE_PATH`：基础表格模板路径；
- `APPLY_ROOT` / `STAGE_NAME`：产物根目录与阶段名，产物自动输出到 `<APPLY_ROOT>\<STAGE_NAME>\`
  （阶段文件夹自动创建）；`OUTPUT_PATH` 为结果表格文件名，一般不用改。

网格参数（一般不用改）：`GRID_START_S=40`（表格起点秒数）、`CELL_SPAN_S=15`（格宽）、
`ROWS_PER_COL=6`（每列行数）。

## 6. 处理规则速查

- 符号只由 (row, col) 查映射表得到，CSV 自带的"符号"列不使用；
- time_s < 40 的采样点丢弃；
- 格子为 15 秒时间窗，左闭右开，边界点归入后一格；
- 单元格值：符号 / `EM`（empty 帧）/ `UN`（未标注点），同格多事件按时间顺序用 `_` 拼接；
- 15:40 之后无数据的格子留空。

## 7. 常见问题

- **UN 太多**：说明映射表覆盖不足，按 `UN.csv` 中 (row, col) 出现情况补标 `小地图位置.md` 后重跑。
- **EM 异常多**：检查视频画面（死亡、遮挡、小地图被盖住）或上游识别脚本。
- **提示缺失图片**：确认截图与采样 CSV 在同一目录，或修改 `IMAGE_DIR`。
- **换对局方（红/蓝方镜像）**：按 `项目3.md` 的设想，未来可能需要两份映射表，届时为 `MAP_PATH` 增加按对局选择即可。
