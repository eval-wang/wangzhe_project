"""
子项目3 数据定位 —— 英雄位置批量检测与符号标注
==================================================
三步流程整合：
  1. 调用子项目2的检测模型，逐帧获取英雄像素坐标或空值(None)
  2. 将像素坐标映射到 20×20 网格 (row, col)，原点左上角
  3. 依据 小地图位置.md 的 (行,列)->符号 映射表，追加"符号"列

输出 CSV 字段：
  file, time_s, row, col, status, px, py, 符号

用法：
  python hero_locate.py <小地图目录> [--out 输出csv] [--symbol 符号映射md]

示例：
  python hero_locate.py D:\\wangzhe_project\\screenshot_collection\\test_collection\\test1
"""
import argparse
import csv
import re
import sys
from pathlib import Path

# 引入子项目2的检测能力
_PARENT = Path(__file__).resolve().parent.parent / "子项目2_英雄头像识别"
sys.path.insert(0, str(_PARENT))
from hero_detect import detect, imread_safe  # noqa: E402

GRID_SIZE = 20        # 20×20 网格
CELL = 9.3            # 186 / 20 = 9.3 px/格

# 默认符号映射表（与 scv简化.md 内容一致，亦存于同目录 小地图位置.md）
DEFAULT_SYMBOL_MD = Path(__file__).resolve().parent / "小地图位置.md"


def parse_time_s(filename: str):
    """从 'frame_0000_0.0s.jpg' 中提取时间秒数（浮点）。"""
    m = re.search(r"_(\d+\.?\d*)s\.jpg$", filename)
    return float(m.group(1)) if m else None


def pixel_to_grid(px, py):
    """像素坐标 -> 网格坐标 (row, col)，原点左上角。"""
    col = int(px // CELL)
    row = int(py // CELL)
    col = max(0, min(GRID_SIZE - 1, col))
    row = max(0, min(GRID_SIZE - 1, row))
    return row, col


def load_symbol_map(md_path):
    """读取 (行,列,符号) 映射表，返回 {(row, col): 符号}。"""
    symbol_map = {}
    for line in Path(md_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        row_s, col_s, sym = parts[0], parts[1], parts[2]
        if not row_s.isdigit() or not col_s.isdigit():
            continue  # 跳过表头
        symbol_map[(int(row_s), int(col_s))] = sym
    return symbol_map


def main():
    ap = argparse.ArgumentParser(description="批量检测小地图英雄位置并输出网格坐标+符号 CSV")
    ap.add_argument("directory", help="小地图目录（含 frame_*.jpg）")
    ap.add_argument("--out", default=None, help="输出 CSV 路径（默认存到目录下 hero_grid_result.csv）")
    ap.add_argument("--symbol", default=str(DEFAULT_SYMBOL_MD), help="符号映射表 md 路径")
    args = ap.parse_args()

    d = Path(args.directory)
    frames = sorted(d.glob("frame_*.jpg"))
    if not frames:
        print(f"目录中无 frame_*.jpg: {d}")
        sys.exit(1)

    symbol_map = load_symbol_map(args.symbol)
    print(f"符号映射表条目: {len(symbol_map)}")

    out = Path(args.out) if args.out else d / "hero_grid_result.csv"

    header = ["file", "time_s", "row", "col", "status", "px", "py", "符号"]
    rows = [header]
    found_cnt = empty_cnt = symbol_cnt = 0

    for p in frames:
        img = imread_safe(p)
        if img is None:
            print(f"[跳过] 无法读取: {p.name}")
            continue
        coord, _ = detect(img)
        time_s = parse_time_s(p.name)
        sym = ""

        if coord is not None:
            px, py = coord
            row, col = pixel_to_grid(px, py)
            sym = symbol_map.get((row, col), "")
            if sym:
                symbol_cnt += 1
            rows.append([p.name, time_s if time_s is not None else "", row, col,
                         "found", px, py, sym])
            found_cnt += 1
        else:
            rows.append([p.name, time_s if time_s is not None else "", "", "",
                         "empty", "", "", ""])
            empty_cnt += 1

    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerows(rows)

    print(f"总帧数: {len(rows) - 1}，found: {found_cnt}，empty: {empty_cnt}，带符号: {symbol_cnt}")
    print(f"CSV 已保存: {out}")


if __name__ == "__main__":
    main()
