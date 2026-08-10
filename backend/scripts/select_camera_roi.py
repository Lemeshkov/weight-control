"""Interactively save a normalized polygon ROI from one diagnostic JPEG."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    image = cv2.imread(str(args.image))
    if image is None:
        raise SystemExit(f"Cannot read {args.image}")
    points: list[tuple[int, int]] = []
    window = "Camera ROI: click polygon, Enter=save, R=reset, Esc=cancel"

    def click(event, x, y, _flags, _data):
        if event == cv2.EVENT_LBUTTONDOWN:
            points.append((x, y))

    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window, click)
    while True:
        preview = image.copy()
        for point in points:
            cv2.circle(preview, point, 4, (0, 255, 0), -1)
        if len(points) > 1:
            cv2.polylines(preview, [np.array(points)], len(points) >= 3, (0, 255, 0), 2)
        cv2.imshow(window, preview)
        key = cv2.waitKey(30) & 0xFF
        if key in (13, 10):
            if len(points) < 3:
                continue
            height, width = image.shape[:2]
            normalized = [[round(x / (width - 1), 6), round(y / (height - 1), 6)] for x, y in points]
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
            cv2.destroyAllWindows()
            print(args.output)
            return 0
        if key in (ord("r"), ord("R")):
            points.clear()
        if key == 27:
            cv2.destroyAllWindows()
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
