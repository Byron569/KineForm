"""运动姿态检测管线：视频/摄像头/图片 → 骨架可视化 + 关键点 JSON + 实时关节角度。

用法:
    python pose_cli.py video.mp4              # 视频文件
    python pose_cli.py webcam                 # 摄像头(0号)
    python pose_cli.py webcam:1               # 摄像头(1号)
    python pose_cli.py photo.jpg              # 单张图片
可选:
    --output-dir outputs   输出目录
    --device cuda:0        推理设备
    --show                实时显示窗口(按 q 退出)
    --no-angles           不在画面上绘制关节角度
"""
import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
import mmpose

ROOT = Path(__file__).resolve().parent
MIM = Path(mmpose.__file__).parent / '.mim'
POSE_CFG = MIM / 'configs/body_2d_keypoint/rtmpose/body8/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py'
POSE_CKPT = ROOT / 'rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth'
DET_CFG = MIM / 'demo/mmdetection_cfg/rtmdet_m_640-8xb32_coco-person.py'
DET_CKPT = ROOT / 'models/rtmdet_m_person.pth'

# halpe26 关键点索引
Nose, LEye, REye, LEar, REar, LSho, RSho, LElb, RElb, LWri, RWri, \
    LHip, RHip, LKnee, RKnee, LAnk, RAnk, Head, Neck, Hip, \
    LBigToe, RBigToe, LSmallToe, RSmallToe, LHeel, RHeel = range(26)

KPT_NAMES = ['nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear',
             'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
             'left_wrist', 'right_wrist', 'left_hip', 'right_hip',
             'left_knee', 'right_knee', 'left_ankle', 'right_ankle',
             'head', 'neck', 'hip', 'left_big_toe', 'right_big_toe',
             'left_small_toe', 'right_small_toe', 'left_heel', 'right_heel']

# (点1, 点2, 颜色 BGR)  左侧肢体绿色，右侧橙色，躯干/头部蓝色
SKELETON = [
    (LAnk, LKnee, (0, 220, 0)), (LKnee, LHip, (0, 220, 0)),
    (RAnk, RKnee, (0, 128, 255)), (RKnee, RHip, (0, 128, 255)),
    (LHip, Hip, (0, 220, 0)), (RHip, Hip, (0, 128, 255)),
    (Head, Neck, (255, 153, 51)), (Neck, Hip, (255, 153, 51)),
    (Neck, LSho, (0, 220, 0)), (LSho, LElb, (0, 220, 0)), (LElb, LWri, (0, 220, 0)),
    (Neck, RSho, (0, 128, 255)), (RSho, RElb, (0, 128, 255)), (RElb, RWri, (0, 128, 255)),
    (LAnk, LBigToe, (0, 220, 0)), (LAnk, LSmallToe, (0, 220, 0)), (LAnk, LHeel, (0, 220, 0)),
    (RAnk, RBigToe, (0, 128, 255)), (RAnk, RSmallToe, (0, 128, 255)), (RAnk, RHeel, (0, 128, 255)),
]

# 关节角度定义: 名称 -> (近端, 顶点, 远端)  伸直=180°
ANGLE_DEFS = {
    '左膝': (LHip, LKnee, LAnk), '右膝': (RHip, RKnee, RAnk),
    '左髋': (LSho, LHip, LKnee), '右髋': (RSho, RHip, RKnee),
    '左踝': (LKnee, LAnk, LBigToe), '右踝': (RKnee, RAnk, RBigToe),
    '左肘': (LSho, LElb, LWri), '右肘': (RSho, RElb, RWri),
}


def joint_angle(p1, p2, p3):
    """以 p2 为顶点的三 点角度（度）。任一点无效返回 None。"""
    if p1 is None or p2 is None or p3 is None:
        return None
    v1 = np.asarray(p1, float) - np.asarray(p2, float)
    v2 = np.asarray(p3, float) - np.asarray(p2, float)
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return None
    cos = np.clip(np.dot(v1, v2) / (n1 * n2), -1, 1)
    return float(np.degrees(np.arccos(cos)))


def draw_pose(img, kpts, scores, kpt_thr=0.35, angles=None):
    """在 img 上绘制骨架、关键点和关节角度，返回 img。"""
    for i, j, color in SKELETON:
        if scores[i] > kpt_thr and scores[j] > kpt_thr:
            cv2.line(img, tuple(kpts[i].astype(int)), tuple(kpts[j].astype(int)),
                     color, 2, cv2.LINE_AA)
    for k in range(len(kpts)):
        if scores[k] > kpt_thr:
            cv2.circle(img, tuple(kpts[k].astype(int)), 3, (255, 255, 255),
                       -1, cv2.LINE_AA)
    if angles:
        for name, (idx, val) in angles.items():
            if val is not None and scores[idx] > kpt_thr:
                x, y = kpts[idx].astype(int)
                cv2.putText(img, f'{val:.0f}', (int(x) + 6, int(y) - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(img, f'{val:.0f}', (int(x) + 6, int(y) - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def detect_persons(detector, frame, score_thr=0.3):
    """返回 (N,5) 数组 [x1,y1,x2,y2,score]。"""
    from mmdet.apis import inference_detector
    result = inference_detector(detector, frame)
    pred = result.pred_instances
    keep = (pred.labels == 0) & (pred.scores > score_thr)
    boxes = pred.bboxes[keep].cpu().numpy()
    scores = pred.scores[keep].cpu().numpy()
    if len(boxes) == 0:
        return np.zeros((0, 5), dtype=np.float32)
    out = np.concatenate([boxes, scores[:, None]], axis=1).astype(np.float32)
    return out[np.argsort(-out[:, 4])]  # 按分数降序，第一行为主人物


def main():
    parser = argparse.ArgumentParser(description='RTMPose-m halpe26 运动姿态检测')
    parser.add_argument('input', help='视频路径 / webcam / webcam:ID / 图片路径')
    parser.add_argument('--output-dir', default='outputs', help='输出目录')
    parser.add_argument('--device', default='cuda:0', help='推理设备')
    parser.add_argument('--show', action='store_true', help='实时显示窗口（按 q 退出）')
    parser.add_argument('--no-angles', action='store_true', help='不绘制关节角度')
    parser.add_argument('--det-thr', type=float, default=0.3, help='人体检测分数阈值')
    args = parser.parse_args()

    from mmdet.apis import init_detector
    from mmpose.apis import init_model, inference_topdown

    print('加载模型中...')
    detector = init_detector(str(DET_CFG), str(DET_CKPT), device=args.device)
    pose_model = init_model(str(POSE_CFG), str(POSE_CKPT), device=args.device)
    print('模型加载完成')

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_data = []

    def process_frame(frame):
        """检测+姿态估计，返回 (主人物kpts(26,2), scores(26,), bbox(5,), 全部结果list)。"""
        boxes = detect_persons(detector, frame, args.det_thr)
        results = []
        main_k, main_s, main_b = None, None, None
        if len(boxes) > 0:
            preds = inference_topdown(pose_model, frame, boxes)
            for i, p in enumerate(preds):
                k = p.pred_instances.keypoints[0]
                s = p.pred_instances.keypoint_scores[0]
                results.append((k, s, boxes[i]))
                if i == 0:
                    main_k, main_s, main_b = k, s, boxes[i]
        return main_k, main_s, main_b, results

    # ---------- 单张图片 ----------
    src = Path(args.input)
    if src.suffix.lower() in ('.jpg', '.jpeg', '.png', '.bmp', '.webp'):
        img = cv2.imread(str(src))
        if img is None:
            raise SystemExit(f'无法读取图片: {src}')
        t0 = time.perf_counter()
        k, s, b, results = process_frame(img)
        dt = (time.perf_counter() - t0) * 1000
        if k is not None:
            angles = {} if args.no_angles else {
                name: (def_[1], joint_angle(k[def_[0]], k[def_[1]], k[def_[2]]))
                for name, def_ in ANGLE_DEFS.items()}
            draw_pose(img, k, s, angles=angles)
            frames_data.append(dict(frame=0, keypoints=k.round(1).tolist(),
                                    scores=s.round(3).tolist(),
                                    bbox=b.round(1).tolist(), time_ms=round(dt, 1)))
            print(f'检测到 {len(results)} 人，推理耗时 {dt:.0f}ms')
        else:
            print('未检测到人体')
        out_img = out_dir / f'{src.stem}_pose.jpg'
        cv2.imwrite(str(out_img), img)
        _save_json(out_dir / f'{src.stem}_keypoints.json', frames_data, src.name, 0, dt)
        print(f'可视化: {out_img}\n关键点: {out_dir / (src.stem + "_keypoints.json")}')
        if args.show:
            cv2.imshow('pose', img)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        return

    # ---------- 视频 / 摄像头 ----------
    if args.input.startswith('webcam'):
        cam_id = int(args.input.split(':')[1]) if ':' in args.input else 0
        cap = cv2.VideoCapture(cam_id)
        fps, src_name = 30.0, f'webcam{cam_id}'
        total = -1
    else:
        if not src.exists():
            raise SystemExit(f'视频不存在: {src}')
        cap = cv2.VideoCapture(str(src))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        src_name = src.name
    if not cap.isOpened():
        raise SystemExit('无法打开视频源')

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out_video = out_dir / f'{Path(src_name).stem}_pose.mp4'
    writer = cv2.VideoWriter(str(out_video), cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))

    frame_id, t_sum, n_valid, missed = 0, 0.0, 0, 0
    print(f'开始处理 {src_name} ({w}x{h} @ {fps:.1f}fps)' + (f' 共{total}帧' if total > 0 else ''))
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t0 = time.perf_counter()
            k, s, b, results = process_frame(frame)
            t_sum += time.perf_counter() - t0

            if k is not None:
                n_valid += 1
                angles = {} if args.no_angles else {
                    name: (def_[1], joint_angle(k[def_[0]], k[def_[1]], k[def_[2]]))
                    for name, def_ in ANGLE_DEFS.items()}
                draw_pose(frame, k, s, angles=angles)
                frames_data.append(dict(
                    frame=frame_id, keypoints=k.round(1).tolist(),
                    scores=s.round(3).tolist(), bbox=b.round(1).tolist()))
            else:
                missed += 1

            # 帧号与处理速度
            cv2.putText(frame, f'#{frame_id}', (8, 24), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(frame, f'#{frame_id}', (8, 24), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (255, 255, 255), 1, cv2.LINE_AA)
            writer.write(frame)
            if args.show:
                cv2.imshow('pose (q to quit)', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            frame_id += 1
            if frame_id % 100 == 0:
                avg = t_sum / max(frame_id, 1) * 1000
                print(f'  已处理 {frame_id} 帧，平均推理 {avg:.1f}ms/帧')
    finally:
        cap.release()
        writer.release()
        if args.show:
            cv2.destroyAllWindows()

    avg_ms = t_sum / max(frame_id, 1) * 1000
    kp_json = out_dir / f'{Path(src_name).stem}_keypoints.json'
    _save_json(kp_json, frames_data, src_name, fps, avg_ms)
    print(f'\n完成: {frame_id} 帧（有效姿态 {n_valid}，漏检 {missed}）')
    print(f'平均推理: {avg_ms:.1f}ms/帧 ({1000 / max(avg_ms, 1e-6):.0f} FPS 上限)')
    print(f'可视化视频: {out_video}')
    print(f'关键点数据: {kp_json}')
    print(f'下一步分析: python sport_analysis.py "{kp_json}" --mode run|jump')


def _save_json(path, frames_data, source, fps, avg_ms):
    meta = dict(
        model='rtmpose-m halpe26 (700e body8, 256x192)',
        num_keypoints=26, keypoint_names=KPT_NAMES, source=source,
        fps=fps, frames=len(frames_data), avg_inference_ms=round(avg_ms or 0, 1))
    path.write_text(json.dumps(dict(meta=meta, frames=frames_data),
                               ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
