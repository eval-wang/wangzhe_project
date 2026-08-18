"""
训练脚本 v6：
  增强特征 + RandomForest（比 GBR 更鲁棒，不易过拟合）
  
特征改进：
  - 图像左上区域的网格化特征（将 ROI 分成 8x8 网格，每格取均值）
  - 灰度直方图
  - HSV 各通道统计
  - 梯度分布
  - 全图宽高比
  
目标：预测归一化坐标 (l/W, t/H, r/W, b/H)
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import KFold
from sklearn.multioutput import MultiOutputRegressor
from sklearn.metrics import mean_absolute_error


OUT_DIR = Path(__file__).resolve().parent.parent  # core/ 上级
LABELS_PATH = OUT_DIR / "labels.json"
MODEL_PATH = OUT_DIR / "roi_model.pkl"

DATA_DIRS = [
    Path(r"D:/wangzhe_project/screenshot_collection/train_collection/train1/full"),
    Path(r"D:/wangzhe_project/screenshot_collection/train_collection/train3/full"),
    Path(r"D:/wangzhe_project/screenshot_collection/train_collection/train5"),
    Path(r"D:/wangzhe_project/screenshot_collection/train_collection/preview_screens/full"),
]


def find_image(filename: str) -> Path | None:
    for d in DATA_DIRS:
        p = d / filename
        if p.exists():
            return p
    return None


def imread_safe(path: Path) -> np.ndarray:
    data = Path(path).read_bytes()
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"无法读取：{path}")
    return img


def extract_features(img_bgr: np.ndarray) -> np.ndarray:
    """提取更丰富的特征向量。"""
    H, W = img_bgr.shape[:2]

    # --- 1. 左上区域网格化特征 ---
    roi_w = max(1, int(W * 0.40))
    roi_h = max(1, int(H * 0.55))
    roi = img_bgr[:roi_h, :roi_w]
    gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0

    # 缩小到 12x16 网格
    grid_h, grid_w = 12, 16
    small = cv2.resize(gray_roi, (grid_w, grid_h), interpolation=cv2.INTER_AREA)
    grid_features = small.flatten()  # 192 维

    # --- 2. 灰度直方图 ---
    hist = cv2.calcHist([gray_roi], [0], None, [24], [0, 1]).flatten()
    hist = hist / max(hist.sum(), 1e-6)

    # --- 3. HSV 各通道统计 ---
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV).astype(np.float32)
    h_mean, s_mean, v_mean = hsv.mean(axis=(0, 1)) / np.array([180, 255, 255])
    h_std, s_std, v_std = hsv.std(axis=(0, 1)) / np.array([180, 255, 255])

    # --- 4. 梯度统计 ---
    sobel_x = np.abs(cv2.Sobel(gray_roi, cv2.CV_64F, 1, 0, ksize=3))
    sobel_y = np.abs(cv2.Sobel(gray_roi, cv2.CV_64F, 0, 1, ksize=3))
    grad_mean_x = float(sobel_x.mean()) / 50.0
    grad_mean_y = float(sobel_y.mean()) / 50.0

    # --- 5. 蓝灰色像素比例 ---
    hsv_full = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    H_ch, S_ch, V_ch = cv2.split(hsv_full)
    bluegray = ((H_ch > 80) & (H_ch < 150) & (S_ch > 15) & (S_ch < 150) & (V_ch > 25) & (V_ch < 160))
    bluegray_ratio = bluegray.mean()

    # --- 6. 绿色像素比例 ---
    green = ((H_ch > 35) & (H_ch < 90) & (S_ch > 40) & (V_ch > 25))
    green_ratio = green.mean()

    # --- 7. 非黑像素密度 ---
    nonblack = (roi.max(axis=2) > 12).mean()

    # --- 8. 全图参数 ---
    aspect = W / max(1, H)
    h_norm = H / 1000.0

    # --- 9. 小地图可能位置的先验特征 ---
    # 计算左侧和顶部边缘的梯度（找小地图边界）
    left_edge_grad = sobel_x[:, :min(roi_w, 30)].mean() / 50.0
    top_edge_grad = sobel_y[:min(roi_h, 30), :].mean() / 50.0
    right_area = int(roi_w * 0.8)
    right_edge_grad = sobel_x[:, right_area:].mean() / 50.0
    bot_area = int(roi_h * 0.8)
    bot_edge_grad = sobel_y[bot_area:, :].mean() / 50.0

    return np.concatenate([
        grid_features,
        hist,
        [h_mean, s_mean, v_mean, h_std, s_std, v_std],
        [grad_mean_x, grad_mean_y, bluegray_ratio, green_ratio, nonblack],
        [aspect, h_norm],
        [left_edge_grad, top_edge_grad, right_edge_grad, bot_edge_grad],
    ]).astype(np.float32)


def load_dataset() -> tuple[np.ndarray, np.ndarray, list[dict]]:
    labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    X_list, y_list, meta = [], [], []
    skipped = 0
    for item in labels:
        path = find_image(item["file"])
        if path is None:
            skipped += 1
            continue
        img = imread_safe(path)
        W, H = item["image_size"]
        l, t, r, b = item["roi"]
        feat = extract_features(img)
        target = np.array([l / W, t / H, r / W, b / H], dtype=np.float32)
        X_list.append(feat)
        y_list.append(target)
        meta.append({"file": item["file"], "size": [W, H], "roi": [l, t, r, b]})
    if skipped:
        print(f"[warn] 跳过 {skipped} 张")
    X = np.stack(X_list)
    y = np.stack(y_list)
    return X, y, meta


def iou(box_a, box_b) -> float:
    al, at, ar, ab = box_a
    bl, bt, br, bb = box_b
    inter_w = max(0.0, min(ar, br) - max(al, bl))
    inter_h = max(0.0, min(ab, bb) - max(at, bt))
    inter = inter_w * inter_h
    area_a = max(0.0, (ar - al)) * max(0.0, (ab - at))
    area_b = max(0.0, (br - bl)) * max(0.0, (bb - bt))
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def main() -> None:
    X, y, meta = load_dataset()
    print(f"[训练] 样本数：{len(X)}，特征维度：{X.shape[1]}")

    if len(X) < 5:
        print("[error] 样本太少")
        return

    # K 折交叉验证
    n_splits = min(5, len(X))
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)
    cv_mae, cv_ious = [], []
    for fold, (tr, va) in enumerate(kf.split(X), 1):
        model = MultiOutputRegressor(
            RandomForestRegressor(n_estimators=200, max_depth=12, random_state=42, n_jobs=-1)
        )
        model.fit(X[tr], y[tr])
        pred = model.predict(X[va])
        cv_mae.append(mean_absolute_error(y[va], pred))
        ious = []
        for i, idx in enumerate(va):
            W, H = meta[idx]["size"]
            l, t, r, b = meta[idx]["roi"]
            pl = int(round(pred[i][0] * W)); pt = int(round(pred[i][1] * H))
            pr = int(round(pred[i][2] * W)); pb = int(round(pred[i][3] * H))
            ious.append(iou([l, t, r, b], [pl, pt, pr, pb]))
        cv_ious.append(float(np.mean(ious)))
        print(f"  fold {fold}: MAE={cv_mae[-1]:.4f}  IoU={cv_ious[-1]:.4f}")

    print(f"\n[CV] 平均 MAE = {np.mean(cv_mae):.4f}")
    print(f"[CV] 平均 IoU = {np.mean(cv_ious):.4f}")

    # 全量训练
    final_model = MultiOutputRegressor(
        RandomForestRegressor(n_estimators=300, max_depth=14, random_state=42, n_jobs=-1)
    )
    final_model.fit(X, y)
    joblib.dump({"model": final_model}, MODEL_PATH)
    print(f"\n[保存] {MODEL_PATH}")


if __name__ == "__main__":
    main()