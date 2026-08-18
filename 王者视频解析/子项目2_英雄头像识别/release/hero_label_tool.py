"""
英雄头像标注工具 v2.0 - 方框标注版
==================================
用方框框住英雄头像（含绿/红/蓝框），程序自动在框内定位圆心。

操作：
  - 鼠标拖拽：画方框
  - 方向键：微调最后画的框（1px）
  - Shift+方向键：微调（5px）
  - 1/2/3 键：切换阵营（绿框/红框/蓝框）
  - Enter：确认并下一张
  - Backspace / R：清除当前标注
  - Ctrl+S：保存
"""
import json
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageTk

WINDOW_W = 1000
WINDOW_H = 750
DISPLAY_SIZE = 600

COLOR_BG = "#222"
COLORS = {"green": "#00FF00", "red": "#FF4444", "blue": "#4488FF"}
COLOR_LABELS = {"green": "绿框", "red": "红框", "blue": "蓝框"}


class HeroLabelTool:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("英雄头像标注工具 v2.0 - 方框标注")
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.root.configure(bg=COLOR_BG)

        self.image_dir: Optional[Path] = None
        self.image_files: List[Path] = []
        self.current_index = 0
        self.cv_image: Optional[np.ndarray] = None
        self.display_img: Optional[ImageTk.PhotoImage] = None
        self.scale = 1.0

        # 标注: [(left, top, right, bottom, label), ...]
        self.labels_all = {}
        self.current_boxes: List[Tuple[int, int, int, int, str]] = []
        self.current_label = "green"

        # 绘制状态
        self.drawing = False
        self.draw_start = (0, 0)

        self._build_ui()
        self._bind_keys()

    # ==================== UI ====================

    def _build_ui(self):
        bar = tk.Frame(self.root, bg=COLOR_BG, height=40)
        bar.pack(fill=tk.X, padx=5, pady=5)

        tk.Button(bar, text="打开目录", command=self._open_dir, width=10,
                  bg="#444", fg="#fff").pack(side=tk.LEFT, padx=3)
        tk.Button(bar, text="◀ 上一张", command=self._prev, width=8,
                  bg="#444", fg="#fff").pack(side=tk.LEFT, padx=3)
        tk.Button(bar, text="下一张 ▶", command=self._next, width=8,
                  bg="#444", fg="#fff").pack(side=tk.LEFT, padx=3)

        self.lbl_idx = tk.Label(bar, text="0/0", bg=COLOR_BG, fg="#aaa",
                                width=10, font=("Consolas", 11))
        self.lbl_idx.pack(side=tk.LEFT, padx=5)

        self.lbl_camp = tk.Label(bar, text="阵营: 绿框 [1]", bg=COLOR_BG,
                                 fg=COLORS["green"],
                                 font=("微软雅黑", 11, "bold"))
        self.lbl_camp.pack(side=tk.LEFT, padx=15)

        for key, color in COLORS.items():
            tk.Button(bar, text=f"{COLOR_LABELS[key]} [{key[0].upper()}]",
                      command=lambda k=key: self._set_label(k),
                      width=9, bg="#333", fg=color).pack(side=tk.LEFT, padx=2)

        tk.Button(bar, text="清除(R)", command=self._clear, width=8,
                  bg="#a44", fg="#fff").pack(side=tk.LEFT, padx=10)
        tk.Button(bar, text="保存(Ctrl+S)", command=self._save, width=12,
                  bg="#2a6", fg="#fff").pack(side=tk.LEFT, padx=3)

        self.lbl_status = tk.Label(bar, text="就绪", bg=COLOR_BG, fg="#ff0",
                                   font=("微软雅黑", 10))
        self.lbl_status.pack(side=tk.RIGHT, padx=10)

        self.canvas = tk.Canvas(self.root, bg="#111", width=DISPLAY_SIZE,
                                height=DISPLAY_SIZE, cursor="crosshair")
        self.canvas.pack(pady=10)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_motion)

        bot = tk.Frame(self.root, bg=COLOR_BG, height=30)
        bot.pack(fill=tk.X, padx=5)

        self.lbl_info = tk.Label(bot, text="", bg=COLOR_BG, fg="#888",
                                 font=("Consolas", 10))
        self.lbl_info.pack(side=tk.LEFT, padx=10)
        self.lbl_coord = tk.Label(bot, text="", bg=COLOR_BG, fg="#666",
                                  font=("Consolas", 10))
        self.lbl_coord.pack(side=tk.RIGHT, padx=10)

        self.progress = ttk.Progressbar(bot, length=150)
        self.progress.pack(side=tk.RIGHT, padx=10)

    def _bind_keys(self):
        self.root.bind("<Left>", lambda e: self._prev())
        self.root.bind("<Right>", lambda e: self._next())
        self.root.bind("<Return>", lambda e: self._next())
        self.root.bind("<BackSpace>", lambda e: self._clear())
        self.root.bind("<r>", lambda e: self._clear())
        self.root.bind("<R>", lambda e: self._clear())
        self.root.bind("<Control-s>", lambda e: self._save())
        self.root.bind("<Up>", lambda e: self._nudge(0, -1))
        self.root.bind("<Down>", lambda e: self._nudge(0, 1))
        self.root.bind("<Shift-Up>", lambda e: self._nudge(0, -5))
        self.root.bind("<Shift-Down>", lambda e: self._nudge(0, 5))
        self.root.bind("<Shift-Left>", lambda e: self._nudge(-5, 0))
        self.root.bind("<Shift-Right>", lambda e: self._nudge(5, 0))
        for key, label in [("1", "green"), ("2", "red"), ("3", "blue")]:
            self.root.bind(f"<KeyPress-{key}>",
                           lambda e, l=label: self._set_label(l))

    def _set_label(self, label):
        self.current_label = label
        self.lbl_camp.config(text=f"阵营: {COLOR_LABELS[label]} [{label[0].upper()}]",
                             fg=COLORS[label])

    # ==================== 图片 ====================

    def _open_dir(self):
        d = filedialog.askdirectory(title="选择小地图目录")
        if not d:
            return
        self.image_dir = Path(d)
        self.image_files = sorted([
            p for p in self.image_dir.glob("*.jpg") if p.stat().st_size > 500
        ])
        if not self.image_files:
            messagebox.showwarning("警告", "没有图片")
            return

        lf = self.image_dir / "hero_labels.json"
        if lf.exists():
            data = json.loads(lf.read_text(encoding="utf-8"))
            for item in data:
                self.labels_all[item["file"]] = [
                    tuple(b) for b in item.get("boxes", [])
                ]
            messagebox.showinfo("加载", f"已加载 {len(self.labels_all)} 条")

        self.current_index = 0
        self._load_image()

    def _load_image(self):
        if not self.image_files:
            return
        path = self.image_files[self.current_index]
        self.cv_image = cv2.imread(str(path))
        if self.cv_image is None:
            return

        H, W = self.cv_image.shape[:2]
        self.scale = DISPLAY_SIZE / max(H, W)
        new_w = int(W * self.scale)
        new_h = int(H * self.scale)
        display = cv2.resize(self.cv_image, (new_w, new_h))
        display_rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        self.display_img = ImageTk.PhotoImage(Image.fromarray(display_rgb))

        self.canvas.delete("all")
        self.ox = (DISPLAY_SIZE - new_w) // 2
        self.oy = (DISPLAY_SIZE - new_h) // 2
        self.canvas.create_image(self.ox, self.oy, anchor=tk.NW, image=self.display_img)

        fname = path.name
        self.current_boxes = list(self.labels_all.get(fname, []))
        self._draw_boxes()

        self.lbl_idx.config(text=f"{self.current_index + 1} / {len(self.image_files)}")
        self.lbl_status.config(text=f"{path.name} ({W}×{H})")
        self._update_progress()

    # ==================== 绘制 ====================

    def _img_to_canvas(self, x, y):
        return int(x * self.scale) + self.ox, int(y * self.scale) + self.oy

    def _canvas_to_img(self, cx, cy):
        H, W = self.cv_image.shape[:2]
        x = int((cx - self.ox) / self.scale)
        y = int((cy - self.oy) / self.scale)
        return max(0, min(W - 1, x)), max(0, min(H - 1, y))

    def _draw_boxes(self):
        self.canvas.delete("box")
        for l, t, r, b, label in self.current_boxes:
            sx1, sy1 = self._img_to_canvas(l, t)
            sx2, sy2 = self._img_to_canvas(r, b)
            color = COLORS.get(label, COLORS["green"])
            self.canvas.create_rectangle(sx1, sy1, sx2, sy2, outline=color,
                                         width=2, tags="box")
            # 圆心十字
            cx_s = (sx1 + sx2) // 2
            cy_s = (sy1 + sy2) // 2
            self.canvas.create_line(cx_s - 3, cy_s, cx_s + 3, cy_s,
                                    fill=color, width=2, tags="box")
            self.canvas.create_line(cx_s, cy_s - 3, cx_s, cy_s + 3,
                                    fill=color, width=2, tags="box")

    # ==================== 交互 ====================

    def _on_press(self, event):
        if self.cv_image is None:
            return
        self.drawing = True
        self.draw_start = (event.x, event.y)
        self.canvas.delete("temp")

    def _on_drag(self, event):
        if not self.drawing:
            return
        self.canvas.delete("temp")
        x1 = min(self.draw_start[0], event.x)
        y1 = min(self.draw_start[1], event.y)
        x2 = max(self.draw_start[0], event.x)
        y2 = max(self.draw_start[1], event.y)
        # 拖拽过程中也显示正方形
        side = max(x2 - x1, y2 - y1)
        x2 = x1 + side
        y2 = y1 + side
        self.canvas.create_rectangle(x1, y1, x2, y2,
                                     outline="#FF0", width=1, dash=(3, 3),
                                     tags="temp")

    def _on_release(self, event):
        if not self.drawing:
            return
        self.drawing = False
        self.canvas.delete("temp")

        x1 = min(self.draw_start[0], event.x)
        y1 = min(self.draw_start[1], event.y)
        x2 = max(self.draw_start[0], event.x)
        y2 = max(self.draw_start[1], event.y)

        il, it = self._canvas_to_img(x1, y1)
        ir, ib = self._canvas_to_img(x2, y2)

        # 强制正方形：以左上角为锚点，边长 = max(宽, 高)
        side = max(ir - il, ib - it)
        if side < 5:
            return
        ir = min(self.cv_image.shape[1] - 1, il + side)
        ib = min(self.cv_image.shape[0] - 1, it + side)

        self.current_boxes.append((il, it, ir, ib, self.current_label))
        self._draw_boxes()
        self.lbl_status.config(text=f"框: ({il},{it},{ir},{ib}) {side}×{side}")

    def _on_motion(self, event):
        if self.cv_image is None:
            return
        x, y = self._canvas_to_img(event.x, event.y)
        self.lbl_coord.config(text=f"({x}, {y})")

    def _nudge(self, dx, dy):
        if not self.current_boxes:
            return
        H, W = self.cv_image.shape[:2]
        l, t, r, b, label = self.current_boxes[-1]
        l = max(0, min(W - 1, l + dx))
        t = max(0, min(H - 1, t + dy))
        r = max(0, min(W - 1, r + dx))
        b = max(0, min(H - 1, b + dy))
        self.current_boxes[-1] = (l, t, r, b, label)
        self._draw_boxes()

    def _clear(self):
        self.current_boxes = []
        self.canvas.delete("box")
        self.lbl_status.config(text="已清除")

    def _prev(self):
        self._auto_save()
        if self.current_index > 0:
            self.current_index -= 1
            self._load_image()

    def _next(self):
        self._auto_save()
        if self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self._load_image()
        else:
            self.lbl_status.config(text="已是最后一张")

    def _auto_save(self):
        if self.image_files and self.current_boxes:
            self.labels_all[self.image_files[self.current_index].name] = list(self.current_boxes)

    def _update_progress(self):
        total = len(self.image_files)
        done = len(self.labels_all)
        self.progress["value"] = done / max(1, total) * 100
        self.lbl_info.config(text=f"已标注: {done}/{total}")

    def _save(self):
        self._auto_save()
        if not self.labels_all:
            return
        out = []
        for fn, boxes in self.labels_all.items():
            out.append({"file": fn, "boxes": [list(b) for b in boxes]})
        path = self.image_dir / "hero_labels.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        self._update_progress()
        self.lbl_status.config(text=f"已保存 {len(out)} 条")
        messagebox.showinfo("保存", f"已保存 {len(out)} 条 → hero_labels.json")


def main():
    root = tk.Tk()
    HeroLabelTool(root)
    root.mainloop()


if __name__ == "__main__":
    main()
