"""
预测脚本 v12：使用清理后的 RandomForest 模型
  - 高精度（IoU 0.97）
  - 对不同分辨率/不同设备自适应
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Tuple

import cv2
import joblib
import numpy as np

from train_model import extract_features, imread_safe


OUT_DIR = Path(__file__).resolve().parent.parent  # core/ 上级
MODEL_PATH = OUT_DIR / "roi_model.pkl"


def imwrite_safe(path: Path, img: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise RuntimeError(f"写入失败：{path}")
    path.write_bytes(buf.tobytes())


def predict_roi(model, img: np.ndarray) -> Tuple[int, int, int, int]:
    H, W = img.shape[:2]
    feat = extract_features(img).reshape(1, -1)
    pred = model.predict(feat)[0]
    l = int(round(float(pred[0]) * W))
    t = int(round(float(pred[1]) * H))
    r = int(round(float(pred[2]) * W))
    b = int(round(float(pred[3]) * H))
    l = max(0, l); t = max(0, t); r = min(W - 1, r); b = min(H - 1, b)
    if r <= l: r = l + 1
    if b <= t: b = t + 1
    return l, t, r, b


def process_dir(test_dir: Path) -> None:
    """对指定目录下的所有大图进行预测。"""
    if not test_dir.exists():
        raise FileNotFoundError(f"测试目录不存在: {test_dir}")

    crop_dir = test_dir / "_cropped"
    viz_dir = test_dir / "_viz"
    pred_json = test_dir / "_predictions.json"

    for old in [crop_dir, viz_dir]:
        if old.exists():
            for f in old.glob("*.jpg"):
                f.unlink()
    crop_dir.mkdir(parents=True, exist_ok=True)
    viz_dir.mkdir(parents=True, exist_ok=True)

    images = sorted([
        p for p in test_dir.glob("*.jpg")
        if p.stat().st_size > 100000 and not p.name.startswith("_")
    ])
    if not images:
        print(f"[warn] {test_dir} 为空")
        return

    bundle = joblib.load(MODEL_PATH)
    model = bundle["model"]
    print(f"[加载模型] {MODEL_PATH}")

    print(f"[预测] {test_dir.name}: 共 {len(images)} 张")
    predictions = []
    for i, p in enumerate(images):
        img = imread_safe(p)
        H, W = img.shape[:2]
        l, t, r, b = predict_roi(model, img)
        w, h = r - l, b - t

        cropped = img[t:b + 1, l:r + 1].copy()
        imwrite_safe(crop_dir / p.name, cropped)

        viz = img.copy()
        cv2.rectangle(viz, (l, t), (r, b), (0, 255, 0), 2)
        cv2.putText(viz, f"{w}x{h}",
                    (l, max(t - 8, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        imwrite_safe(viz_dir / p.name, viz)

        predictions.append({
            "file": p.name,
            "image_size": [W, H],
            "roi": [l, t, r, b],
            "roi_size": [w, h],
        })

        if (i + 1) % 30 == 0 or i < 3:
            print(f"  [{i+1}/{len(images)}] {p.name}: {W}x{H}  "
                  f"ROI=({l},{t},{r},{b})  size={w}x{h}")

    pred_json.write_text(json.dumps(predictions, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[完成] {test_dir.name}")
    print(f"  小地图裁剪：{crop_dir}")
    print(f"  可视化标注：{viz_dir}")
    print(f"  预测结果：  {pred_json}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=str, required=True, help="测试目录")
    args = parser.parse_args()
    test_dir = Path(args.dir)
    process_dir(test_dir)


if __name__ == "__main__":
    main()