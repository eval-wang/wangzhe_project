"""
小地图标注工具 v1.0
==================
用于在完整游戏画面中标注小地图的精确边界。

功能：
  - 加载指定目录下的所有 .jpg 图片
  - 鼠标拖拽绘制矩形标注框
  - 支持微调（键盘方向键移动/缩放）
  - 保存/加载标注为 labels.json
  - 一键导出裁切的小地图

操作说明：
  - 鼠标拖拽：在图片上画框（仅限左上 50%×60% 区域）
  - 方向键：微调框的位置（每次 1px）
  - Shift+方向键：微调框的位置（每次 5px）
  - +/- 键：缩放框的大小
  - Enter：确认当前标注，跳下一张
  - Backspace：清除当前标注
  - Ctrl+S：保存标注到 labels.json
  - Ctrl+E：导出当前标注的裁切图
  - ← →：上一张 / 下一张
  - R：重置当前标注

数据格式：
  labels.json = [{"file": "xxx.jpg", "roi": [l, t, r, b]}, ...]
"""

import json
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageTk
import cv2
import numpy as np

# ==================== 常量 ====================
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900
CANVAS_WIDTH = 1280
CANVAS_HEIGHT = 720
MIN_BOX_SIZE = 30

# ==================== 颜色配置 ====================
COLOR_BOX = "#00FF00"          # 标注框颜色
COLOR_BOX_SELECTED = "#FF0000"  # 选中标注框
COLOR_BG = "#333333"            # 背景色
COLOR_INFO = "#AAAAAA"          # 信息栏文字

# ==================== 工具主体 ====================


class LabelTool:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("小地图标注工具 v1.0")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.configure(bg=COLOR_BG)

        # 状态
        self.image_dir: Optional[Path] = None
        self.image_files: List[Path] = []
        self.current_index: int = 0
        self.photo: Optional[ImageTk.PhotoImage] = None
        self.cv_image: Optional[np.ndarray] = None  # 当前 BGR 图像
        self.display_image: Optional[np.ndarray] = None
        self.scale_x: float = 1.0
        self.scale_y: float = 1.0
        self.offset_x: int = 0
        self.offset_y: int = 0

        # 标注数据
        self.labels: Dict[str, List[int]] = {}  # filename -> [l, t, r, b]
        self.current_roi: Optional[List[int]] = None  # 当前图片的 ROI

        # 绘制状态
        self.drawing = False
        self.start_x = 0
        self.start_y = 0
        self.end_x = 0
        self.end_y = 0
        self.box_id = None

        # 构建 UI
        self._build_ui()
        self._bind_keys()

    # ==================== UI 构建 ====================

    def _build_ui(self):
        # 顶部工具栏
        toolbar = tk.Frame(self.root, bg=COLOR_BG, height=40)
        toolbar.pack(fill=tk.X, padx=5, pady=5)

        tk.Button(toolbar, text="打开目录", command=self._open_dir, width=12,
                  bg="#444", fg="#fff").pack(side=tk.LEFT, padx=3)

        self.btn_prev = tk.Button(toolbar, text="◀ 上一张", command=self._prev_image,
                                  width=10, bg="#444", fg="#fff")
        self.btn_prev.pack(side=tk.LEFT, padx=3)

        self.lbl_index = tk.Label(toolbar, text="0 / 0", bg=COLOR_BG, fg=COLOR_INFO,
                                  width=12, font=("Consolas", 11))
        self.lbl_index.pack(side=tk.LEFT, padx=5)

        self.btn_next = tk.Button(toolbar, text="下一张 ▶", command=self._next_image,
                                  width=10, bg="#444", fg="#fff")
        self.btn_next.pack(side=tk.LEFT, padx=3)

        tk.Button(toolbar, text="保存标注 (Ctrl+S)", command=self._save_labels,
                  width=18, bg="#2a6", fg="#fff").pack(side=tk.LEFT, padx=10)

        tk.Button(toolbar, text="导出裁切 (Ctrl+E)", command=self._export_crop,
                  width=18, bg="#26a", fg="#fff").pack(side=tk.LEFT, padx=3)

        self.btn_reset = tk.Button(toolbar, text="重置 (R)", command=self._reset_roi,
                                   width=10, bg="#a44", fg="#fff")
        self.btn_reset.pack(side=tk.LEFT, padx=3)

        # 状态标签
        self.lbl_status = tk.Label(toolbar, text="就绪", bg=COLOR_BG, fg="#ff0",
                                   font=("微软雅黑", 10))
        self.lbl_status.pack(side=tk.RIGHT, padx=10)

        # 画布
        canvas_frame = tk.Frame(self.root, bg=COLOR_BG)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.canvas = tk.Canvas(canvas_frame, bg="#111",
                                width=CANVAS_WIDTH, height=CANVAS_HEIGHT,
                                cursor="crosshair")
        self.canvas.pack(pady=5)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_motion)

        # 底部信息栏
        bottom = tk.Frame(self.root, bg=COLOR_BG, height=50)
        bottom.pack(fill=tk.X, padx=5, pady=3)

        self.lbl_roi = tk.Label(bottom, text="ROI: 未标注", bg=COLOR_BG,
                                fg=COLOR_INFO, font=("Consolas", 11))
        self.lbl_roi.pack(side=tk.LEFT, padx=10)

        self.lbl_size = tk.Label(bottom, text="", bg=COLOR_BG, fg=COLOR_INFO,
                                 font=("Consolas", 10))
        self.lbl_size.pack(side=tk.LEFT, padx=10)

        self.lbl_coord = tk.Label(bottom, text="", bg=COLOR_BG, fg="#888",
                                  font=("Consolas", 10))
        self.lbl_coord.pack(side=tk.RIGHT, padx=10)

        # 进度条
        self.progress = ttk.Progressbar(bottom, length=200)
        self.progress.pack(side=tk.RIGHT, padx=10)

    def _bind_keys(self):
        self.root.bind("<Left>", lambda e: self._prev_image())
        self.root.bind("<Right>", lambda e: self._next_image())
        self.root.bind("<Return>", lambda e: self._next_image())
        self.root.bind("<BackSpace>", lambda e: self._reset_roi())
        self.root.bind("<Control-s>", lambda e: self._save_labels())
        self.root.bind("<Control-e>", lambda e: self._export_crop())
        self.root.bind("<r>", lambda e: self._reset_roi())
        self.root.bind("<R>", lambda e: self._reset_roi())

        # 微调
        self.root.bind("<Up>", lambda e: self._nudge(0, -1))
        self.root.bind("<Down>", lambda e: self._nudge(0, 1))
        self.root.bind("<Shift-Up>", lambda e: self._nudge(0, -5))
        self.root.bind("<Shift-Down>", lambda e: self._nudge(0, 5))
        self.root.bind("<Shift-Left>", lambda e: self._nudge(-5, 0))
        self.root.bind("<Shift-Right>", lambda e: self._nudge(5, 0))

        self.root.bind("<plus>", lambda e: self._nudge_size(2))
        self.root.bind("<equal>", lambda e: self._nudge_size(2))
        self.root.bind("<minus>", lambda e: self._nudge_size(-2))

    # ==================== 图片加载 ====================

    def _open_dir(self):
        d = filedialog.askdirectory(title="选择图片目录")
        if not d:
            return
        self.image_dir = Path(d)
        self.image_files = sorted([
            p for p in self.image_dir.glob("*.jpg")
            if p.stat().st_size > 10000
        ])
        # 也找 png
        self.image_files += sorted(self.image_dir.glob("*.png"))
        self.image_files.sort(key=lambda p: p.stem)

        if not self.image_files:
            messagebox.showwarning("警告", "目录中没有找到图片文件")
            return

        # 尝试加载已有的 labels.json
        label_file = self.image_dir / "labels.json"
        if label_file.exists():
            try:
                data = json.loads(label_file.read_text(encoding="utf-8"))
                for item in data:
                    self.labels[item["file"]] = item.get("roi", [])
                messagebox.showinfo("加载", f"已加载 {len(self.labels)} 条已有标注")
            except Exception:
                pass

        self.current_index = 0
        self._load_image()
        self._update_progress()

    def _load_image(self):
        if not self.image_files:
            return
        path = self.image_files[self.current_index]
        self.cv_image = cv2.imread(str(path))
        if self.cv_image is None:
            self.lbl_status.config(text=f"无法读取: {path.name}")
            return

        # 计算缩放
        h, w = self.cv_image.shape[:2]
        self.scale_x = CANVAS_WIDTH / w
        self.scale_y = CANVAS_HEIGHT / h
        scale = min(self.scale_x, self.scale_y)
        self.scale_x = scale
        self.scale_y = scale

        # 居中偏移
        new_w = int(w * scale)
        new_h = int(h * scale)
        self.offset_x = (CANVAS_WIDTH - new_w) // 2
        self.offset_y = (CANVAS_HEIGHT - new_h) // 2

        # 缩放图片
        display = cv2.resize(self.cv_image, (new_w, new_h))
        display_rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(display_rgb)
        self.photo = ImageTk.PhotoImage(pil_img)
        self.display_image = display

        # 清空画布
        self.canvas.delete("all")
        self.canvas.create_image(self.offset_x, self.offset_y,
                                 anchor=tk.NW, image=self.photo)

        # 加载已有标注
        fname = path.name
        if fname in self.labels and self.labels[fname]:
            self.current_roi = self.labels[fname]
            self._draw_roi()
        else:
            self.current_roi = None

        self.lbl_index.config(text=f"{self.current_index + 1} / {len(self.image_files)}")
        self.lbl_status.config(text=f"{path.name}  ({w}×{h})")
        self._update_info()

    # ==================== 绘制 ====================

    def _draw_roi(self):
        """在画布上绘制当前 ROI。"""
        self.canvas.delete("roi")
        if self.current_roi is None:
            return
        l, t, r, b = self.current_roi
        x1 = int(l * self.scale_x) + self.offset_x
        y1 = int(t * self.scale_y) + self.offset_y
        x2 = int(r * self.scale_x) + self.offset_x
        y2 = int(b * self.scale_y) + self.offset_y
        self.canvas.create_rectangle(x1, y1, x2, y2, outline=COLOR_BOX,
                                     width=2, tags="roi")
        # 尺寸标签
        self.canvas.create_text(x1 + 4, max(y1 - 10, 4),
                                text=f"{r-l}×{b-t}",
                                anchor=tk.NW, fill=COLOR_BOX,
                                font=("Consolas", 11), tags="roi")

    def _on_press(self, event):
        if self.cv_image is None:
            return
        # 限制绘制区域在图片范围内
        x = event.x - self.offset_x
        y = event.y - self.offset_y
        if x < 0 or y < 0:
            return
        img_h, img_w = self.cv_image.shape[:2]
        if x > img_w * self.scale_x or y > img_h * self.scale_y:
            return
        self.drawing = True
        self.start_x = event.x
        self.start_y = event.y
        self.canvas.delete("temp_box")

    def _on_drag(self, event):
        if not self.drawing:
            return
        self.canvas.delete("temp_box")
        x1, y1 = self.start_x, self.start_y
        x2, y2 = event.x, event.y
        # 限制在图片范围内
        self.canvas.create_rectangle(x1, y1, x2, y2, outline="#FF0",
                                     width=1, dash=(4, 4), tags="temp_box")

    def _on_release(self, event):
        if not self.drawing:
            return
        self.drawing = False
        self.canvas.delete("temp_box")

        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)

        # 转换回图片坐标
        img_l = max(0, int((x1 - self.offset_x) / self.scale_x))
        img_t = max(0, int((y1 - self.offset_y) / self.scale_y))
        img_r = min(self.cv_image.shape[1] - 1, int((x2 - self.offset_x) / self.scale_x))
        img_b = min(self.cv_image.shape[0] - 1, int((y2 - self.offset_y) / self.scale_y))

        w, h = img_r - img_l, img_b - img_t
        if w < MIN_BOX_SIZE or h < MIN_BOX_SIZE:
            self.lbl_status.config(text="框太小，请重新绘制 (最小 30×30)")
            return

        self.current_roi = [img_l, img_t, img_r, img_b]
        self._draw_roi()
        self._update_info()
        self.lbl_status.config(text=f"标注完成: ({img_l},{img_t},{img_r},{img_b}) {w}×{h}")

    def _on_motion(self, event):
        if self.cv_image is None:
            return
        x = int((event.x - self.offset_x) / self.scale_x)
        y = int((event.y - self.offset_y) / self.scale_y)
        img_h, img_w = self.cv_image.shape[:2]
        if 0 <= x < img_w and 0 <= y < img_h:
            self.lbl_coord.config(text=f"({x}, {y})")
        else:
            self.lbl_coord.config(text="")

    # ==================== 操作 ====================

    def _update_info(self):
        if self.current_roi:
            l, t, r, b = self.current_roi
            w, h = r - l, b - t
            self.lbl_roi.config(text=f"ROI: ({l}, {t}) → ({r}, {b})")
            self.lbl_size.config(text=f"尺寸: {w}×{h}  | 宽高比: {w/h:.3f}")
        else:
            self.lbl_roi.config(text="ROI: 未标注")
            self.lbl_size.config(text="")

    def _update_progress(self):
        total = len(self.image_files)
        done = len(self.labels)
        self.progress["value"] = done / max(1, total) * 100

    def _nudge(self, dx, dy):
        """微调位置。"""
        if self.current_roi is None:
            return
        l, t, r, b = self.current_roi
        img_h, img_w = self.cv_image.shape[:2]
        l = max(0, l + dx)
        t = max(0, t + dy)
        r = min(img_w - 1, r + dx)
        b = min(img_h - 1, b + dy)
        self.current_roi = [l, t, r, b]
        self._draw_roi()
        self._update_info()

    def _nudge_size(self, d):
        """缩放大小。"""
        if self.current_roi is None:
            return
        l, t, r, b = self.current_roi
        img_h, img_w = self.cv_image.shape[:2]
        # 同时缩放四边
        l = max(0, l - d)
        t = max(0, t - d)
        r = min(img_w - 1, r + d)
        b = min(img_h - 1, b + d)
        if r - l < MIN_BOX_SIZE or b - t < MIN_BOX_SIZE:
            return
        self.current_roi = [l, t, r, b]
        self._draw_roi()
        self._update_info()

    def _reset_roi(self):
        self.current_roi = None
        self.canvas.delete("roi")
        self._update_info()
        self.lbl_status.config(text="标注已清除")

    def _prev_image(self):
        if not self.image_files:
            return
        self._auto_save_current()
        if self.current_index > 0:
            self.current_index -= 1
            self._load_image()
            self._update_progress()

    def _next_image(self):
        if not self.image_files:
            return
        self._auto_save_current()
        if self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self._load_image()
            self._update_progress()
        else:
            self.lbl_status.config(text="已是最后一张")

    def _auto_save_current(self):
        """自动保存当前标注到内存。"""
        if self.image_files and self.current_roi is not None:
            fname = self.image_files[self.current_index].name
            self.labels[fname] = list(self.current_roi)

    # ==================== 保存/导出 ====================

    def _save_labels(self):
        self._auto_save_current()
        if not self.labels:
            messagebox.showinfo("提示", "没有任何标注数据")
            return
        out = []
        for fname, roi in self.labels.items():
            out.append({"file": fname, "roi": roi})
        path = self.image_dir / "labels.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        self._update_progress()
        self.lbl_status.config(text=f"已保存 {len(out)} 条标注 → labels.json")
        messagebox.showinfo("保存", f"已保存 {len(out)} 条标注到\n{path}")

    def _export_crop(self):
        """导出当前标注的裁切图。"""
        if self.current_roi is None or self.cv_image is None:
            messagebox.showinfo("提示", "请先标注当前图片")
            return
        l, t, r, b = self.current_roi
        cropped = self.cv_image[t:b+1, l:r+1].copy()
        out_dir = self.image_dir / "_crops"
        out_dir.mkdir(exist_ok=True)
        fname = self.image_files[self.current_index].stem + "_crop.jpg"
        out_path = out_dir / fname
        cv2.imwrite(str(out_path), cropped, [cv2.IMWRITE_JPEG_QUALITY, 95])
        self.lbl_status.config(text=f"已导出: {fname}")
        messagebox.showinfo("导出", f"裁切图已保存:\n{out_path}\n尺寸: {cropped.shape[1]}×{cropped.shape[0]}")


# ==================== 入口 ====================

def main():
    root = tk.Tk()
    LabelTool(root)
    root.mainloop()


if __name__ == "__main__":
    main()
