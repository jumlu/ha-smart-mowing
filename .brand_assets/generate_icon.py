"""Generates the Smart Mowing brand icon/logo assets.

Not part of the integration itself - output goes to home-assistant/brands,
not into custom_components/. Kept here only so the icon can be regenerated
or tweaked later.

Design: a classic push-mower side silhouette (two wheels, a rounded deck,
a diagonal handle) - the least ambiguous "lawn mower" pictogram there is -
as a bold white cutout on a solid squircle. Two earlier top-down/abstract
concepts (leaf-sprout, D-shaped robot-vacuum glyph, circle-with-grass-
spikes) all read as something else at a glance (a bowtie, a shield, a cat
face); a literal mower silhouette doesn't have that problem.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

GREEN = (56, 142, 60, 255)  # #388E3C
WHITE = (255, 255, 255, 255)
TRANSPARENT = (0, 0, 0, 0)

SS = 4  # supersampling factor for clean anti-aliased edges


def _canvas(size: int) -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
    s = size * SS
    img = Image.new("RGBA", (s, s), TRANSPARENT)
    return img, ImageDraw.Draw(img), s


def _down(img: Image.Image, size: int) -> Image.Image:
    return img.resize((size, size), Image.LANCZOS)


def _thick_line(draw: ImageDraw.ImageDraw, p1, p2, width: float, fill) -> None:
    """A line with round caps, built from a rectangle + two end circles."""
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    length = (dx**2 + dy**2) ** 0.5
    nx, ny = -dy / length, dx / length
    hw = width / 2
    draw.polygon(
        [
            (x1 + nx * hw, y1 + ny * hw),
            (x2 + nx * hw, y2 + ny * hw),
            (x2 - nx * hw, y2 - ny * hw),
            (x1 - nx * hw, y1 - ny * hw),
        ],
        fill=fill,
    )
    for x, y in (p1, p2):
        draw.ellipse((x - hw, y - hw, x + hw, y + hw), fill=fill)


def draw_icon(size: int) -> Image.Image:
    img, draw, s = _canvas(size)

    # Squircle background.
    margin = s * 0.06
    radius = (s - 2 * margin) * 0.30
    draw.rounded_rectangle((margin, margin, s - margin, s - margin), radius=radius, fill=GREEN)

    # Deck (mower body/hood): a squat rounded rectangle.
    deck_left, deck_right = s * 0.22, s * 0.71
    deck_top, deck_bottom = s * 0.40, s * 0.62
    deck_radius = s * 0.07
    draw.rounded_rectangle(
        (deck_left, deck_top, deck_right, deck_bottom), radius=deck_radius, fill=WHITE
    )

    # Handle: one bold diagonal bar rooted flush in the deck's top edge,
    # staying well clear of the squircle's rounded corner.
    handle_base = (deck_left + (deck_right - deck_left) * 0.62, deck_top)
    handle_tip = (s * 0.73, s * 0.215)
    handle_w = s * 0.075
    _thick_line(draw, handle_base, handle_tip, handle_w, WHITE)

    # Wheels: centered on the deck's bottom edge so their top half tucks
    # behind the deck - reads as one solid machine, not a cart with legs.
    wheel_r = s * 0.145
    wheel_y = deck_bottom
    for wheel_x in (deck_left + s * 0.10, deck_right - s * 0.10):
        draw.ellipse(
            (wheel_x - wheel_r, wheel_y - wheel_r, wheel_x + wheel_r, wheel_y + wheel_r),
            fill=WHITE,
        )
        hub_r = wheel_r * 0.32
        draw.ellipse(
            (wheel_x - hub_r, wheel_y - hub_r, wheel_x + hub_r, wheel_y + hub_r), fill=GREEN
        )

    return _down(img, size)


def draw_logo(size_w: int, size_h: int) -> Image.Image:
    """Same glyph, centered on a wider transparent canvas (no wordmark)."""
    icon_size = min(size_w, size_h)
    icon = draw_icon(icon_size)
    canvas = Image.new("RGBA", (size_w, size_h), TRANSPARENT)
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
