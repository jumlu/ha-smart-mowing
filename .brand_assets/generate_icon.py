"""Generates the Smart Mowing brand icon/logo assets.

Not part of the integration itself - output goes to home-assistant/brands,
not into custom_components/. Kept here only so the icon can be regenerated
or tweaked later.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw

MOWER_GREEN = (46, 125, 50, 255)  # #2E7D32
MOWER_GREEN_DARK = (27, 94, 32, 255)  # #1B5E20
SPROUT_GREEN = (139, 195, 74, 255)  # #8BC34A
WHITE = (255, 255, 255, 255)


def _rounded_square_path(size: int, margin: float, radius_ratio: float):
    inset = size * margin
    box = (inset, inset, size - inset, size - inset)
    radius = (box[2] - box[0]) * radius_ratio
    return box, radius


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Mower chassis: a large rounded square, flat single-tone per HA brand style.
    box, radius = _rounded_square_path(size, margin=0.08, radius_ratio=0.34)
    draw.rounded_rectangle(box, radius=radius, fill=MOWER_GREEN)

    # Two wheels peeking out at the bottom corners.
    wheel_r = size * 0.085
    wheel_y = box[3] - wheel_r * 0.4
    for wheel_x in (box[0] + size * 0.14, box[2] - size * 0.14):
        draw.ellipse(
            (wheel_x - wheel_r, wheel_y - wheel_r, wheel_x + wheel_r, wheel_y + wheel_r),
            fill=MOWER_GREEN_DARK,
        )

    # Lidar/nav puck on top, off-center like the real mower's sensor mast.
    puck_r = size * 0.065
    puck_cx, puck_cy = size * 0.5, box[1] + size * 0.09
    draw.ellipse(
        (puck_cx - puck_r, puck_cy - puck_r, puck_cx + puck_r, puck_cy + puck_r),
        fill=MOWER_GREEN_DARK,
    )

    # Sprout (growth-based decision making) centered in the lower chassis,
    # well clear of the nav puck above it.
    cx, cy = size * 0.5, size * 0.64
    stem_w = size * 0.035
    stem_top = cy - size * 0.06
    stem_bottom = cy + size * 0.14
    draw.line((cx, stem_top, cx, stem_bottom), fill=WHITE, width=int(stem_w))
    draw.ellipse(
        (cx - stem_w / 2, stem_bottom - stem_w / 2, cx + stem_w / 2, stem_bottom + stem_w / 2),
        fill=WHITE,
    )

    # Two simple pointed-oval leaves, angled up and out from the stem tip.
    leaf_len, leaf_w = size * 0.24, size * 0.13
    supersample = 4
    for direction in (-1, 1):
        canvas_w, canvas_h = int(leaf_w * supersample), int(leaf_len * supersample)
        leaf = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        leaf_draw = ImageDraw.Draw(leaf)
        leaf_draw.ellipse((0, 0, canvas_w, canvas_h), fill=SPROUT_GREEN)
        leaf = leaf.resize((canvas_w // supersample, canvas_h // supersample), Image.LANCZOS)
        angle = 40 * direction
        leaf = leaf.rotate(angle, expand=True, resample=Image.BICUBIC)
        anchor_x = cx + direction * size * 0.11 - leaf.width / 2
        anchor_y = stem_top - leaf.height * 0.82
        img.alpha_composite(leaf, (int(anchor_x), int(anchor_y)))

    return img


def draw_logo(size_w: int, size_h: int) -> Image.Image:
    """Wordmark-free logo: same icon, slightly more breathing room, wide canvas."""
    icon_size = min(size_w, size_h)
    icon = draw_icon(icon_size)
    canvas = Image.new("RGBA", (size_w, size_h), (0, 0, 0, 0))
    canvas.alpha_composite(icon, ((size_w - icon_size) // 2, (size_h - icon_size) // 2))
    return canvas


if __name__ == "__main__":
    import os

    out_dir = os.path.dirname(__file__)

    draw_icon(256).save(os.path.join(out_dir, "icon.png"))
    draw_icon(512).save(os.path.join(out_dir, "icon@2x.png"))
    draw_logo(512, 256).save(os.path.join(out_dir, "logo.png"))
    draw_logo(1024, 512).save(os.path.join(out_dir, "logo@2x.png"))
    print("done")
