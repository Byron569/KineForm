"""一次性：PNG → 多尺寸 ICO + 像素校验。用后即删。"""
import sys
from pathlib import Path

from PIL import Image

build = Path(__file__).resolve().parent / 'build'
base = Image.open(build / 'icon-256.png').convert('RGBA')

# 像素校验（icon-64.png 与 SVG viewBox 0 0 64 64 恰好 1:1）：
# 圆角方块外角透明、内部为品牌蓝 #4285F4、K 竖线处白色
check = Image.open(build / 'icon-64.png').convert('RGBA')
corner = check.getpixel((2, 2))            # 圆角外 → 透明
blue = check.getpixel((32, 8))             # 顶部方块内部 → 蓝色
white = check.getpixel((21, 20))           # K 竖线（21,17..47, w=4.4）→ 白色
assert corner[3] == 0, f'corner should be transparent, got {corner}'
assert blue[:3] == (66, 133, 244), f'expect #4285F4, got {blue}'
assert white[:3] == (255, 255, 255), f'expect white, got {white}'
print('pixel check OK: transparent corner / #4285F4 / white stroke')

sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
         (128, 128), (256, 256)]
base.save(build / 'icon.ico', format='ICO', sizes=sizes)
base.save(build / 'icon.png', format='PNG')

# 回读 ICO 校验多尺寸条目
ico = Image.open(build / 'icon.ico')
sizes_in = sorted(ico.info.get('sizes', set()))
assert set(sizes_in) == set(sizes), f'ico sizes: {sizes_in}'
print(f'icon.ico OK: {sorted(sizes_in)}')

# 清理中间 PNG（保留 icon.ico 与 icon.png=256 供 electron-builder/Linux）
for px in build.glob('icon-*.png'):
    px.unlink()
print('intermediate pngs cleaned; kept icon.ico + icon.png')
sys.exit(0)
