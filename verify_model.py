# 验证 RTMPose-m halpe26 模型：1) state_dict 匹配检查 2) 单图推理
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent
MIM = ROOT / '.venv/Lib/site-packages/mmpose/.mim'
POSE_CFG = MIM / 'configs/body_2d_keypoint/rtmpose/body8/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py'
POSE_CKPT = ROOT / 'rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth'
DET_CFG = MIM / 'demo/mmdetection_cfg/rtmdet_m_640-8xb32_coco-person.py'
DET_CKPT = ROOT / 'models/rtmdet_m_person.pth'
IMG = ROOT / 'test_running.jpg'

print('=== 1. state_dict 匹配检查 ===')
from mmpose.apis import init_model

model = init_model(str(POSE_CFG), checkpoint=None, device='cpu')
ckpt = torch.load(str(POSE_CKPT), map_location='cpu')
sd = ckpt.get('state_dict', ckpt)
missing, unexpected = model.load_state_dict(sd, strict=False)
print(f'missing keys: {len(missing)}, unexpected keys: {len(unexpected)}')
if missing:
    print('  missing 示例:', missing[:5])
if unexpected:
    print('  unexpected 示例:', unexpected[:5])
match = '完全匹配' if not missing and not unexpected else '不匹配!'
print(f'checkpoint 与 body8-halpe26 配置: {match}')

print('\n=== 2. 单图推理（GPU）===')
from mmpose.apis import MMPoseInferencer

inferencer = MMPoseInferencer(
    pose2d=str(POSE_CFG),
    pose2d_weights=str(POSE_CKPT),
    det_model=str(DET_CFG),
    det_weights=str(DET_CKPT),
    device='cuda:0',
)
gen = inferencer(str(IMG), show=False, out_dir=str(ROOT / 'outputs'), return_vis=True)
res = next(gen)
preds = res['predictions'][0]
print(f'检测到人数: {len(preds)}')
for i, p in enumerate(preds):
    kps = np.array(p['keypoints'])
    scores = np.array(p['keypoint_scores'])
    print(f'人 {i}: {kps.shape[0]} 个关键点, 平均置信度 {scores.mean():.3f}')
    print('  各点置信度:', np.round(scores, 2).tolist())
print('可视化结果已保存到 outputs/ 目录')
