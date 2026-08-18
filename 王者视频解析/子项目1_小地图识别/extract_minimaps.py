"""
小地图自动提取工具 v2.0
======================
从视频中按时间范围截取帧 → 用模型裁切小地图 → 统一缩放到 186×186

功能：
  - 指定时间范围和间隔截取视频帧
  - 用训练好的 RF 模型预测小地图位置并裁切
  - 自动检测异常帧（尺寸偏差过大时跳过）
  - 统一缩放到固定尺寸
  - 生成记录文档（CSV），标注时间、文件名和状态

用法：
  python extract_minimaps.py --video <视频路径> --output <输出目录>
                             --start 300 --end 400 --interval 10
                             --size 186 --max-deviation 0.15
"""

import argparse
import csv
import os
from pathlib import Path

import cv2
import joblib
import numpy as np

# ==================== 配置 ====================
MODEL_PATH = Path(__file__).resolve().parent / "roi_model.pkl"
DEFAULT_VIDEO = r"D:\wangzhe_project\相关素材\视频素材\训练营.mp4"
DEFAULT_OUTPUT = r"D:\wangzhe_project\selected_screenshot_collection\test"
DEFAULT_SIZE = 186
DEFAULT_MAX_DEVIATION = 0.03  # 尺寸偏差超过 3% 视为异常


# ==================== 核心函数 ====================

def load_model():
    """加载训练好的模型。"""
    from core.train_model import extract_features
    bundle = joblib.load(str(MODEL_PATH))
    return bundle["model"], extract_features


def predict_roi(model, extract_features, frame):
    """预测小地图 ROI。"""
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
    """判断裁切尺寸是否异常。"""
    if ref_w <= 0 or ref_h <= 0:
        return False
    dw = abs(w - ref_w) / ref_w
    dh = abs(h - ref_h) / ref_h
    return dw > max_deviation or dh > max_deviation


def format_time(seconds):
    """将秒数转换为 分:秒 格式。"""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


# ==================== 主流程 ====================

def extract_minimaps(video_path, output_dir,
                     start_s=300, end_s=400, interval_s=10,
                     target_size=DEFAULT_SIZE, max_deviation=DEFAULT_MAX_DEVIATION):
    """
    从视频中提取并裁切小地图。

    Args:
        video_path: 视频文件路径
        output_dir: 输出目录
        start_s: 起始时间（秒）
        end_s: 结束时间（秒）
        interval_s: 截取间隔（秒）
        target_size: 输出小地图的尺寸（正方形）
        max_deviation: 最大允许尺寸偏差比例（超过则跳过）
    """
    video_path = os.path.abspath(video_path)
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(video_path):
        print(f"错误：视频文件不存在 - {video_path}")
        return

    # 加载模型
    model, extract_features_fn = load_model()

    # 打开视频
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"错误：无法打开视频 - {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps

    print(f"视频: {os.path.basename(video_path)}")
    print(f"参数: {fps:.1f}fps, 时长={format_time(duration)}, 总帧数={total_frames}")
    print(f"截取: {format_time(start_s)} ~ {format_time(end_s)}, 间隔={interval_s}s")
    print(f"输出: {output_dir}, 目标尺寸={target_size}×{target_size}")
    print("-" * 60)

    # 计算帧范围
    start_frame = int(start_s * fps)
    end_frame = int(end_s * fps)
    frame_interval = int(fps * interval_s)

    # 跳到起始帧
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frame_index = start_frame

    # 记录
    records = []
    count = 0
    anomaly_count = 0
    ref_w, ref_h = 0, 0  # 参考尺寸（用第一帧的有效裁切）

    while frame_index <= end_frame:
        ret, frame = cap.read()
        if not ret:
            break

        if (frame_index - start_frame) % frame_interval == 0:
            timestamp = frame_index / fps
            time_str = format_time(timestamp)

            # 预测 ROI
            l, t, r, b = predict_roi(model, extract_features_fn, frame)
            w, h = r - l, b - t

            # 异常检测
            if count > 0 and is_anomaly(w, h, ref_w, ref_h, max_deviation):
                anomaly_count += 1
                records.append({
                    "index": count,
                    "time": time_str,
                    "timestamp_s": round(timestamp, 1),
                    "filename": "",
                    "original_size": f"{w}×{h}",
                    "status": "跳过(尺寸异常)",
                })
                print(f"  [{count}] {time_str}: 尺寸异常 {w}×{h} (参考={ref_w}×{ref_h}) → 跳过")
            else:
                # 裁切
                minimap = frame[t:b + 1, l:r + 1].copy()
                orig_w, orig_h = w, h

                # 统一缩放
                minimap_resized = cv2.resize(minimap, (target_size, target_size),
                                             interpolation=cv2.INTER_CUBIC)

                filename = f"frame_{count:04d}_{timestamp:.1f}s.jpg"
                output_path = os.path.join(output_dir, filename)
                cv2.imwrite(output_path, minimap_resized,
                            [cv2.IMWRITE_JPEG_QUALITY, 95])

                # 更新参考尺寸
                if count == 0:
                    ref_w, ref_h = orig_w, orig_h

                records.append({
                    "index": count,
                    "time": time_str,
                    "timestamp_s": round(timestamp, 1),
                    "filename": filename,
                    "original_size": f"{orig_w}×{orig_h}",
                    "status": "正常",
                })
                print(f"  [{count}] {time_str}: {orig_w}×{orig_h} → {target_size}×{target_size} → {filename}")

            count += 1

        frame_index += 1

    cap.release()

    # 生成记录文档
    csv_path = os.path.join(output_dir, "extraction_log.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["序号", "时间(分:秒)", "时间戳(秒)", "文件名", "原始尺寸", "状态"])
        for r in records:
            writer.writerow([
                r["index"],
                r["time"],
                r["timestamp_s"],
                r["filename"],
                r["original_size"],
                r["status"],
            ])

    # 打印汇总
    normal = sum(1 for r in records if r["status"] == "正常")
    print(f"\n{'=' * 60}")
    print(f"处理完成！")
    print(f"  正常输出: {normal} 张")
    print(f"  异常跳过: {anomaly_count} 张")
    print(f"  记录文档: {csv_path}")
    print(f"  输出目录: {output_dir}")

    # 验证
    actual_files = [f for f in os.listdir(output_dir) if f.endswith(".jpg")]
    print(f"  实际文件: {len(actual_files)} 个 jpg")


# ==================== 命令行入口 ====================

def main():
    parser = argparse.ArgumentParser(description="小地图自动提取工具 v2.0")
    parser.add_argument("--video", type=str, default=DEFAULT_VIDEO, help="视频文件路径")
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT, help="输出目录")
    parser.add_argument("--start", type=float, default=300, help="起始时间（秒）")
    parser.add_argument("--end", type=float, default=400, help="结束时间（秒）")
    parser.add_argument("--interval", type=float, default=10, help="截取间隔（秒）")
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE, help="输出尺寸（正方形）")
    parser.add_argument("--max-deviation", type=float, default=DEFAULT_MAX_DEVIATION,
                        help="最大尺寸偏差比例（超过则跳过）")
    args = parser.parse_args()

    extract_minimaps(
        video_path=args.video,
        output_dir=args.output,
        start_s=args.start,
        end_s=args.end,
        interval_s=args.interval,
        target_size=args.size,
        max_deviation=args.max_deviation,
    )


if __name__ == "__main__":
    main()
