"""
子项目2 批量检测脚本 —— 输出英雄坐标到 CSV
================================================
对小地图目录全部帧逐一检测，将像素坐标映射到 20×20 网格，输出 CSV。

用法：
  python batch_detect_to_csv.py <目录> [输出csv路径]

示例：
  python batch_detect_to_csv.py D:\\wangzhe_project\\screenshot_collection\\test_collection\\test1

CSV 字段：
  file      帧文件名
  time_s    文件名中的时间（秒）
  row       网格行 0-19（从上到下）
  col       网格列 0-19（从左到右）
  status    found / empty
  px, py    像素坐标（empty 时留空）

网格换算：col = floor(px / 9.3)，row = floor(py / 9.3)，原点左上角。
"""
import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hero_detect import detect, imread_safe

GRID_SIZE = 20        # 20×20 网格
CELL = 9.3            # 186 / 20 = 9.3 px/格


def parse_time_s(filename: str):
    """从 'frame_0000_0.0s.jpg' 中提取时间秒数（浮点）。"""
    m = re.search(r"_(\d+\.?\d*)s\.jpg$", filename)
    return float(m.group(1)) if m else None


def pixel_to_grid(px, py):
    """像素坐标 -> 网格坐标 (row, col)。"""
    col = int(px // CELL)
    row = int(py // CELL)
    # 边界保护：极端情况下钳制在 0-19
    col = max(0, min(GRID_SIZE - 1, col))
    row = max(0, min(GRID_SIZE - 1, row))
    return row, col


def main():
    ap = argparse.ArgumentParser(description="批量检测小地图并输出网格坐标 CSV")
    ap.add_argument("directory", help="小地图目录")
    ap.add_argument("output", nargs="?", default=None, help="输出 CSV 路径（默认存到目录下 hero_grid_result.csv）")
    args = ap.parse_args()

    d = Path(args.directory)
    frames = sorted(d.glob("frame_*.jpg"))
    if not frames:
        print(f"目录中无 frame_*.jpg: {d}")
        sys.exit(1)

    out = Path(args.output) if args.output else d / "hero_grid_result.csv"

    rows = []
    found_cnt = 0
    empty_cnt = 0

    for p in frames:
        img = imread_safe(p)
        if img is None:
            print(f"[跳过] 无法读取: {p.name}")
            continue
        coord, _ = detect(img)
        time_s = parse_time_s(p.name)

        if coord is not None:
            px, py = coord
            row, col = pixel_to_grid(px, py)
            rows.append([p.name, time_s if time_s is not None else "", row, col,
                         "found", px, py])
            found_cnt += 1
        else:
            rows.append([p.name, time_s if time_s is not None else "", "", "",
                         "empty", "", ""])
            empty_cnt += 1

    # 写 CSV
    header = ["file", "time_s", "row", "col", "status", "px", "py"]
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

    print(f"总帧数: {len(rows)}，检测到(found): {found_cnt}，空值(empty): {empty_cnt}")
    print(f"CSV 已保存: {out}")


if __name__ == "__main__":
    main()
