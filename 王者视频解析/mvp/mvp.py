
VIDEO_PATH = r"D:\素材\2月8日 (短视频测试).mp4"  # 改你的视频路径
MINIMAP_ROI = (840, 310, 1440, 1380)  # (x, y, w, h) 小地图区域
HERO_COLOR = "hero"


import cv2
import numpy as np
import csv
import os

# 专为 RGB(115,170,105) 定制的小地图英雄识别范围
COLOR_RANGES = {
    "hero": [(np.array([55, 80, 90]), np.array([75, 200, 220]))]
}

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
        if cv2.contourArea(largest) > 10:  # 过滤噪点
            M = cv2.moments(largest)
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            return (cx, cy)
    return None

# 主流程
cap = cv2.VideoCapture(VIDEO_PATH)
if not cap.isOpened():
    print("❌ 视频打开失败！请检查路径是否正确")
    exit()

fps = cap.get(cv2.CAP_PROP_FPS)
frame_interval = int(fps * 3)  # 每3秒
x, y, w, h = MINIMAP_ROI
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
            # 归一化坐标（0~1）
            norm_pos = (round(pos[0]/w, 3), round(pos[1]/h, 3))
            results.append([t_sec, norm_pos[0], norm_pos[1]])
            print(f"⏱️ {t_sec}s → 位置: {norm_pos}")
                        # 👇👇👇 新增：在小地图上画红点，并保存整张截图 👇👇👇
            marked_minimap = minimap.copy()
            cv2.circle(marked_minimap, pos, radius=5, color=(0, 0, 255), thickness=-1)  # 红色实心圆
            output_img_path = f"marked_frame_{int(t_sec)}s.jpg"
            cv2.imwrite(output_img_path, marked_minimap)
            print(f"    📸 已保存标记图: {output_img_path}")
        else:
            results.append([t_sec, None, None])
            print(f"⏱️ {t_sec}s → 未检测到英雄（正常现象）")
    frame_count += 1
cap.release()

# 保存结果
output_path = "hero_positions.csv"
with open(output_path, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['time_sec', 'x_norm', 'y_norm'])
    writer.writerows(results)

print(f"\n✅ MVP成功！结果已保存至: {os.path.abspath(output_path)}")
print("💡 小提示：用Excel打开CSV，筛选掉空值行，就能看到英雄移动轨迹啦！")