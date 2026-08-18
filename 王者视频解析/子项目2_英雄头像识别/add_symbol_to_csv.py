"""
给 hero_grid_result.csv 追加"符号"列
======================================
根据 scv简化.md 的 (行,列)->符号 映射表，为 CSV 中每行的网格坐标
(row, col) 查询对应符号，写入新列"符号"。empty 帧或映射表中不存在的
格子留空。

用法：
  python add_symbol_to_csv.py <csv路径> <映射md路径> [输出csv路径]
"""
import argparse
import csv
from pathlib import Path


def load_symbol_map(md_path):
    """读取 scv简化.md，返回 {(row, col): 符号} 字典。"""
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
            continue  # 跳过表头"行,列,符号"
        symbol_map[(int(row_s), int(col_s))] = sym
    return symbol_map


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", help="hero_grid_result.csv 路径")
    ap.add_argument("md_path", help="scv简化.md 路径")
    ap.add_argument("output", nargs="?", default=None, help="输出 csv（默认覆盖原文件）")
    args = ap.parse_args()

    symbol_map = load_symbol_map(args.md_path)
    print(f"符号映射表条目: {len(symbol_map)}")

    csv_path = Path(args.csv_path)
    out_path = Path(args.output) if args.output else csv_path

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)

    header = rows[0]
    # 找到 row/col 列下标
    idx_row = header.index("row")
    idx_col = header.index("col")
    # 追加"符号"列
    header.append("符号")

    out_rows = [header]
    filled = 0
    for r in rows[1:]:
        row_s, col_s = r[idx_row], r[idx_col]
        sym = ""
        if row_s != "" and col_s != "":
            key = (int(row_s), int(col_s))
            sym = symbol_map.get(key, "")
            if sym:
                filled += 1
        r.append(sym)
        out_rows.append(r)

    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerows(out_rows)

    print(f"已追加符号列，共 {filled} 行匹配到符号")
    print(f"输出: {out_path}")


if __name__ == "__main__":
    main()
