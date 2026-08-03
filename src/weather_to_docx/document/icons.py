from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw


class WeatherIconRenderer:
    """Generate local PNG icons so the DOCX never depends on emoji fonts or the network."""

    def __init__(self, cache_dir: Path, size: int = 128) -> None:
        self.cache_dir = cache_dir
        self.size = size
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def render(self, icon_key: str) -> Path:
        target = self.cache_dir / f"{icon_key}-{self.size}.png"
        if target.exists() and target.stat().st_size > 0:
            return target

        image = Image.new("RGBA", (self.size, self.size), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)
        if icon_key == "clear_day":
            self._sun(draw, 64, 64, 27)
        elif icon_key == "clear_night":
            self._moon(draw, 64, 62, 31)
        elif icon_key == "partly_cloudy_day":
            self._sun(draw, 43, 42, 21)
            self._cloud(draw, 66, 73, 1.0)
        elif icon_key == "partly_cloudy_night":
            self._moon(draw, 43, 40, 23)
            self._cloud(draw, 66, 73, 1.0)
        elif icon_key == "cloudy":
            self._cloud(draw, 64, 65, 1.22)
        elif icon_key == "rain":
            self._cloud(draw, 64, 53, 1.08)
            self._rain(draw, 35, 77, 4)
        elif icon_key == "freezing_rain":
            self._cloud(draw, 64, 51, 1.08)
            self._rain(draw, 32, 75, 3)
            self._snowflake(draw, 91, 91, 9)
        elif icon_key == "snow":
            self._cloud(draw, 64, 52, 1.08)
            for x in (35, 64, 93):
                self._snowflake(draw, x, 92, 8)
        elif icon_key == "thunderstorm":
            self._cloud(draw, 64, 48, 1.08)
            self._lightning(draw, 58, 72)
            self._rain(draw, 30, 76, 2)
        elif icon_key == "fog":
            self._cloud(draw, 64, 43, 0.92)
            for y, inset in ((76, 24), (91, 17), (106, 29)):
                draw.rounded_rectangle((inset, y, self.size - inset, y + 5), radius=3, fill=(125, 137, 148, 230))
        else:
            self._cloud(draw, 64, 65, 1.1)
        image.save(target, format="PNG", optimize=True)
        return target

    def _sun(self, draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int) -> None:
        for angle in range(0, 360, 45):
            radians = math.radians(angle)
            x1 = cx + math.cos(radians) * (radius + 8)
            y1 = cy + math.sin(radians) * (radius + 8)
            x2 = cx + math.cos(radians) * (radius + 17)
            y2 = cy + math.sin(radians) * (radius + 17)
            draw.line((x1, y1, x2, y2), fill=(232, 153, 34, 255), width=5)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(255, 193, 54, 255), outline=(222, 143, 25, 255), width=3)

    def _moon(self, draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int) -> None:
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(247, 224, 147, 255))
        draw.ellipse((cx - 4, cy - radius - 4, cx + radius + 12, cy + radius - 7), fill=(255, 255, 255, 0))

    def _cloud(self, draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float) -> None:
        fill = (221, 229, 236, 255)
        outline = (113, 129, 145, 255)
        circles = [
            (cx - 35 * scale, cy - 5 * scale, 22 * scale),
            (cx - 8 * scale, cy - 20 * scale, 29 * scale),
            (cx + 25 * scale, cy - 7 * scale, 23 * scale),
        ]
        draw.rounded_rectangle(
            (cx - 50 * scale, cy - 8 * scale, cx + 51 * scale, cy + 28 * scale),
            radius=int(17 * scale),
            fill=fill,
            outline=outline,
            width=max(2, int(3 * scale)),
        )
        for x, y, radius in circles:
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill, outline=outline, width=max(2, int(3 * scale)))
        draw.rectangle((cx - 37 * scale, cy - 7 * scale, cx + 38 * scale, cy + 24 * scale), fill=fill)

    def _rain(self, draw: ImageDraw.ImageDraw, start_x: int, y: int, count: int) -> None:
        for index in range(count):
            x = start_x + index * 21
            draw.line((x + 6, y, x, y + 18), fill=(50, 129, 198, 255), width=5)

    def _snowflake(self, draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int) -> None:
        for angle in (0, 60, 120):
            radians = math.radians(angle)
            dx = math.cos(radians) * radius
            dy = math.sin(radians) * radius
            draw.line((cx - dx, cy - dy, cx + dx, cy + dy), fill=(65, 145, 206, 255), width=3)

    def _lightning(self, draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
        points = [
            (cx + 3, cy - 8),
            (cx - 12, cy + 17),
            (cx - 1, cy + 17),
            (cx - 8, cy + 40),
            (cx + 17, cy + 7),
            (cx + 5, cy + 7),
        ]
        draw.polygon(points, fill=(244, 183, 42, 255), outline=(167, 105, 13, 255))
