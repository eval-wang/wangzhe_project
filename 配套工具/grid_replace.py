# -*- coding: utf-8 -*-
"""
王者荣耀 20x20 网格符号处理工具
================================

处理规则（两个阶段，均基于快照单轮执行，替换完成后停止、不连锁扩散）：

阶段一 · 8 邻域替换
    检测每个中文字符格周围 8 个格子，若存在英文（如 B/W），
    则用该中文符号替换这些英文。

阶段二 · 中心对称替换
    以网格中心为对称点（(r, c) -> (19-r, 19-c)），将中文字符映射到
    对称方向另一边：若对称格是英文，则替换为 “敌方”+中文符号；
    若对称格不存在英文，则不写入（空格保持为空）。

用法：
    python grid_replace.py                     # 默认读取同目录 input.csv，输出 result.csv
    python grid_replace.py 输入.csv            # 指定输入文件
    python grid_replace.py 输入.csv 输出.csv   # 指定输入与输出文件

输入 / 输出 CSV 格式一致（行,列,符号），只修改符号内容，不增删行。
"""
import csv
import re
import sys
from pathlib import Path

N = 20
CHINESE_RE = re.compile(r'[一-鿿]')

# 8 邻域方向
DIRS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def is_chinese(s):
    return bool(s) and bool(CHINESE_RE.search(s))


def is_english(s):
    return bool(s) and s.isascii() and s.isalpha()


def main():
    script_dir = Path(__file__).resolve().parent
    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 else script_dir / "input.csv"
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else script_dir / "result.csv"

    if not in_path.exists():
        print(f"错误：找不到输入文件 {in_path}")
        sys.exit(1)

    # ---------- 1. 读取输入并建网格 ----------
    grid = [[""] * N for _ in range(N)]
    input_rows = []  # 保持输入行顺序: (r, c)
    with open(in_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            r, c = int(row["行"]), int(row["列"])
            if not (0 <= r < N and 0 <= c < N):
                print(f"警告：跳过越界坐标 ({r},{c})")
                continue
            grid[r][c] = row["符号"]
            input_rows.append((r, c))

    # ---------- 2. 阶段一：8 邻域替换（快照单轮，替换后停止） ----------
    snapshot = [row[:] for row in grid]
    changes = []

    for r in range(N):
        for c in range(N):
            src = snapshot[r][c]
            if not is_chinese(src):
                continue
            for dr, dc in DIRS:
                nr, nc = r + dr, c + dc
                if 0 <= nr < N and 0 <= nc < N and is_english(snapshot[nr][nc]):
                    if grid[nr][nc] != src:
                        grid[nr][nc] = src
                        changes.append((nr, nc, snapshot[nr][nc], src))

    # ---------- 3. 阶段二：中心对称替换 ----------
    # 对称点: (r, c) -> (N-1-r, N-1-c)
    # 对称格为英文 -> 替换为 "敌方"+中文; 否则不写入（空格保持为空）
    snapshot2 = [row[:] for row in grid]  # 再次快照，防止“敌方XX”被二次映射
    mirror_changes = []

    for r in range(N):
        for c in range(N):
            src = snapshot2[r][c]
            if not is_chinese(src):
                continue
            mr, mc = N - 1 - r, N - 1 - c
            target = snapshot2[mr][mc]
            if is_english(target):
                new_val = "敌方" + src
                if grid[mr][mc] != new_val:
                    grid[mr][mc] = new_val
                    mirror_changes.append((mr, mc, target, new_val, r, c))

    # ---------- 4. 输出（与输入格式一致：行,列,符号） ----------
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["行", "列", "符号"])
        for r, c in input_rows:
            w.writerow([r, c, grid[r][c]])

    print(f"阶段一 8邻域替换：{len(changes)} 处")
    for r, c, old, new in changes:
        print(f"  ({r},{c})  {old} -> {new}")
    print(f"阶段二 中心对称替换：{len(mirror_changes)} 处")
    for mr, mc, old, new, r, c in mirror_changes:
        print(f"  ({r},{c}) 的对称格 ({mr},{mc})  {old} -> {new}")
    print(f"结果已保存: {out_path}")


if __name__ == "__main__":
    main()
