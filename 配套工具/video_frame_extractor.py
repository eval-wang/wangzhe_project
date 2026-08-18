import cv2
import os
import sys

def extract_frames(video_path, output_dir, interval_seconds=3):
    """
    从视频中每隔指定秒数截取一帧图片

    Args:
        video_path: 视频文件路径
        output_dir: 输出图片的目录
        interval_seconds: 截取间隔（秒）
    """
    # 路径规范化
    video_path = os.path.abspath(video_path)
    output_dir = os.path.abspath(output_dir)

    # 检查视频文件是否存在
    if not os.path.exists(video_path):
        print(f"错误：视频文件不存在 - {video_path}")
        return

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    print(f"输出目录已确认：{output_dir}")

    # 打开视频
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"错误：无法打开视频文件 - {video_path}")
        return

    # 获取视频的帧率
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        print("警告：无法获取帧率，使用默认 30fps")
        fps = 30

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps

    print(f"视频信息：帧率={fps:.2f}fps, 总帧数={total_frames}, 时长={duration:.2f}秒")
    print(f"截取间隔：{interval_seconds}秒")

    frame_interval = int(fps * interval_seconds)  # 每 interval_seconds 秒对应的帧数
    count = 0
    frame_index = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # 每隔指定帧数截取一张
        if frame_index % frame_interval == 0:
            timestamp = frame_index / fps  # 当前时间戳（秒）
            filename = f"frame_{count:04d}_{timestamp:.1f}s.jpg"
            output_path = os.path.join(output_dir, filename)
            success = cv2.imwrite(output_path, frame)
            if success:
                print(f"已保存：{filename}  (帧#{frame_index}, 时间={timestamp:.1f}s)")
            else:
                print(f"写入失败：{output_path}")
            count += 1

        frame_index += 1

    cap.release()
    print(f"\n完成！共截取 {count} 张图片，保存在 {output_dir}")

    # 验证输出
    actual_files = [f for f in os.listdir(output_dir) if f.endswith('.jpg')]
    print(f"验证：目录中实际有 {len(actual_files)} 个 jpg 文件")


if __name__ == "__main__":
    video_path = r'D:\wangzhe_project\相关素材\视频素材\训练营.mp4'
    output_dir = r"D:\wangzhe_project\screeshot_collection\train_collection\train5"

    print(f"视频路径：{video_path}")
    print(f"输出路径：{output_dir}")
    print("-" * 50)

    extract_frames(video_path, output_dir, interval_seconds=3)
