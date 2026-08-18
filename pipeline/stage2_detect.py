# -*- coding: utf-8 -*-
"""
Pipeline 阶段2 —— 英雄头像检测（子项目2 包装 + EM 归档）
==========================================================
只读调用子项目2 的检测能力（双掩膜环形模板 + 融合打分，hero_detect.py），
对阶段1 的小地图帧逐帧检测，**只输出 (px, py) 像素坐标**（网格+符号归阶段3）。

产物（<APPLY_ROOT>\\<document>\\subproject2\\，自动创建）：
  - hero_position.csv：file, time_s, status, px, py（status = found / empty）
  - EM\\EM.csv + EM\\frame_*.jpg：未识别帧（empty）的明细与截图归档

特性：
  - 断点续跑：hero_position.csv 逐条落盘；中断后重跑自动跳过已检测帧，
    EM 归档每次根据完整 CSV 重建。
  - 多进程并行：检测为 CPU 密集（实测约 0.3 帧/秒/进程），
    默认开 6 个 worker 并行（hero_detect.py 只读不改）。

依赖（只读引用子项目2）：
  - 检测：王者视频解析\\子项目2_英雄头像识别\\hero_detect.py
  - 模型：王者视频解析\\子项目2_英雄头像识别\\release\\hero_model.pkl（露娜·绿框）
"""

import csv
import os
import re
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

# ---------------- 子项目2 只读引用 ----------------
SUBPROJECT2_DIR = Path(r"D:\wangzhe_project\王者视频解析\子项目2_英雄头像识别")
if str(SUBPROJECT2_DIR) not in sys.path:
    sys.path.insert(0, str(SUBPROJECT2_DIR))

EMPTY_MARK = "EM"
CSV_HEADER = ["file", "time_s", "status", "px", "py"]
DEFAULT_WORKERS = 6


def parse_time_s(filename: str):
    """从 'frame_0000_0.0s.jpg' 中提取时间秒数（浮点）。"""
    m = re.search(r"_(\d+\.?\d*)s\.jpg$", filename)
    return float(m.group(1)) if m else None


def _detect_one(path_str: str):
    """worker：检测单帧，返回 CSV 行（模块级函数，Windows spawn 可 pickle）。"""
    from hero_detect import detect, imread_safe  # 子项目2（只读）
    p = Path(path_str)
    img = imread_safe(p)
    time_s = parse_time_s(p.name)
    time_s = time_s if time_s is not None else ""
    if img is None:
        return [p.name, time_s, "unreadable", "", ""]
    coord, _ = detect(img)
    if coord is not None:
        return [p.name, time_s, "found", coord[0], coord[1]]
    return [p.name, time_s, "empty", "", ""]


def load_done(csv_path: Path) -> set:
    """读取已检测帧的文件名（断点续跑用）。"""
    if not csv_path.exists():
        return set()
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        return {r["file"] for r in csv.DictReader(f)}


def rebuild_em_archive(csv_path: Path, frames_dir: Path, em_dir: Path):
    """根据完整 hero_position.csv 重建 EM 归档（先清空再生成）。"""
    empty_rows = []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["status"] == "empty":
                empty_rows.append((r["file"], r["time_s"]))

    if em_dir.exists():
        shutil.rmtree(em_dir)
    em_dir.mkdir(parents=True)

    counter = Counter(name for name, _ in empty_rows)
    with open(em_dir / f"{EMPTY_MARK}.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["file", "time_s", "count"])
        for name, cnt in sorted(counter.items()):
            time_s = next(t for n, t in empty_rows if n == name)
            writer.writerow([name, time_s, cnt])

    copied = 0
    for name in counter:
        src = frames_dir / name
        if src.exists():
            shutil.copy2(src, em_dir / name)
            copied += 1
    return len(empty_rows), copied


def detect_frames(frames_dir, output_dir, limit=None, workers=DEFAULT_WORKERS):
    """
    对小地图帧目录逐帧检测英雄像素坐标（断点续跑 + 多进程）。

    Args:
        frames_dir: 阶段1 输出目录（含 frame_*.jpg）
        output_dir: 阶段2 产物目录（<APPLY_ROOT>\\<document>\\subproject2），自动创建
        limit: 本轮最多新检测的帧数（None = 全部剩余帧）
        workers: 并行进程数（1 = 串行）

    Returns:
        dict: {"csv_path", "total", "found", "empty", "em_dir", "remaining"}
    """
    frames_dir = Path(frames_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)  # 阶段文件夹自动创建

    frames = sorted(frames_dir.glob("frame_*.jpg"))
    if not frames:
        raise FileNotFoundError(f"目录中无 frame_*.jpg: {frames_dir}")

    csv_path = output_dir / "hero_position.csv"
    done = load_done(csv_path)
    todo = [p for p in frames if p.name not in done]
    if limit is not None:
        todo = todo[:limit]

    print(f"[阶段2] 输入帧 {len(frames)}，已检测 {len(done)}，本轮待检测 {len(todo)}，"
          f"并行进程 {workers}")

    new_file = not csv_path.exists()
    t0 = time.time()
    completed = 0
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(CSV_HEADER)

        if workers > 1 and len(todo) > 1:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=workers) as pool:
                for row in pool.map(_detect_one, [str(p) for p in todo], chunksize=4):
                    writer.writerow(row)
                    f.flush()
                    completed += 1
                    if completed % 20 == 0:
                        speed = completed / (time.time() - t0)
                        print(f"[阶段2] 本轮 {completed}/{len(todo)}（{speed:.1f} 帧/秒）...")
        else:
            for p in todo:
                writer.writerow(_detect_one(str(p)))
                f.flush()
                completed += 1
                if completed % 10 == 0:
                    speed = completed / (time.time() - t0)
                    print(f"[阶段2] 本轮 {completed}/{len(todo)}（{speed:.1f} 帧/秒）...")

    # 汇总 + 重建 EM 归档
    found = empty = 0
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["status"] == "found":
                found += 1
            elif r["status"] == "empty":
                empty += 1
    em_dir = output_dir / EMPTY_MARK
    _, em_copied = rebuild_em_archive(csv_path, frames_dir, em_dir)
    remaining = len(frames) - len(load_done(csv_path))

    print(f"[阶段2] 累计: found {found}，empty(EM) {empty}，EM 归档 {em_copied} 张截图，"
          f"剩余未检测 {remaining}（本轮耗时 {(time.time() - t0) / 60:.1f} 分钟）")
    return {"csv_path": csv_path, "total": found + empty, "found": found,
            "empty": empty, "em_dir": em_dir, "remaining": remaining}


if __name__ == "__main__":
    # 支持命令行分批运行：python stage2_detect.py <帧目录> <输出目录> [--limit N] [--workers N]
    import argparse
    ap = argparse.ArgumentParser(description="阶段2 英雄检测（断点续跑 + 多进程）")
    ap.add_argument("frames_dir")
    ap.add_argument("output_dir")
    ap.add_argument("--limit", type=int, default=None, help="本轮最多检测帧数")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="并行进程数")
    args = ap.parse_args()
    detect_frames(args.frames_dir, args.output_dir, args.limit, args.workers)
