"""
素材处理 v5：用对应序号的 train2/train4 模板匹配 train1/train3，
获得精确的"小地图在完整画面中的边界"标注。

策略：
  - 对每张 train1[i]，用 train2[i] 小地图本体作为模板多尺度匹配
  - 对每张 train3[i]，用 train4[i] 小地图本体作为模板多尺度匹配
  - 输出 labels.json：每张完整画面的精确 ROI

注意：train2/train4 中小地图本体本身就是正确答案的高清放大版，
所以匹配得到的 ROI 就是用户在完整画面中应该裁切的精确范围。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np


OUT_DIR = Path(__file__).resolve().parent
LABELS_PATH = OUT_DIR / "labels.json"

# 训练素材：完整游戏画面
WHOLE_DIRS = [
    Path(r"D:/wangzhe_project/screenshot_collection/train_collection/train1"),
    Path(r"D:/wangzhe_project/screenshot_collection/train_collection/train3"),
]

# 对应模板：小地图本体（高清放大版）
TEMPLATE_DIRS = [
    Path(r"D:/wangzhe_project/screenshot_collection/train_collection/train2"),
    Path(r"D:/wangzhe_project/screenshot_collection/train_collection/train4"),
]


def imread_safe(path: Path) -> np.ndarray:
    data = Path(path).read_bytes()
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"无法读取：{path}")
    return img


def extract_minimap_body(img: np.ndarray) -> np.ndarray:
    """从 train2/train4 图中提取小地图本体（非黑紧密边界）。"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    x1 = next(i for i in range(w) if (gray[:, i] > 10).sum() > h * 0.3)
    x2 = next(i for i in range(w - 1, -1, -1) if (gray[:, i] > 10).sum() > h * 0.3)
    y1 = next(i for i in range(h) if (gray[i, :] > 10).sum() > w * 0.3)
    y2 = next(i for i in range(h - 1, -1, -1) if (gray[i, :] > 10).sum() > w * 0.3)
    return img[y1:y2 + 1, x1:x2 + 1]


def refine_with_edges(gray: np.ndarray, loc: Tuple[int, int], tw: int, th: int, search_range: int = 4) -> Tuple[int, int, int, int]:
    """在匹配框附近用 Sobel 梯度找精确边界。"""
    H, W = gray.shape
    margin = search_range + 2
    y1 = max(0, loc[1] - margin)
    y2 = min(H, loc[1] + th + margin)
    x1 = max(0, loc[0] - margin)
    x2 = min(W, loc[0] + tw + margin)
    roi = gray[y1:y2, x1:x2]
    if roi.size == 0:
        return loc[0], loc[1], loc[0] + tw, loc[1] + th

    sobel_x = np.abs(cv2.Sobel(roi, cv2.CV_64F, 1, 0, ksize=3))
    sobel_y = np.abs(cv2.Sobel(roi, cv2.CV_64F, 0, 1, ksize=3))

    h_grad = sobel_y.mean(axis=1)
    v_grad = sobel_x.mean(axis=0)

    local_top = loc[1] - y1
    local_bot = loc[1] + th - y1
    local_left = loc[0] - x1
    local_right = loc[0] + tw - x1

    sr = search_range

    def pick(arr, c):
        i0 = max(0, c - sr)
        i1 = min(len(arr), c + sr + 1)
        if i1 <= i0:
            return c
        return i0 + int(np.argmax(arr[i0:i1]))

    best_up = pick(h_grad, local_top)
    best_dn = pick(h_grad, local_bot)
    best_lf = pick(v_grad, local_left)
    best_rt = pick(v_grad, local_right)

    return x1 + best_lf, y1 + best_up, x1 + best_rt, y1 + best_dn


def match_with_template(whole_img: np.ndarray, template: np.ndarray, refine: bool = True) -> Tuple[int, int, int, int, float]:
    """多尺度模板匹配 + 可选边缘细化。"""
    H, W = whole_img.shape[:2]
    gray = cv2.cvtColor(whole_img, cv2.COLOR_BGR2GRAY)
    th_t, tw_t = template.shape[:2]

    best_score = -1.0
    best_info = None
    # 缩小搜索范围，基于已知比例
    # train1: 582 高, minimap ~183 高, scale = 183/1080 ≈ 0.170
    # train3: 720 高, minimap ~207 高, scale = 207/1071 ≈ 0.193
    if H <= 600:  # train1
        scale_range = np.arange(0.165, 0.180, 0.001)
    else:  # train3
        scale_range = np.arange(0.190, 0.205, 0.001)
    for scale in scale_range:
        tw = int(tw_t * scale)
        th = int(th_t * scale)
        if tw > W * 0.5 or th > H:
            continue
        if tw < 40 or th < 40:
            continue
        tmpl = cv2.resize(template, (tw, th))
        result = cv2.matchTemplate(whole_img, tmpl, cv2.TM_CCOEFF_NORMED)
        _, maxVal, _, maxLoc = cv2.minMaxLoc(result)
        if maxVal > best_score:
            best_score = maxVal
            best_info = (tw, th, maxLoc)

    if best_info is None:
        # 兜底：用图像左上区域的几何规则
        s = int(H * 0.30)
        l, t = max(0, int(W * 0.02)), max(0, int(H * 0.02))
        return l, t, l + s, t + s, 0.0

    tw, th, loc = best_info
    if refine:
        l, t, r, b = refine_with_edges(gray, loc, tw, th)
    else:
        l, t, r, b = loc[0], loc[1], loc[0] + tw, loc[1] + th
    return l, t, r, b, float(best_score)


def main() -> None:
    # 预加载所有 train2/train4 模板，按 frame 编号索引
    templates_map: Dict[str, np.ndarray] = {}
    for d in TEMPLATE_DIRS:
        for f in sorted(d.glob("*.jpg")):
            img = imread_safe(f)
            body = extract_minimap_body(img)
            # 按 frame 编号作为 key (例如 frame_0021)
            key = f.stem.split('_')[0] + '_' + f.stem.split('_')[1]
            templates_map[key] = body
    print(f"[模板] 预加载 {len(templates_map)} 个模板")

    # 处理 train1/train3
    labels: List[Dict] = []
    total = 0
    matched = 0
    for whole_dir in WHOLE_DIRS:
        for wf in sorted(whole_dir.glob("*.jpg")):
            total += 1
            # 用 frame 编号找模板
            key = wf.stem.split('_')[0] + '_' + wf.stem.split('_')[1]
            if key not in templates_map:
                print(f"[warn] 找不到模板: {wf.name} (key={key})")
                continue

            tpl = templates_map[key]
            whole_img = imread_safe(wf)
            H, W = whole_img.shape[:2]

            l, t, r, b, score = match_with_template(whole_img, tpl, refine=True)

            labels.append({
                "file": wf.name,
                "image_size": [W, H],
                "roi": [l, t, r, b],
                "roi_size": [r - l, b - t],
                "template_score": round(score, 4),
            })
            matched += 1

            if matched % 50 == 0 or matched <= 3:
                print(f"  [{matched}] {wf.name}: {W}x{H}  "
                      f"ROI=({l},{t},{r},{b})  size={r-l}x{b-t}  "
                      f"score={score:.4f}")

    print(f"\n[完成] 共 {matched}/{total} 张标注")
    LABELS_PATH.write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[保存] {LABELS_PATH}")


if __name__ == "__main__":
    main()