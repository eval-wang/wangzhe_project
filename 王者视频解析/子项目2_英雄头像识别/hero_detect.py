"""
英雄头像检测 - 颜色优先策略 v2（环形模板匹配）
==============================================
流程：
  1. HSV 颜色过滤：提取绿环像素（实测分布 H 61-85 / S 83-150 / V 104-194）
  2. 形态学闭运算：连接 1-3px 断续的绿环细线
  3. 环形模板匹配：用半径 10-14 的圆环核对绿色掩膜做卷积，
     响应 = 环上绿色覆盖率，可容忍部分遮挡（团战时头像互相覆盖）
  4. NMS 取局部峰值 → 候选圆心
  5. （可选）分类器二次确认：用 hero_model.pkl 区分目标英雄

用法：
  python hero_detect.py <图片路径>               # 单张检测
  python hero_detect.py --validate               # 在所有数据目录上对照标注全量验证
  python hero_detect.py --validate --no-clf      # 纯颜色+环形模板，不用分类器
"""
import argparse
import json
import pickle
import sys
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
MODEL_FILE = Path(r"D:\wangzhe_project\王者视频解析\子项目2_英雄头像识别\release\hero_model.pkl")
DEBUG_DIR = Path(r"D:\wangzhe_project\王者视频解析\子项目2_英雄头像识别\debug_output")

# HSV 双掩膜配置：(lower, upper, 覆盖率下限)
#   green：绿环实测 H 57-94 / S 60-155 / V 61-227，抗锯齿边缘偏低
#   cyan ：泉水治疗光会把绿环染成青色（H 91-106），单独放宽但提高覆盖率门槛
COLOR_MASKS = [
    ("green", np.array([45, 50, 55], dtype=np.uint8),
     np.array([95, 255, 255], dtype=np.uint8), 0.22),
    ("cyan", np.array([95, 40, 55], dtype=np.uint8),
     np.array([112, 255, 255], dtype=np.uint8), 0.35),
]

# 环形模板参数（标注框边长 21-27 → 环半径约 10-14）
RING_RADII = [10, 11, 12, 13, 14]
RING_THICK = 1.2        # 环核厚度容差(px)
NMS_RADIUS = 6          # 峰值去重半径（重叠英雄圆心可近至 8px，不宜过大）
MIN_RING_VALID = 0.60   # 环在画面内的有效占比下限（抑制边缘虚高峰值）
MAX_INTERIOR = 0.30     # 环内部同色占比上限（排除草丛/河道等实心块）
INTERIOR_SHRINK = 4     # 内部区域 = 半径减此值的圆盘

# 验证判定：圆心误差 <= 此值视为命中
HIT_DIST = 5


def imread_safe(path):
    data = open(path, "rb").read()
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def color_mask(img_bgr, lower, upper):
    """HSV 颜色过滤 + 闭运算连接断续细线。"""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower, upper)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def _ring_kernel(radius, thick=RING_THICK):
    """生成圆环核：距圆心 radius±thick 的像素为 1。"""
    R = int(np.ceil(radius + thick)) + 1
    yy, xx = np.mgrid[-R:R + 1, -R:R + 1]
    dist = np.sqrt(xx ** 2 + yy ** 2)
    k = (np.abs(dist - radius) <= thick).astype(np.float32)
    return k


def ring_response(mask):
    """对绿色掩膜做多半径环形模板匹配。
    返回 (覆盖率图, 最佳半径图, 有效占比图)：
      覆盖率 = 环上绿色像素 / 环在画面内的像素
      有效占比 = 环在画面内的像素 / 完整环像素（抑制边缘虚高）
    """
    m = mask.astype(np.float32) / 255.0
    ones = np.ones_like(m)
    best_resp = np.zeros_like(m)
    best_r = np.zeros_like(m)
    best_valid = np.zeros_like(m)
    for r in RING_RADII:
        k = _ring_kernel(r)
        k_sum = k.sum()
        num = cv2.filter2D(m, -1, k, borderType=cv2.BORDER_CONSTANT)
        den = cv2.filter2D(ones, -1, k, borderType=cv2.BORDER_CONSTANT)
        resp = np.where(den > 0, num / np.maximum(den, 1e-6), 0).astype(np.float32)
        valid = (den / k_sum).astype(np.float32)
        upd = resp > best_resp
        best_resp[upd] = resp[upd]
        best_r[upd] = r
        best_valid[upd] = valid[upd]
    return best_resp, best_r, best_valid


def interior_green_ratio(mask, center, radius):
    """环内部（半径-INTERIOR_SHRINK 的圆盘）的绿色占比。"""
    cx, cy = center
    r = max(radius - INTERIOR_SHRINK, 2)
    yy, xx = np.mgrid[0:mask.shape[0], 0:mask.shape[1]]
    disk = ((xx - cx) ** 2 + (yy - cy) ** 2 <= r * r)
    area = int(disk.sum())
    if area == 0:
        return 1.0
    return float((mask[disk] > 0).sum()) / area


def find_candidates(img_bgr):
    """双掩膜颜色过滤 → 环形模板匹配 → 内部抑制 → 贪婪NMS，返回候选圆心列表。"""
    raw = []
    for name, lower, upper, min_cov in COLOR_MASKS:
        mask = color_mask(img_bgr, lower, upper)
        resp, best_r, valid = ring_response(mask)

        # 局部极大值 + 覆盖率阈值 + 有效占比阈值（3px 邻域峰值，精细定位用）
        dil = cv2.dilate(resp, np.ones((3, 3), np.uint8))
        peaks = (resp == dil) & (resp >= min_cov) & (valid >= MIN_RING_VALID)
        ys, xs = np.nonzero(peaks)

        for x, y in zip(xs, ys):
            r = int(best_r[y, x])
            interior = interior_green_ratio(mask, (int(x), int(y)), r)
            if interior > MAX_INTERIOR:
                continue  # 实心色块（草丛/河道等），排除
            raw.append({
                "center": (int(x), int(y)),
                "radius": r,
                "coverage": float(resp[y, x]),
                "interior": interior,
                "mask": name,
                "clf_prob": None,
            })

    # 贪婪 NMS：按覆盖率从高到低，抑制 NMS_RADIUS 内的弱峰
    raw.sort(key=lambda c: -c["coverage"])
    candidates = []
    for c in raw:
        cx, cy = c["center"]
        if all((cx - k["center"][0]) ** 2 + (cy - k["center"][1]) ** 2 > NMS_RADIUS ** 2
               for k in candidates):
            candidates.append(c)
    return candidates


# ============== 身份确认：分类器 + 模板NCC 融合 ==============
# 融合打分 = ncc + clf + FUSED_COV_W * coverage
#   ncc ：候选 patch 与参考模板（训练正样本原图）的归一化互相关，取最相似5个均值
#   clf ：RandomForest 分类器概率
#   依据：帧级对半实验（未见帧）—— 单用 clf 43%，单用 ncc 53%，融合 77%
FUSED_COV_W = 0.3
FUSED_THRESHOLD = 1.05   # 未见帧实验：真值候选大多 ≥1.0，干扰候选 ≤1.02

_clf_cache = None


def load_classifier():
    global _clf_cache
    if _clf_cache is not None:
        return _clf_cache or None
    if not MODEL_FILE.exists():
        _clf_cache = False
        return None
    # 延迟导入：复用训练脚本的特征提取，保证训练/检测一致
    sys.path.insert(0, str(Path(__file__).parent))
    from train_hero_model import extract_features
    with open(MODEL_FILE, "rb") as f:
        bundle = pickle.load(f)
    refs = bundle.get("refs")
    refs = refs.astype(np.float32) if refs is not None and len(refs) else None
    _clf_cache = (bundle["model"], extract_features,
                  bundle.get("patch_size", 24), refs)
    return _clf_cache


def _ncc(a, b):
    """归一化互相关。"""
    a = a.flatten() - a.mean()
    b = b.flatten() - b.mean()
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-6))


def _template_ncc(patch, refs, top_k=5):
    """与最相似的 top_k 个参考模板取 NCC 均值。"""
    sims = sorted((_ncc(patch, r) for r in refs), reverse=True)
    return float(np.mean(sims[:top_k]))


def score_with_classifier(img_bgr, candidates):
    """对每个候选区域做身份确认打分（写入 clf_prob / ncc / fused）。"""
    clf = load_classifier()
    if not clf:
        return candidates
    model, extract_features, patch_size, refs = clf
    H, W = img_bgr.shape[:2]
    for c in candidates:
        cx, cy = c["center"]
        half = c["radius"] + 1
        x1, y1 = max(0, cx - half), max(0, cy - half)
        x2, y2 = min(W, cx + half), min(H, cy + half)
        patch = img_bgr[y1:y2, x1:x2]
        if patch.size == 0:
            c["clf_prob"], c["ncc"], c["fused"] = 0.0, -1.0, -1.0
            continue
        patch = cv2.resize(patch, (patch_size, patch_size))
        feat = extract_features(patch).reshape(1, -1)
        c["clf_prob"] = float(model.predict_proba(feat)[0, 1])
        c["ncc"] = _template_ncc(patch.astype(np.float32), refs) if refs is not None else 0.0
        c["fused"] = c["ncc"] + c["clf_prob"] + FUSED_COV_W * c["coverage"]
    return candidates


def detect(img_bgr, use_classifier=True):
    """主入口：返回 ((px, py) 或 None, 候选列表)。"""
    candidates = find_candidates(img_bgr)
    if not candidates:
        return None, candidates

    if use_classifier:
        candidates = score_with_classifier(img_bgr, candidates)
        ok = [c for c in candidates if (c.get("fused") or -1) >= FUSED_THRESHOLD]
        if not ok:
            return None, candidates
        best = max(ok, key=lambda c: c["fused"])
    else:
        best = candidates[0]  # 已按覆盖率排序

    return best["center"], candidates


# ============== 验证 ==============
def validate(use_classifier=True, save_debug=True):
    # 汇总所有数据目录的 (目录, 帧名, 标注框)（各目录帧名会重复，按目录区分）
    entries = []  # (data_dir, file_name, boxes)
    for d in DATA_DIRS:
        lf = d / "hero_labels.json"
        labels = {}
        if lf.exists():
            labels = {item["file"]: item.get("boxes", [])
                      for item in json.loads(lf.read_text(encoding="utf-8"))}
        for fn in sorted(p.name for p in d.glob("frame_*.jpg")):
            entries.append((d, fn, labels.get(fn, [])))
    print(f"数据目录数: {len(DATA_DIRS)}，图片总数: {len(entries)}，"
          f"有标注: {sum(1 for _, _, b in entries if b)}")
    print(f"分类器二次确认: {'开' if use_classifier else '关'}")

    if save_debug:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    hit, miss, fp, tn = 0, 0, 0, 0
    miss_list, fp_list = [], []
    dists = []

    for data_dir, fn, boxes in entries:
        tag = f"{data_dir.name}/{fn}"  # 输出时带目录名区分同名帧
        img = imread_safe(data_dir / fn)
        if img is None:
            continue
        pred, candidates = detect(img, use_classifier=use_classifier)
        gt_boxes = [b for b in boxes if b[4] == "green"]

        if gt_boxes:
            l, t, r, b, _ = gt_boxes[0]
            gt_c = ((l + r) / 2, (t + b) / 2)
            if pred is not None:
                d = ((pred[0] - gt_c[0]) ** 2 + (pred[1] - gt_c[1]) ** 2) ** 0.5
                dists.append(d)
                if d <= HIT_DIST:
                    hit += 1
                else:
                    miss += 1
                    miss_list.append((tag, f"偏差{d:.1f}px pred={pred} gt=({gt_c[0]:.0f},{gt_c[1]:.0f})"))
            else:
                miss += 1
                miss_list.append((tag, f"未检出 gt=({gt_c[0]:.0f},{gt_c[1]:.0f}) 候选数={len(candidates)}"))
        else:
            if pred is None:
                tn += 1
            else:
                fp += 1
                fp_list.append((tag, f"误报 pred={pred}"))

        if save_debug:
            vis = img.copy()
            for b in gt_boxes:  # 蓝=标注真值
                cv2.rectangle(vis, (b[0], b[1]), (b[2], b[3]), (255, 0, 0), 1)
            for c in candidates[:5]:  # 黄=候选
                cv2.circle(vis, c["center"], c["radius"], (0, 255, 255), 1)
            if pred:  # 红=最终输出
                cv2.circle(vis, pred, 3, (0, 0, 255), -1)
                cv2.circle(vis, pred, 10, (0, 0, 255), 1)
            vis = cv2.resize(vis, (vis.shape[1] * 3, vis.shape[0] * 3), interpolation=cv2.INTER_NEAREST)
            sub = DEBUG_DIR / data_dir.name
            sub.mkdir(parents=True, exist_ok=True)
            cv2.imencode(".jpg", vis)[1].tofile(str(sub / fn))

    total_pos = hit + miss
    print("\n===== 验证结果 =====")
    print(f"有标注图: 命中 {hit}/{total_pos} ({hit / total_pos * 100:.1f}%)，漏检/偏移 {miss}")
    print(f"无标注图: 正确拒绝 {tn}，误报 {fp}")
    if dists:
        print(f"圆心误差: 均值 {np.mean(dists):.2f}px，中位 {np.median(dists):.2f}px，最大 {max(dists):.2f}px")
    if miss_list:
        print("\n-- 漏检/偏移明细 --")
        for fn, msg in miss_list:
            print(f"  {fn}: {msg}")
    if fp_list:
        print("\n-- 误报明细 --")
        for fn, msg in fp_list:
            print(f"  {fn}: {msg}")
    if save_debug:
        print(f"\n调试图已保存: {DEBUG_DIR}")
    return hit, miss, fp, tn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image", nargs="?", help="待检测图片路径（可选）")
    ap.add_argument("--validate", action="store_true", help="在 train1 上全量验证")
    ap.add_argument("--no-clf", action="store_true", help="禁用分类器二次确认")
    ap.add_argument("--no-debug", action="store_true", help="验证时不保存调试图")
    args = ap.parse_args()

    if args.validate:
        validate(use_classifier=not args.no_clf, save_debug=not args.no_debug)
    elif args.image:
        img = imread_safe(args.image)
        if img is None:
            print(f"无法读取: {args.image}")
            sys.exit(1)
        pred, candidates = detect(img, use_classifier=not args.no_clf)
        print(f"候选数: {len(candidates)}")
        for c in candidates[:10]:
            print(f"  center={c['center']} r={c['radius']} cov={c['coverage']:.2f} "
                  f"clf={c.get('clf_prob')} ncc={c.get('ncc')} fused={c.get('fused')}")
        print(f"检测结果: {pred}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
