import cv2
import numpy as np
import csv
import os

# ==================== 配置区 ====================
VIDEO_PATH = r"D:\b站视频\素材\2月8日 (短视频测试).mp4"   # 你的视频路径
MINIMAP_ROI = (840, 310, 1440, 1380)                # 小地图裁剪区域
HERO_COLOR = "hero"

# 网格映射表文件路径（请确保路径正确）
GRID_MAP_FILE = r"D:\study_hub\生产\输出\b站\王者自动化复盘\地图\scv简化.md"          # 你的网格符号表

# 颜色范围（针对 RGB(115,170,105) 英雄）
COLOR_RANGES = {
    "hero": [(np.array([55, 80, 90]), np.array([75, 200, 220]))]
}
# =================================================

# ---------- 1. 读取网格映射表 ----------
def load_grid_map(file_path):
    """
    从文本文件加载 20x20 网格映射表
    返回：grid[20][20] 列表，每个元素是符号字符串或 None
    """
    grid = [[None for _ in range(20)] for _ in range(20)]
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            is_first_line = True
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # 跳过 CSV 标题行（包含中文列名）
                if is_first_line and ('行' in line or '列' in line or '符号' in line):
                    is_first_line = False
                    continue
                is_first_line = False
                
                parts = line.split(',')
                if len(parts) != 3:
                    continue
                try:
                    row = int(parts[0].strip())
                    col = int(parts[1].strip())
                    symbol = parts[2].strip()
                    if 0 <= row < 20 and 0 <= col < 20:
                        grid[row][col] = symbol
                except ValueError:
                    # 跳过无法解析为整数的行
                    continue
    except FileNotFoundError:
        print(f"⚠️ 网格映射文件未找到: {file_path}")
        print("将不使用网格映射，所有符号标记为 'unknown'")
        return None
    return grid

grid = load_grid_map(GRID_MAP_FILE)

# ---------- 2. 坐标转网格符号的函数 ----------
def get_grid_symbol(x_norm, y_norm, grid):
    """
    输入归一化坐标 (0~1)，返回对应的网格行列和符号
    如果 grid 为 None，则返回 (None, None, 'unknown')
    """
    if grid is None:
        return None, None, 'unknown'
    
    # 四舍五入并钳制到 0~19
    col = round(x_norm * 20)
    row = round(y_norm * 20)
    col = min(max(col, 0), 19)
    row = min(max(row, 0), 19)
    
    symbol = grid[row][col]
    if symbol is None:
        symbol = 'unknown'
    return row, col, symbol

# ---------- 3. 英雄检测函数（原样） ----------
def detect_hero(minimap, color_ranges):
    hsv = cv2.cvtColor(minimap, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lower, upper in color_ranges:
        mask |= cv2.inRange(hsv, lower, upper)
    
    kernel = np.ones((3,3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) > 10:
            M = cv2.moments(largest)
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            return (cx, cy)
    return None

# ---------- 4. 主流程 ----------
cap = cv2.VideoCapture(VIDEO_PATH)
if not cap.isOpened():
    print("❌ 视频打开失败！请检查路径（建议纯英文路径）")
    exit()

# 获取视频尺寸
frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"📐 视频分辨率: {frame_width} x {frame_height}")

# 自适应修正 ROI
x, y, w, h = MINIMAP_ROI
if x + w > frame_width:
    w = frame_width - x
if y + h > frame_height:
    h = frame_height - y
if w <= 0 or h <= 0:
    print("❌ ROI 越界，请重新标定")
    exit()
MINIMAP_ROI = (x, y, w, h)
print(f"✅ 最终 ROI: {MINIMAP_ROI}")

fps = cap.get(cv2.CAP_PROP_FPS)
frame_interval = int(fps * 3)  # 每 3 秒采样一次

results = []
frame_count = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    if frame_count % frame_interval == 0:
        t_sec = round(frame_count / fps, 1)
        minimap = frame[y:y+h, x:x+w]
        pos = detect_hero(minimap, COLOR_RANGES[HERO_COLOR])
        
        if pos:
            # 归一化坐标
            x_norm = round(pos[0] / w, 3)
            y_norm = round(pos[1] / h, 3)
            
            # 映射到网格符号
            row, col, symbol = get_grid_symbol(x_norm, y_norm, grid)
            
            # 记录数据
            results.append([t_sec, x_norm, y_norm, row, col, symbol])
            print(f"⏱️ {t_sec}s → ({x_norm}, {y_norm}) → 网格({row},{col}) → {symbol}")
            
            # （可选）保存标记图
            marked_minimap = minimap.copy()
            cv2.circle(marked_minimap, pos, radius=5, color=(0,0,255), thickness=-1)
            output_img_path = f"marked_frame_{int(t_sec)}s.jpg"
            cv2.imwrite(output_img_path, marked_minimap)
            print(f"    📸 已保存标记图: {output_img_path}")
        else:
            # 未检测到英雄
            results.append([t_sec, None, None, None, None, 'none'])
            print(f"⏱️ {t_sec}s → 未检测到英雄")
    
    frame_count += 1

cap.release()

# ---------- 5. 保存 CSV ----------
output_path = "hero_positions_labeled.csv"
with open(output_path, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['time_sec', 'x_norm', 'y_norm', 'grid_row', 'grid_col', 'symbol'])
    writer.writerows(results)

print(f"\n✅ 处理完成！结果已保存至: {os.path.abspath(output_path)}")
print("💡 用 Excel 打开，即可看到每个时刻的网格符号")