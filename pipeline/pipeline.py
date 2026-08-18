# -*- coding: utf-8 -*-
"""
Pipeline 一键调度入口 —— 视频 → 填充表格 + UN/EM 归档
======================================================
串联三个阶段（产物规范见 项目思路\\产物目录命名规范.md）：

  阶段1  stage1_extract.py       视频 → 抽帧(40s起/3s间隔/至结束) → ROI裁切 → 186×186 小地图
  阶段2  stage2_detect.py        小地图 → 双掩膜环形模板检测 → (px,py) CSV + EM 归档
  阶段3  stage3_locate_fill.py   (px,py) → 网格+符号 → 填充基础表格 + UN 归档

用法：
  python pipeline.py --document document2
  python pipeline.py --document document2 --apply-root D:\\wangzhe_project\\apply

目录约定（一个 document 对应一局录像）：
  <apply-root>\\<document>\\video_footage\\*.mp4   ← 输入视频（唯一一个 mp4）
  <apply-root>\\<document>\\subproject1\\          ← 阶段1 产物（自动创建）
  <apply-root>\\<document>\\subproject2\\          ← 阶段2 产物（自动创建）
  <apply-root>\\<document>\\subproject3\\          ← 阶段3 产物（自动创建）

运行环境：pipeline\\.venv（opencv / scikit-learn / joblib / openpyxl / numpy）
"""

import argparse
import sys
import time
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPELINE_DIR))

DEFAULT_APPLY_ROOT = Path(r"D:\wangzhe_project\apply")


def find_video(document_dir: Path) -> Path:
    """在 documentN\\video_footage\\ 下找到唯一的 mp4。"""
    footage = document_dir / "video_footage"
    videos = sorted(footage.glob("*.mp4")) if footage.exists() else []
    if not videos:
        raise FileNotFoundError(f"未找到视频: {footage}（应放置一个 mp4）")
    if len(videos) > 1:
        raise RuntimeError(f"video_footage 下有 {len(videos)} 个 mp4，一个 document 只对应一个视频")
    return videos[0]


def run(document: str, apply_root: Path = DEFAULT_APPLY_ROOT):
    document_dir = apply_root / document
    if not document_dir.exists():
        raise FileNotFoundError(f"document 目录不存在: {document_dir}")

    video = find_video(document_dir)
    stage1_dir = document_dir / "subproject1"
    stage2_dir = document_dir / "subproject2"
    stage3_dir = document_dir / "subproject3"

    print("=" * 60)
    print(f"Pipeline 启动: {document}")
    print(f"视频: {video}")
    print("=" * 60)
    t0 = time.time()

    # ---------- 阶段1：抽帧裁切 ----------
    import stage1_extract
    r1 = stage1_extract.extract(video, stage1_dir)

    # ---------- 阶段2：英雄检测 + EM 归档 ----------
    import stage2_detect
    r2 = stage2_detect.detect_frames(stage1_dir, stage2_dir)

    # ---------- 阶段3：网格+符号+填表 + UN 归档 ----------
    import stage3_locate_fill
    r3 = stage3_locate_fill.locate_and_fill(r2["csv_path"], stage1_dir, stage3_dir)

    elapsed = time.time() - t0
    print("=" * 60)
    print(f"Pipeline 完成（{elapsed / 60:.1f} 分钟）")
    print(f"  阶段1: 小地图 {r1['normal']} 张（异常跳过 {r1['anomaly']}）→ {r1['output_dir']}")
    print(f"  阶段2: found {r2['found']} / EM {r2['empty']} → {r2['csv_path']}")
    print(f"  阶段3: 填充 {r3['filled_cells']} 格，UN {r3['un_count']} 次 → {r3['table_path']}")
    print("=" * 60)
    return {"stage1": r1, "stage2": r2, "stage3": r3}


def main():
    ap = argparse.ArgumentParser(description="王者视频解析 pipeline 一键调度入口")
    ap.add_argument("--document", required=True, help="document 名，如 document2")
    ap.add_argument("--apply-root", default=str(DEFAULT_APPLY_ROOT), help="产物根目录")
    args = ap.parse_args()
    run(args.document, Path(args.apply_root))


if __name__ == "__main__":
    main()
