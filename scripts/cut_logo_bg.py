"""Remove dark background from CRM brand logo; keep C/emoji/M/coins."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "public" / "brand" / "logo-original.png"
OUT = ROOT / "frontend" / "public" / "brand" / "logo.png"
PREVIEW_DIR = ROOT / "frontend" / "public" / "brand"

# Sampled corner background from source art.
BG = (34, 34, 44)


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing source: {SRC}")

    im = Image.open(SRC).convert("RGBA")
    pixels = im.load()
    w, h = im.size

    min_x, min_y = w, h
    max_x, max_y = 0, 0
    bg_r, bg_g, bg_b = BG

    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            dist = ((r - bg_r) ** 2 + (g - bg_g) ** 2 + (b - bg_b) ** 2) ** 0.5
            chroma = max(r, g, b) - min(r, g, b)
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b

            # Hard remove near-bg; keep saturated / brighter ink (C, emoji, M, coins).
            if dist < 22 and chroma < 24 and lum < 70:
                pixels[x, y] = (r, g, b, 0)
                continue
            if dist < 38 and chroma < 28 and lum < 62:
                # Soft edge
                t = max(0.0, min(1.0, (dist - 18) / 20))
                pixels[x, y] = (r, g, b, int(a * t))
            if pixels[x, y][3] > 12:
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y

    pad = 16
    box = (
        max(0, min_x - pad),
        max(0, min_y - pad),
        min(w, max_x + pad + 1),
        min(h, max_y + pad + 1),
    )
    out_img = im.crop(box)
    out_img.save(OUT, "PNG")
    print(f"saved {OUT} {out_img.size} {out_img.mode}")

    for name, bg_color in (
        ("preview-light.png", (245, 246, 248, 255)),
        ("preview-dark.png", (22, 27, 34, 255)),
    ):
        bg = Image.new("RGBA", (out_img.width + 48, out_img.height + 48), bg_color)
        bg.paste(out_img, (24, 24), out_img)
        path = PREVIEW_DIR / name
        bg.save(path, "PNG")
        print(f"preview {path.name} {bg.size}")

    side = out_img.copy()
    side.thumbnail((180, 40), Image.Resampling.LANCZOS)
    for bar_name, bar_bg in (
        ("preview-sidebar.png", (255, 255, 255, 255)),
        ("preview-sidebar-dark.png", (22, 27, 34, 255)),
    ):
        bar = Image.new("RGBA", (240, 56), bar_bg)
        bar.paste(side, (12, (56 - side.height) // 2), side)
        path = PREVIEW_DIR / bar_name
        bar.save(path, "PNG")
        print(f"preview {path.name} {bar.size}")


if __name__ == "__main__":
    main()
