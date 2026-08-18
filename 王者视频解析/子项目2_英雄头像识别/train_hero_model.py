"""
英雄头像识别 - 模型训练 v1
==========================
基于颜色特征的轻量分类器：
  1. 加载标注数据，从框内提取正样本（绿框英雄头像区域）
  2. 从小地图其他位置随机采样负样本（背景/其他头像）
  3. 用 HSV 颜色直方图 + HOG 简单梯度特征描述样本
  4. 训练 SVM / RandomForest 分类器
  5. 保存模型供检测阶段使用

数据目录（支持多个，逐目录读取各自的 hero_labels.json）：
  D:/wangzhe_project/selected_screenshot_collection/train1
  D:/wangzhe_project/screenshot_collection/train_collection/train3
  D:/wangzhe_project/screenshot_collection/train_collection/train4
"""
import json
import os
import pickle
import random
from pathlib import Path

import cv2
import numpy as np

# ============== 配置 ==============
DATA_DIRS = [
    Path(r"D:\wangzhe_project\selected_screenshot_collection\train1"),
    Path(r"D:\wangzhe_project\screenshot_collection\train_collection\train3"),
    Path(r"D:\wangzhe_project\screenshot_collection\train_collection\train4"),
    Path(r"D:\wangzhe_project\screenshot_collection\train_collection\train5"),
]
MODEL_OUTPUT = Path(r"D:\wangzhe_project\王者视频解析\子项目2_英雄头像识别\release\hero_model.pkl")

# 正样本框统一缩放尺寸
PATCH_SIZE = 24          # 模型训练时统一为 24x24
HOG_WIN_SIZE = (24, 24)
HOG_BLOCK = (8, 8)
HOG_CELL = (4, 4)
HOG_BIN = 9

# 负样本采样
NEG_PER_POS = 4          # 每个正样本配 4 个负样本
MIN_NEG_DIST = 30        # 负样本距正样本中心至少 30px

RANDOM_SEED = 42


def imread_safe(path):
    data = open(path, "rb").read()
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def extract_color_hist(patch_bgr, h_bins=18, s_bins=8):
    """提取 HSV 颜色直方图特征。"""
    hsv = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist(
        [hsv], [0, 1], None, [h_bins, s_bins], [0, 180, 0, 256]
    )
    hist = hist.flatten()
    hist = hist / (hist.sum() + 1e-6)
    return hist


_hog = cv2.HOGDescriptor(
    HOG_WIN_SIZE, (8, 8), HOG_BLOCK, HOG_CELL, HOG_BIN
)


def extract_hog(patch_bgr):
    """提取 HOG 梯度特征。"""
    gray = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2GRAY)
    return _hog.compute(gray).flatten()


def extract_features(patch_bgr):
    """拼接颜色直方图 + HOG 特征。"""
    color = extract_color_hist(patch_bgr)
    hog = extract_hog(patch_bgr)
    return np.concatenate([color, hog])


# ============== 加载标注 ==============
def load_labels():
    """加载所有数据目录的标注，每条记录附加 "dir" 字段指向所属目录
    （各目录帧文件名会重复，必须按目录区分）。"""
    data = []
    for d in DATA_DIRS:
        lf = d / "hero_labels.json"
        if not lf.exists():
            print(f"  警告: 无标注文件，跳过 {d}")
            continue
        for item in json.loads(lf.read_text(encoding="utf-8")):
            item["dir"] = d
            data.append(item)
    return data


def extract_positives(data, collect_patches=False):
    """从标注框中提取正样本特征（含数据增强）。
    collect_patches=True 时额外返回原始 patch 列表（未增强），
    用作检测阶段的 NCC 参考模板。"""
    pos_feats = []
    pos_meta = []  # 记录 (file, cx, cy, side) 供可视化
    patches = []

    for item in data:
        fn = item["file"]
        path = item["dir"] / fn
        img = imread_safe(path)
        if img is None:
            continue
        for box in item.get("boxes", []):
            if box[4] != "green":
                continue
            l, t, r, b, _ = box
            cx = (l + r) // 2
            cy = (t + b) // 2
            side = max(r - l, b - t)
            # 抠出正方形区域
            half = side // 2
            x1, y1 = max(0, cx - half), max(0, cy - half)
            x2, y2 = min(img.shape[1], cx + half), min(img.shape[0], cy + half)
            patch = img[y1:y2, x1:x2]
            if patch.size == 0:
                continue
            patch = cv2.resize(patch, (PATCH_SIZE, PATCH_SIZE))
            pos_feats.append(extract_features(patch))
            pos_meta.append((fn, cx, cy, side))
            patches.append(patch)
            # 数据增强：旋转 / 亮度 / 翻转 / 平移，提升分类器鲁棒性
            for aug in augment_patch(patch):
                pos_feats.append(extract_features(aug))

    if collect_patches:
        return np.array(pos_feats), pos_meta, patches
    return np.array(pos_feats), pos_meta


def augment_patch(patch):
    """对单个正样本 patch 做轻量增强，返回增强后的 patch 列表。"""
    out = []
    c = PATCH_SIZE // 2
    # 旋转
    for angle in (-8, 8):
        M = cv2.getRotationMatrix2D((c, c), angle, 1.0)
        out.append(cv2.warpAffine(patch, M, (PATCH_SIZE, PATCH_SIZE),
                                  borderMode=cv2.BORDER_REFLECT))
    # 亮度
    for alpha in (0.85, 1.15):
        out.append(np.clip(patch.astype(np.float32) * alpha, 0, 255).astype(np.uint8))
    # 水平翻转
    out.append(cv2.flip(patch, 1))
    # 平移 ±2px（模拟圆心定位抖动）
    for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        out.append(cv2.warpAffine(patch, M, (PATCH_SIZE, PATCH_SIZE),
                                  borderMode=cv2.BORDER_REFLECT))
    return out


def extract_negatives(data, n_per_pos):
    """从图片中随机采样负样本（远离正样本位置）。"""
    neg_feats = []

    for item in data:
        fn = item["file"]
        path = item["dir"] / fn
        img = imread_safe(path)
        if img is None:
            continue

        # 收集本图的正样本中心
        pos_centers = []
        for box in item.get("boxes", []):
            if box[4] != "green":
                continue
            l, t, r, b, _ = box
            pos_centers.append(((l + r) // 2, (t + b) // 2))

        # 每个正样本配 n 个负样本
        for _ in range(n_per_pos):
            for _ in range(20):  # 最多尝试 20 次找到合规位置
                # 随机框中心与大小
                H, W = img.shape[:2]
                cy = random.randint(PATCH_SIZE // 2, H - PATCH_SIZE // 2 - 1)
                cx = random.randint(PATCH_SIZE // 2, W - PATCH_SIZE // 2 - 1)
                # 远离正样本
                if all(
                    (cx - px) ** 2 + (cy - py) ** 2 > MIN_NEG_DIST ** 2
                    for px, py in pos_centers
                ) or not pos_centers:
                    half = PATCH_SIZE // 2
                    patch = img[cy - half:cy + half, cx - half:cx + half]
                    if patch.shape[:2] != (PATCH_SIZE, PATCH_SIZE):
                        continue
                    feat = extract_features(patch)
                    neg_feats.append(feat)
                    break

    return np.array(neg_feats)


def mine_hard_negatives(data, max_per_img=20):
    """难负样本挖掘：跑检测候选生成器，把"长得像绿环但不是目标英雄"
    的候选（距真值 > HARD_NEG_DIST）作为负样本。这些正是检测阶段
    最容易被误选的干扰（主宰坑、基地 UI、其他英雄头像、复活特效等）。
    无标注的帧（英雄死亡/消失）所有候选都视为负样本。
    """
    from hero_detect import find_candidates  # 延迟导入避免循环依赖

    HARD_NEG_DIST = 14  # 距真值中心超过此值才算负样本（框边长~25，取一半以上）
    neg_feats = []

    # 无标注帧也要参与挖掘（如复活倒计时特效是典型难负样本）
    # 按目录分组处理，避免不同目录的同名帧互相干扰
    entries = list(data)
    for d in DATA_DIRS:
        labeled_files = {item["file"] for item in data if item["dir"] == d}
        for p in sorted(d.glob("frame_*.jpg")):
            if p.name not in labeled_files:
                entries.append({"file": p.name, "boxes": [], "dir": d})

    for item in entries:
        fn = item["file"]
        path = item["dir"] / fn
        img = imread_safe(path)
        if img is None:
            continue

        pos_centers = [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
                       for b in item.get("boxes", []) if b[4] == "green"]

        candidates = find_candidates(img)
        H, W = img.shape[:2]
        count = 0
        for c in candidates:
            if count >= max_per_img:
                break
            cx, cy = c["center"]
            if any((cx - px) ** 2 + (cy - py) ** 2 <= HARD_NEG_DIST ** 2
                   for px, py in pos_centers):
                continue  # 是正样本本身
            half = c["radius"] + 1
            x1, y1 = max(0, cx - half), max(0, cy - half)
            x2, y2 = min(W, cx + half), min(H, cy + half)
            patch = img[y1:y2, x1:x2]
            if patch.size == 0:
                continue
            patch = cv2.resize(patch, (PATCH_SIZE, PATCH_SIZE))
            neg_feats.append(extract_features(patch))
            count += 1

    if not neg_feats:
        return np.empty((0, 0))
    return np.array(neg_feats)


def main():
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)

    print("=" * 60)
    print("英雄头像识别 - 模型训练")
    print("=" * 60)

    print("\n[1/5] 加载标注...")
    data = load_labels()
    print(f"  标注条目: {len(data)}")

    print("\n[2/5] 提取正样本...")
    pos_feats, pos_meta, pos_patches = extract_positives(data, collect_patches=True)
    print(f"  正样本: {len(pos_feats)}（含增强），原始 patch {len(pos_patches)} 个")

    print("\n[3/5] 提取负样本...")
    neg_feats = extract_negatives(data, n_per_pos=NEG_PER_POS)
    print(f"  随机负样本: {len(neg_feats)}")
    hard_feats = mine_hard_negatives(data)
    print(f"  难负样本: {len(hard_feats)}")
    if len(hard_feats):
        neg_feats = np.vstack([neg_feats, hard_feats])
    print(f"  负样本合计: {len(neg_feats)}")

    print("\n[4/5] 准备训练数据...")
    X = np.vstack([pos_feats, neg_feats])
    y = np.concatenate([
        np.ones(len(pos_feats), dtype=np.int32),
        np.zeros(len(neg_feats), dtype=np.int32)
    ])
    print(f"  训练集: X={X.shape}, y={y.shape}, 正/负={int(y.sum())}/{int(len(y)-y.sum())}")

    # 打乱
    idx = np.arange(len(y))
    np.random.shuffle(idx)
    X, y = X[idx], y[idx]

    print("\n[5/5] 训练分类器 (SVM)...")
    from sklearn.svm import SVC
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_score

    # SVM
    svm = SVC(kernel="rbf", C=10, gamma="scale", probability=True, random_state=RANDOM_SEED)
    svm_scores = cross_val_score(svm, X, y, cv=5, scoring="f1")
    print(f"  SVM 5-fold F1: {svm_scores.mean():.3f} ± {svm_scores.std():.3f}")

    svm.fit(X, y)

    # RandomForest（对比）
    rf = RandomForestClassifier(n_estimators=200, max_depth=12, random_state=RANDOM_SEED, n_jobs=-1)
    rf_scores = cross_val_score(rf, X, y, cv=5, scoring="f1")
    print(f"  RF  5-fold F1: {rf_scores.mean():.3f} ± {rf_scores.std():.3f}")

    rf.fit(X, y)

    # 选更优的
    if rf_scores.mean() > svm_scores.mean():
        best_name, best_model = "RandomForest", rf
    else:
        best_name, best_model = "SVM", svm
    print(f"\n  选用模型: {best_name}")

    # 训练集性能
    train_pred = best_model.predict(X)
    train_acc = (train_pred == y).mean()
    print(f"  训练集准确率: {train_acc:.3f}")

    # 保存（refs = 正样本原始 patch，检测阶段用作 NCC 参考模板）
    MODEL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_OUTPUT, "wb") as f:
        pickle.dump({
            "model": best_model,
            "model_name": best_name,
            "patch_size": PATCH_SIZE,
            "refs": np.array(pos_patches),  # (N, 24, 24, 3) uint8
            "pos_count": int(len(pos_feats)),
            "neg_count": int(len(neg_feats)),
            "svm_f1": float(svm_scores.mean()),
            "rf_f1": float(rf_scores.mean()),
        }, f)

    print(f"\n模型已保存到: {MODEL_OUTPUT}")
    print("=" * 60)


if __name__ == "__main__":
    main()