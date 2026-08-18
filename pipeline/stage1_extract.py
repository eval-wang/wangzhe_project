# -*- coding: utf-8 -*-
"""
Pipeline 阶段1 —— 小地图抽帧裁切（子项目1 的规范化副本）
==========================================================
依据 `产物目录命名规范` 重写输出逻辑：产物输出到 <APPLY_ROOT>\\<document>\\subproject1\\，
阶段文件夹自动创建。**不改动子项目1 原始脚本**，仅复用其模型与特征提取。

流程（与子项目1 extract_minimaps.py 一致）：
  视频 → 按间隔抽帧 → RF 模型预测 ROI → 裁切 → 统一缩放 186×186 → extraction_log.csv

参数差异（pipeline 约定）：
  start=40s（时间基准从 40s 开始，前 40 秒不抽）、interval=3s、end=视频结束。

依赖（只读引用子项目1）：
  - 模型：王者视频解析\\子项目1_小地图识别\\roi_model.pkl
  - 特征提取：王者视频解析\\子项目1_小地图识别\\core\\train_model.py
"""

import csv
import sys
from pathlib import Path

import cv2
import joblib

# ---------------- 子项目1 只读引用 ----------------
SUBPROJECT1_DIR = Path(r"D:\wangzhe_project\王者视频解析\子项目1_小地图识别")
MODEL_PATH = SUBPROJECT1_DIR / "roi_model.pkl"
sys.path.insert(0, str(SUBPROJECT1_DIR / "core"))

# ---------------- 默认参数（pipeline 约定） ----------------
DEFAULT_START_S = 40.0     # 时间基准从 40s 开始
DEFAULT_INTERVAL_S = 3.0   # 每 3 秒抽帧
DEFAULT_SIZE = 186         # 输出正方形尺寸
DEFAULT_MAX_DEVIATION = 0.03  # 尺寸偏差超过 3% 视为异常跳过


def load_model():
    """加载子项目1 的 RF 模型与特征提取函数。"""
    from train_model import extract_features  # 子项目1 core 模块（只读）
    bundle = joblib.load(str(MODEL_PATH))
    return bundle["model"], extract_features


def predict_roi(model, extract_features, frame):
    """预测小地图 ROI（归一化坐标 → 像素坐标）。"""
    H, W = frame.shape[:2]
    feat = extract_features(frame).reshape(1, -1)
    pred = model.predict(feat)[0]
    l = max(0, int(round(float(pred[0]) * W)))
    t = max(0, int(round(float(pred[1]) * H)))
    r = min(W - 1, int(round(float(pred[2]) * W)))
    b = min(H - 1, int(round(float(pred[3]) * H)))
    if r <= l:
        r = l + 1
    if b <= t:
        b = t + 1
    return l, t, r, b


def is_anomaly(w, h, ref_w, ref_h, max_deviation):
    """裁切尺寸与参考帧偏差超过阈值视为异常。"""
    if ref_w <= 0 or ref_h <= 0:
        return False
    return (abs(w - ref_w) / ref_w > max_deviation
            or abs(h - ref_h) / ref_h > max_deviation)


def format_time(seconds):
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def extract(video_path, output_dir,
            start_s=DEFAULT_START_S, end_s=None, interval_s=DEFAULT_INTERVAL_S,
            target_size=DEFAULT_SIZE, max_deviation=DEFAULT_MAX_DEVIATION):
    """
    从视频中按间隔抽帧并裁切小地图。

    Args:
        video_path: 视频文件路径
        output_dir: 输出目录（<APPLY_ROOT>\\<document>\\subproject1），自动创建
        start_s: 起始时间（秒），默认 40
        end_s: 结束时间（秒），None = 视频结束
        interval_s: 抽帧间隔（秒），默认 3
        target_size: 输出小地图边长
        max_deviation: 尺寸异常阈值

    Returns:
        dict: {"output_dir", "total", "normal", "anomaly", "duration_s"}
    """
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)  # 阶段文件夹自动创建

    if not video_path.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    model, extract_features_fn = load_model()

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    if end_s is None or end_s > duration:
        end_s = duration

    print(f"[阶段1] 视频: {video_path.name}（{fps:.1f}fps，时长 {format_time(duration)}）")
    print(f"[阶段1] 抽帧: {format_time(start_s)} ~ {format_time(end_s)}，间隔 {interval_s}s，"
          f"预计 {int((end_s - start_s) / interval_s) + 1} 帧")
    print(f"[阶段1] 输出: {output_dir}")

    start_frame = int(start_s * fps)
    end_frame = int(end_s * fps)
    frame_interval = max(1, int(round(fps * interval_s)))

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frame_index = start_frame

    records = []
    count = 0
    anomaly_count = 0
    ref_w, ref_h = 0, 0

    while frame_index <= end_frame:
        ret, frame = cap.read()
        if not ret:
            break

        if (frame_index - start_frame) % frame_interval == 0:
            timestamp = frame_index / fps
            l, t, r, b = predict_roi(model, extract_features_fn, frame)
            w, h = r - l, b - t

            if count > 0 and is_anomaly(w, h, ref_w, ref_h, max_deviation):
                anomaly_count += 1
                records.append([count, format_time(timestamp), round(timestamp, 1),
                                "", f"{w}×{h}", "跳过(尺寸异常)"])
            else:
                minimap = cv2.resize(frame[t:b + 1, l:r + 1].copy(),
                                     (target_size, target_size),
                                     interpolation=cv2.INTER_CUBIC)
                filename = f"frame_{count:04d}_{timestamp:.1f}s.jpg"
                cv2.imwrite(str(output_dir / filename), minimap,
                            [cv2.IMWRITE_JPEG_QUALITY, 95])
                if count == 0:
                    ref_w, ref_h = w, h
                records.append([count, format_time(timestamp), round(timestamp, 1),
                                filename, f"{w}×{h}", "正常"])

            count += 1
            if count % 50 == 0:
                print(f"[阶段1] 已处理 {count} 帧（{format_time(timestamp)}）...")

        frame_index += 1

    cap.release()

    csv_path = output_dir / "extraction_log.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["序号", "时间(分:秒)", "时间戳(秒)", "文件名", "原始尺寸", "状态"])
        writer.writerows(records)

    normal = sum(1 for r in records if r[5] == "正常")
    print(f"[阶段1] 完成: 正常 {normal} 张，异常跳过 {anomaly_count} 张，日志 {csv_path.name}")
    return {"output_dir": output_dir, "total": count, "normal": normal,
            "anomaly": anomaly_count, "duration_s": duration}
