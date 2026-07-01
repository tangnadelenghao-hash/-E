import argparse
from dataclasses import dataclass
import html
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


BOUNDARY = b"frame"


@dataclass
class DetectionResult:
    detected: bool
    corners: object
    area: float
    inner_corners: object = None


def parse_camera(value):
    """Return an OpenCV camera index for numbers, otherwise a device path."""
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return text


def camera_label(camera):
    if isinstance(camera, int):
        return f"/dev/video{camera}"
    return str(camera)


def camera_device_path(camera):
    if isinstance(camera, int):
        return f"/dev/video{camera}"

    text = str(camera).strip()
    if text.startswith("/dev/video"):
        suffix = text[len("/dev/video") :]
        if suffix.isdigit():
            return text
    return None


def configure_camera_for_fps(camera, fps=30, runner=None):
    device = camera_device_path(camera)
    if device is None:
        return False

    runner = runner or subprocess.run
    commands = [
        ["v4l2-ctl", "-d", device, "--set-ctrl=exposure_auto_priority=0"],
        ["v4l2-ctl", "-d", device, f"--set-parm={max(1, int(fps))}"],
    ]
    applied = False
    for command in commands:
        try:
            result = runner(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except (FileNotFoundError, OSError):
            continue
        applied = applied or getattr(result, "returncode", 1) == 0
    return applied


def build_index_html(camera, port):
    safe_camera = html.escape(camera_label(camera))
    safe_port = html.escape(str(port))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RK3566 USB Camera</title>
  <style>
    :root {{
      color-scheme: dark;
      font-family: Arial, sans-serif;
      background: #101418;
      color: #eef2f6;
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      grid-template-rows: auto 1fr auto;
    }}
    header, footer {{
      padding: 14px 18px;
      background: #18212b;
      border-color: #2b3948;
    }}
    header {{
      border-bottom: 1px solid #2b3948;
    }}
    footer {{
      border-top: 1px solid #2b3948;
      color: #9fb0c3;
      font-size: 13px;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 22px;
      font-weight: 700;
    }}
    main {{
      display: grid;
      place-items: center;
      padding: 16px;
    }}
    img {{
      width: min(100%, 960px);
      aspect-ratio: 4 / 3;
      object-fit: contain;
      background: #000;
      border: 1px solid #2b3948;
      border-radius: 8px;
    }}
    .meta {{
      color: #9fb0c3;
      font-size: 14px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>RK3566 USB Camera Preview</h1>
    <div class="meta">Camera: {safe_camera} | Port: {safe_port}</div>
  </header>
  <main>
    <img src="/stream.mjpg" alt="Live camera stream">
  </main>
  <footer>MJPEG stream endpoint: /stream.mjpg</footer>
</body>
</html>"""


def order_points(points):
    import numpy as np

    pts = np.asarray(points, dtype=np.float32).reshape(4, 2)
    ordered = np.zeros((4, 2), dtype=np.float32)
    sums = pts.sum(axis=1)
    diffs = np.diff(pts, axis=1).reshape(4)
    ordered[0] = pts[np.argmin(sums)]
    ordered[2] = pts[np.argmax(sums)]
    ordered[1] = pts[np.argmin(diffs)]
    ordered[3] = pts[np.argmax(diffs)]
    return ordered


def _resize_rotated_box(corners, delta):
    import cv2
    import numpy as np

    rect = cv2.minAreaRect(np.asarray(corners, dtype=np.float32).reshape(4, 2))
    width, height = float(rect[1][0]), float(rect[1][1])
    resized = (
        rect[0],
        (max(1.0, width + 2.0 * delta), max(1.0, height + 2.0 * delta)),
        rect[2],
    )
    return order_points(cv2.boxPoints(resized))


def _line_coeff(x1, y1, x2, y2):
    return (float(y1 - y2), float(x2 - x1), float(x1 * y2 - x2 * y1))


def _line_intersection(line_a, line_b):
    a1, b1, c1 = line_a
    a2, b2, c2 = line_b
    det = a1 * b2 - a2 * b1
    if abs(det) < 1e-6:
        return None
    x = (b1 * c2 - b2 * c1) / det
    y = (c1 * a2 - c2 * a1) / det
    return (x, y)


def _overlap_ratio(a0, a1, b0, b1):
    left = max(float(min(a0, a1)), float(min(b0, b1)))
    right = min(float(max(a0, a1)), float(max(b0, b1)))
    denom = max(1.0, float(max(b0, b1) - min(b0, b1)))
    return max(0.0, right - left) / denom


def _mask_ratio(mask, x0, y0, x1, y1):
    import cv2

    height, width = mask.shape[:2]
    left = max(0, min(width, int(round(min(x0, x1)))))
    right = max(0, min(width, int(round(max(x0, x1)))))
    top = max(0, min(height, int(round(min(y0, y1)))))
    bottom = max(0, min(height, int(round(max(y0, y1)))))
    if right <= left or bottom <= top:
        return 0.0
    roi = mask[top:bottom, left:right]
    return float(cv2.countNonZero(roi)) / float(roi.size)


def _scan_black_rows(mask, x0, x1, start_y, step, max_distance, threshold):
    height = mask.shape[0]
    last_good = 0
    misses_after_band = 0
    for distance in range(1, max_distance + 1):
        y = int(round(start_y + step * distance))
        if y < 0 or y >= height:
            break
        ratio = _mask_ratio(mask, x0, y - 1, x1, y + 2)
        if ratio >= threshold:
            last_good = distance
            misses_after_band = 0
        elif last_good > 0:
            misses_after_band += 1
            if misses_after_band >= 3:
                break
    return last_good


def _scan_black_cols(mask, y0, y1, start_x, step, max_distance, threshold):
    width = mask.shape[1]
    last_good = 0
    misses_after_band = 0
    for distance in range(1, max_distance + 1):
        x = int(round(start_x + step * distance))
        if x < 0 or x >= width:
            break
        ratio = _mask_ratio(mask, x - 1, y0, x + 2, y1)
        if ratio >= threshold:
            last_good = distance
            misses_after_band = 0
        elif last_good > 0:
            misses_after_band += 1
            if misses_after_band >= 3:
                break
    return last_good


def _expand_to_outer_black_band(corners, black_mask):
    import cv2
    import numpy as np

    height, width = black_mask.shape[:2]
    ordered = order_points(corners)
    min_x = float(ordered[:, 0].min())
    max_x = float(ordered[:, 0].max())
    min_y = float(ordered[:, 1].min())
    max_y = float(ordered[:, 1].max())
    rect_width = max(1.0, max_x - min_x)
    rect_height = max(1.0, max_y - min_y)
    max_distance = max(8, int(round(min(rect_width, rect_height) * 0.28)))
    threshold = 0.16

    x_padding = rect_width * 0.14
    y_padding = rect_height * 0.14
    top_extent = _scan_black_rows(
        black_mask,
        min_x + x_padding,
        max_x - x_padding,
        min_y,
        -1,
        max_distance,
        threshold,
    )
    bottom_extent = _scan_black_rows(
        black_mask,
        min_x + x_padding,
        max_x - x_padding,
        max_y,
        1,
        max_distance,
        threshold,
    )
    left_extent = _scan_black_cols(
        black_mask,
        min_y + y_padding,
        max_y - y_padding,
        min_x,
        -1,
        max_distance,
        threshold,
    )
    right_extent = _scan_black_cols(
        black_mask,
        min_y + y_padding,
        max_y - y_padding,
        max_x,
        1,
        max_distance,
        threshold,
    )

    if max(top_extent, bottom_extent, left_extent, right_extent) < 3:
        return ordered

    expanded = np.asarray(
        [
            [ordered[0][0] - left_extent, ordered[0][1] - top_extent],
            [ordered[1][0] + right_extent, ordered[1][1] - top_extent],
            [ordered[2][0] + right_extent, ordered[2][1] + bottom_extent],
            [ordered[3][0] - left_extent, ordered[3][1] + bottom_extent],
        ],
        dtype=np.float32,
    )
    expanded[:, 0] = np.clip(expanded[:, 0], 0, width - 1)
    expanded[:, 1] = np.clip(expanded[:, 1], 0, height - 1)
    if cv2.contourArea(expanded) <= cv2.contourArea(ordered):
        return ordered
    return order_points(expanded)


def _detect_black_rectangle_by_line_segments(frame, black_mask, min_area_ratio):
    import cv2
    import math
    import numpy as np

    height, width = frame.shape[:2]
    frame_area = float(width * height)
    min_side = min(width, height) * 0.12
    edge_margin = max(6.0, min(width, height) * 0.015)

    edges = cv2.Canny(black_mask, 50, 150)
    min_line_length = max(45, int(round(min(width, height) * 0.10)))
    max_line_gap = max(12, int(round(min(width, height) * 0.04)))
    threshold = max(35, int(round(min(width, height) * 0.08)))
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180.0,
        threshold=threshold,
        minLineLength=min_line_length,
        maxLineGap=max_line_gap,
    )
    if lines is None:
        return DetectionResult(False, None, 0.0)

    horizontal = []
    vertical = []
    for raw_line in lines[:, 0, :]:
        x1, y1, x2, y2 = [int(value) for value in raw_line]
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length < min_line_length:
            continue

        angle = math.degrees(math.atan2(dy, dx))
        if angle < -90:
            angle += 180
        if angle > 90:
            angle -= 180

        coeff = _line_coeff(x1, y1, x2, y2)
        if abs(angle) <= 18:
            y_mid = (y1 + y2) * 0.5
            if y_mid <= edge_margin or y_mid >= height - edge_margin:
                continue
            horizontal.append(
                {
                    "x0": min(x1, x2),
                    "x1": max(x1, x2),
                    "y": y_mid,
                    "length": length,
                    "line": coeff,
                }
            )
        elif abs(abs(angle) - 90) <= 18:
            x_mid = (x1 + x2) * 0.5
            if x_mid <= edge_margin or x_mid >= width - edge_margin:
                continue
            vertical.append(
                {
                    "y0": min(y1, y2),
                    "y1": max(y1, y2),
                    "x": x_mid,
                    "length": length,
                    "line": coeff,
                }
            )

    horizontal = sorted(horizontal, key=lambda item: item["length"], reverse=True)[:28]
    vertical = sorted(vertical, key=lambda item: item["length"], reverse=True)[:28]
    if len(horizontal) < 2 or len(vertical) < 2:
        return DetectionResult(False, None, 0.0)

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    best = None
    best_inner = None
    best_score = 0.0
    best_area = 0.0

    for top_index in range(len(horizontal)):
        for bottom_index in range(top_index + 1, len(horizontal)):
            first_h = horizontal[top_index]
            second_h = horizontal[bottom_index]
            top = first_h if first_h["y"] <= second_h["y"] else second_h
            bottom = second_h if first_h["y"] <= second_h["y"] else first_h
            approx_height = bottom["y"] - top["y"]
            if approx_height < min_side:
                continue

            for left_index in range(len(vertical)):
                for right_index in range(left_index + 1, len(vertical)):
                    first_v = vertical[left_index]
                    second_v = vertical[right_index]
                    left = first_v if first_v["x"] <= second_v["x"] else second_v
                    right = second_v if first_v["x"] <= second_v["x"] else first_v
                    approx_width = right["x"] - left["x"]
                    if approx_width < min_side:
                        continue

                    aspect = approx_width / max(1.0, approx_height)
                    if aspect < 0.65 or aspect > 2.8:
                        continue

                    intersections = [
                        _line_intersection(top["line"], left["line"]),
                        _line_intersection(top["line"], right["line"]),
                        _line_intersection(bottom["line"], right["line"]),
                        _line_intersection(bottom["line"], left["line"]),
                    ]
                    if any(point is None for point in intersections):
                        continue

                    corners = order_points(np.asarray(intersections, dtype=np.float32))
                    min_x = float(corners[:, 0].min())
                    max_x = float(corners[:, 0].max())
                    min_y = float(corners[:, 1].min())
                    max_y = float(corners[:, 1].max())
                    if min_x <= edge_margin or min_y <= edge_margin:
                        continue
                    if max_x >= (width - 1 - edge_margin) or max_y >= (height - 1 - edge_margin):
                        continue

                    area = float(cv2.contourArea(corners))
                    if area < frame_area * min_area_ratio or area > frame_area * 0.65:
                        continue

                    top_coverage = _overlap_ratio(top["x0"], top["x1"], left["x"], right["x"])
                    bottom_coverage = _overlap_ratio(bottom["x0"], bottom["x1"], left["x"], right["x"])
                    left_coverage = _overlap_ratio(left["y0"], left["y1"], top["y"], bottom["y"])
                    right_coverage = _overlap_ratio(right["y0"], right["y1"], top["y"], bottom["y"])
                    coverages = [top_coverage, bottom_coverage, left_coverage, right_coverage]
                    if top_coverage < 0.35 or bottom_coverage < 0.25:
                        continue
                    if left_coverage < 0.25 or right_coverage < 0.20:
                        continue
                    if sum(coverage >= 0.35 for coverage in coverages) < 3:
                        continue

                    strip = max(6, int(round(min(approx_width, approx_height) * 0.08)))
                    top_ratio = _mask_ratio(black_mask, min_x, min_y - strip, max_x, min_y + strip)
                    bottom_ratio = _mask_ratio(black_mask, min_x, max_y - strip, max_x, max_y + strip)
                    left_ratio = _mask_ratio(black_mask, min_x - strip, min_y, min_x + strip, max_y)
                    right_ratio = _mask_ratio(black_mask, max_x - strip, min_y, max_x + strip, max_y)
                    side_ratios = [top_ratio, bottom_ratio, left_ratio, right_ratio]
                    if sum(ratio >= 0.12 for ratio in side_ratios) < 3:
                        continue
                    if (sum(side_ratios) / 4.0) < 0.14:
                        continue

                    inner_margin = max(strip * 2, int(round(min(approx_width, approx_height) * 0.15)))
                    inner_black_ratio = _mask_ratio(
                        black_mask,
                        min_x + inner_margin,
                        min_y + inner_margin,
                        max_x - inner_margin,
                        max_y - inner_margin,
                    )
                    if inner_black_ratio > 0.38:
                        continue

                    inner_left = int(round(max(0, min(width, min_x + inner_margin))))
                    inner_right = int(round(max(0, min(width, max_x - inner_margin))))
                    inner_top = int(round(max(0, min(height, min_y + inner_margin))))
                    inner_bottom = int(round(max(0, min(height, max_y - inner_margin))))
                    if inner_right <= inner_left or inner_bottom <= inner_top:
                        continue
                    inner_mean = float(gray[inner_top:inner_bottom, inner_left:inner_right].mean())
                    border_mean = 255.0 * (1.0 - (sum(side_ratios) / 4.0))
                    contrast_score = max(0.0, inner_mean - border_mean * 0.25) / 255.0

                    score = sum(coverages) + sum(side_ratios) * 1.5 + contrast_score + (area / frame_area) * 5.0
                    if score > best_score:
                        best = corners
                        best_score = score
                        best_area = area

    if best is None:
        return DetectionResult(False, None, 0.0)

    best = _expand_to_outer_black_band(best, black_mask)
    best_area = float(cv2.contourArea(best))
    return DetectionResult(True, best, best_area)


def detect_black_rectangle(frame, min_area_ratio=0.04):
    import cv2
    import numpy as np

    if frame is None or frame.size == 0:
        return DetectionResult(False, None, 0.0)

    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    black_mask = cv2.inRange(gray, 0, 85)

    kernel_size = max(5, int(round(min(width, height) * 0.012)))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    black_mask = cv2.morphologyEx(black_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    black_mask = cv2.morphologyEx(black_mask, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(black_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return DetectionResult(False, None, 0.0)

    frame_area = float(width * height)
    min_area = frame_area * min_area_ratio
    best = None
    best_area = 0.0

    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < min_area:
            continue

        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue

        approx = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            corners = approx.reshape(4, 2)
        else:
            rect = cv2.minAreaRect(contour)
            box = cv2.boxPoints(rect)
            rect_area = float(rect[1][0] * rect[1][1])
            if rect_area <= 0:
                continue
            rectangularity = area / rect_area
            if rectangularity < 0.45:
                continue
            corners = box

        ordered = order_points(corners)
        edge_lengths = [
            np.linalg.norm(ordered[1] - ordered[0]),
            np.linalg.norm(ordered[2] - ordered[1]),
            np.linalg.norm(ordered[2] - ordered[3]),
            np.linalg.norm(ordered[3] - ordered[0]),
        ]
        if min(edge_lengths) < min(width, height) * 0.12:
            continue

        edge_margin = max(6.0, min(width, height) * 0.015)
        min_x = float(ordered[:, 0].min())
        max_x = float(ordered[:, 0].max())
        min_y = float(ordered[:, 1].min())
        max_y = float(ordered[:, 1].max())
        if min_x <= edge_margin or min_y <= edge_margin:
            continue
        if max_x >= (width - 1 - edge_margin) or max_y >= (height - 1 - edge_margin):
            continue

        if area > best_area:
            best = ordered
            best_area = area

    if best is None:
        return _detect_black_rectangle_by_line_segments(frame, black_mask, min_area_ratio)

    return DetectionResult(True, best, best_area)


def detect_black_rectangle_fast(frame, min_area_ratio=0.035):
    import cv2
    import numpy as np

    if frame is None or frame.size == 0:
        return DetectionResult(False, None, 0.0)

    height, width = frame.shape[:2]
    frame_area = float(width * height)
    min_side = min(width, height) * 0.12
    edge_margin = max(4.0, min(width, height) * 0.01)

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    black_mask = cv2.inRange(gray, 0, 75)

    kernel_size = max(3, int(round(min(width, height) * 0.01)))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    black_mask = cv2.morphologyEx(black_mask, cv2.MORPH_CLOSE, kernel, iterations=1)

    contours, hierarchy = cv2.findContours(black_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return DetectionResult(False, None, 0.0)
    hierarchy = hierarchy[0] if hierarchy is not None else None

    best = None
    best_score = 0.0
    best_area = 0.0

    for contour_index, contour in enumerate(contours):
        if len(contour) < 4:
            continue

        rect = cv2.minAreaRect(contour)
        rect_width, rect_height = float(rect[1][0]), float(rect[1][1])
        if rect_width <= 0 or rect_height <= 0:
            continue

        short_side = min(rect_width, rect_height)
        long_side = max(rect_width, rect_height)
        if short_side < min_side:
            continue

        aspect = long_side / max(1.0, short_side)
        if aspect < 0.55 or aspect > 3.2:
            continue

        parent_index = -1 if hierarchy is None else int(hierarchy[contour_index][3])
        is_hole_contour = parent_index >= 0
        raw_box = order_points(cv2.boxPoints(rect))
        if is_hole_contour:
            box = _expand_to_outer_black_band(raw_box, black_mask)
        else:
            box = raw_box.copy()
        box[:, 0] = np.clip(box[:, 0], 0, width - 1)
        box[:, 1] = np.clip(box[:, 1], 0, height - 1)
        area = float(cv2.contourArea(box))
        if area < frame_area * min_area_ratio or area > frame_area * 0.75:
            continue

        edge_box = raw_box if is_hole_contour else box
        min_x = float(edge_box[:, 0].min())
        max_x = float(edge_box[:, 0].max())
        min_y = float(edge_box[:, 1].min())
        max_y = float(edge_box[:, 1].max())
        if min_x <= edge_margin or min_y <= edge_margin:
            continue
        if max_x >= (width - 1 - edge_margin) or max_y >= (height - 1 - edge_margin):
            continue

        contour_area = max(1.0, float(cv2.contourArea(contour)))
        raw_rect_area = max(1.0, rect_width * rect_height)
        rectangularity = min(1.0, contour_area / raw_rect_area)
        hole_bonus = 1.25 if is_hole_contour else 1.0
        score = area * (rectangularity**3) * hole_bonus
        if score > best_score:
            best = box
            if is_hole_contour:
                best_inner = raw_box
            else:
                inner_margin = max(4.0, min(rect_width, rect_height) * 0.08)
                best_inner = _resize_rotated_box(box, -inner_margin)
            best_score = score
            best_area = area

    if best is None:
        return DetectionResult(False, None, 0.0)

    return DetectionResult(True, best, best_area, best_inner)


def detect_black_rectangle_resized(frame, scale=0.5, min_area_ratio=0.04):
    import cv2
    import numpy as np

    if frame is None or frame.size == 0:
        return DetectionResult(False, None, 0.0)

    scale = float(scale)
    if scale <= 0 or scale >= 0.99:
        return detect_black_rectangle(frame, min_area_ratio=min_area_ratio)

    height, width = frame.shape[:2]
    scaled_width = max(1, int(round(width * scale)))
    scaled_height = max(1, int(round(height * scale)))
    scaled_frame = cv2.resize(frame, (scaled_width, scaled_height), interpolation=cv2.INTER_AREA)
    result = detect_black_rectangle(scaled_frame, min_area_ratio=min_area_ratio)
    if not result.detected or result.corners is None:
        return result

    corners = np.asarray(result.corners, dtype=np.float32) / scale
    inner_corners = None
    if result.inner_corners is not None:
        inner_corners = np.asarray(result.inner_corners, dtype=np.float32) / scale
    return DetectionResult(True, corners, float(result.area) / (scale * scale), inner_corners)


def detect_black_rectangle_fast_resized(frame, scale=0.75, min_area_ratio=0.035):
    import cv2
    import numpy as np

    if frame is None or frame.size == 0:
        return DetectionResult(False, None, 0.0)

    scale = float(scale)
    if scale <= 0 or scale >= 0.99:
        return detect_black_rectangle_fast(frame, min_area_ratio=min_area_ratio)

    height, width = frame.shape[:2]
    scaled_width = max(1, int(round(width * scale)))
    scaled_height = max(1, int(round(height * scale)))
    scaled_frame = cv2.resize(frame, (scaled_width, scaled_height), interpolation=cv2.INTER_AREA)
    result = detect_black_rectangle_fast(scaled_frame, min_area_ratio=min_area_ratio)
    if not result.detected or result.corners is None:
        return result

    corners = np.asarray(result.corners, dtype=np.float32) / scale
    inner_corners = None
    if result.inner_corners is not None:
        inner_corners = np.asarray(result.inner_corners, dtype=np.float32) / scale
    return DetectionResult(True, corners, float(result.area) / (scale * scale), inner_corners)


class RectangleSmoother:
    def __init__(self, alpha=0.35, hold_frames=5):
        self.alpha = alpha
        self.hold_frames = hold_frames
        self._corners = None
        self._inner_corners = None
        self._area = 0.0
        self._miss_count = 0

    def update(self, result):
        import numpy as np

        if result.detected and result.corners is not None:
            corners = np.asarray(result.corners, dtype=np.float32)
            inner_corners = None if result.inner_corners is None else np.asarray(result.inner_corners, dtype=np.float32)
            if self._corners is None:
                self._corners = corners
            else:
                self._corners = self.alpha * corners + (1.0 - self.alpha) * self._corners
            self._inner_corners = inner_corners
            self._area = result.area
            self._miss_count = 0
            copied_inner = None if self._inner_corners is None else self._inner_corners.copy()
            return DetectionResult(True, self._corners.copy(), self._area, copied_inner)

        if self._corners is not None:
            self._miss_count += 1
            if self._miss_count <= self.hold_frames:
                copied_inner = None if getattr(self, "_inner_corners", None) is None else self._inner_corners.copy()
                return DetectionResult(True, self._corners.copy(), self._area, copied_inner)

        return DetectionResult(False, None, 0.0)


class FrameRateMeter:
    def __init__(self, alpha=0.2):
        self.alpha = alpha
        self._last_time = None
        self._fps = None

    def tick(self, now=None):
        now = time.monotonic() if now is None else float(now)
        if self._last_time is None:
            self._last_time = now
            return None

        elapsed = now - self._last_time
        self._last_time = now
        if elapsed <= 0:
            return self._fps

        instant_fps = 1.0 / elapsed
        if self._fps is None:
            self._fps = instant_fps
        else:
            self._fps = self.alpha * instant_fps + (1.0 - self.alpha) * self._fps
        return self._fps


class AsyncRectangleDetector:
    def __init__(self, target_fps=8, detect_scale=0.5, detect_fn=None, smoother=None):
        self.target_fps = max(0.1, float(target_fps))
        self.detect_scale = float(detect_scale)
        self.detect_fn = detect_fn or detect_black_rectangle_resized
        self.smoother = smoother or RectangleSmoother(alpha=0.35, hold_frames=4)
        self._condition = threading.Condition()
        self._result_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._pending_frame = None
        self._busy = False
        self._last_submit_time = None
        self._latest_result = DetectionResult(False, None, 0.0)

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        with self._condition:
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def submit(self, frame, now=None):
        now = time.monotonic() if now is None else float(now)
        min_interval = 1.0 / self.target_fps
        if self._last_submit_time is not None and now - self._last_submit_time < min_interval:
            return False

        with self._condition:
            if self._busy or self._pending_frame is not None:
                return False
            self._pending_frame = frame.copy()
            self._last_submit_time = now
            self._condition.notify()
            return True

    def snapshot(self):
        import numpy as np

        with self._result_lock:
            result = self._latest_result
            corners = None if result.corners is None else np.asarray(result.corners, dtype=np.float32).copy()
            inner_corners = None
            if result.inner_corners is not None:
                inner_corners = np.asarray(result.inner_corners, dtype=np.float32).copy()
            return DetectionResult(result.detected, corners, result.area, inner_corners)

    def _run(self):
        while not self._stop_event.is_set():
            with self._condition:
                while self._pending_frame is None and not self._stop_event.is_set():
                    self._condition.wait(timeout=0.1)
                if self._stop_event.is_set():
                    break
                frame = self._pending_frame
                self._pending_frame = None
                self._busy = True

            try:
                result = self.detect_fn(frame, scale=self.detect_scale)
                result = self.smoother.update(result)
            except Exception:
                result = DetectionResult(False, None, 0.0)

            with self._result_lock:
                self._latest_result = result
            with self._condition:
                self._busy = False


def draw_detection_overlay(frame, result, label=None, fps_value=None):
    import cv2
    import numpy as np

    if result.detected and result.corners is not None:
        points = np.asarray(result.corners, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(frame, [points], True, (0, 255, 0), 1, cv2.LINE_AA)
        if result.inner_corners is not None:
            inner_points = np.asarray(result.inner_corners, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(frame, [inner_points], True, (0, 0, 255), 1, cv2.LINE_AA)

    if label:
        color = (0, 255, 0) if result.detected else (0, 0, 255)
        cv2.putText(frame, label, (16, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2, cv2.LINE_AA)

    if fps_value is not None:
        text = f"FPS {fps_value:.1f}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.7
        thickness = 2
        padding = 7
        margin = 10
        (text_width, text_height), baseline = cv2.getTextSize(text, font, scale, thickness)
        x2 = frame.shape[1] - margin
        y1 = margin
        x1 = max(0, x2 - text_width - padding * 2)
        y2 = y1 + text_height + baseline + padding * 2
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 0), -1)
        cv2.putText(
            frame,
            text,
            (x1 + padding, y1 + padding + text_height),
            font,
            scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )

    return frame


class FrameStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._jpeg = None
        self._status = "Waiting for camera frame"

    def set_jpeg(self, jpeg, status="OK"):
        with self._lock:
            self._jpeg = jpeg
            self._status = status

    def snapshot(self):
        with self._lock:
            return self._jpeg, self._status


def _make_status_jpeg(message, width=640, height=480):
    import cv2
    import numpy as np

    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:] = (24, 31, 39)
    cv2.rectangle(frame, (14, 14), (width - 15, height - 15), (70, 87, 105), 2)
    cv2.putText(
        frame,
        message[:48],
        (36, height // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (230, 238, 246),
        2,
        cv2.LINE_AA,
    )
    ok, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return None
    return jpeg.tobytes()


def capture_loop(
    store,
    camera,
    width,
    height,
    fps,
    jpeg_quality,
    stop_event,
    detect_enabled=True,
    detect_fps=8,
    detect_scale=0.5,
):
    import cv2

    configure_camera_for_fps(camera, fps)
    cap = cv2.VideoCapture(camera, cv2.CAP_V4L2)
    if not cap.isOpened():
        store.set_jpeg(_make_status_jpeg(f"Cannot open {camera_label(camera)}"), "camera open failed")
        return

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)

    fail_count = 0
    delay = 1.0 / max(fps, 1)
    fps_meter = FrameRateMeter(alpha=0.2)
    detector = None
    if detect_enabled:
        detector = AsyncRectangleDetector(target_fps=detect_fps, detect_scale=detect_scale)
        detector.start()

    try:
        while not stop_event.is_set():
            loop_started = time.monotonic()
            ok, frame = cap.read()
            if not ok or frame is None:
                fail_count += 1
                if fail_count == 1 or fail_count % 30 == 0:
                    store.set_jpeg(_make_status_jpeg("Camera read failed"), "camera read failed")
                time.sleep(0.1)
                continue

            fail_count = 0
            current_fps = fps_meter.tick()
            if detect_enabled:
                detector.submit(frame)
                detection = detector.snapshot()
                label = "DETECTED" if detection.detected else "LOST"
            else:
                detection = DetectionResult(False, None, 0.0)
                label = None

            frame = draw_detection_overlay(frame, detection, label, current_fps)

            ok, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
            if ok:
                store.set_jpeg(jpeg.tobytes())

            remaining = delay - (time.monotonic() - loop_started)
            if remaining > 0:
                time.sleep(remaining)
    finally:
        if detector is not None:
            detector.stop()
        cap.release()


def stream_delay_for_fps(fps):
    fps = int(fps)
    if fps <= 0:
        fps = 30
    return 1.0 / fps


def make_handler(store, camera, port, stream_fps=30):
    stream_delay = stream_delay_for_fps(stream_fps)

    class WebcamHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body = build_index_html(camera, port).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path == "/healthz":
                _, status = store.snapshot()
                body = (status + "\n").encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path != "/stream.mjpg":
                self.send_error(404)
                return

            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()

            while True:
                jpeg, status = store.snapshot()
                if jpeg is None:
                    jpeg = _make_status_jpeg(status)
                if jpeg is None:
                    time.sleep(0.1)
                    continue

                try:
                    self.wfile.write(b"--" + BOUNDARY + b"\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii"))
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
                    time.sleep(stream_delay)
                except (BrokenPipeError, ConnectionResetError):
                    break

    return WebcamHandler


def request_shutdown(stop_event):
    stop_event.set()
    raise SystemExit(0)


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Serve a USB camera as an MJPEG web page.")
    parser.add_argument("--camera", default="9", help="OpenCV camera index or device path, default: 9")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP bind host, default: 0.0.0.0")
    parser.add_argument("--port", type=int, default=8081, help="HTTP port, default: 8081")
    parser.add_argument("--width", type=int, default=640, help="Capture width, default: 640")
    parser.add_argument("--height", type=int, default=480, help="Capture height, default: 480")
    parser.add_argument("--fps", type=int, default=30, help="Capture fps, default: 30")
    parser.add_argument("--detect-fps", type=float, default=8.0, help="Rectangle detection fps, default: 8")
    parser.add_argument("--detect-scale", type=float, default=0.75, help="Detection resize scale 0-1, default: 0.75")
    parser.add_argument("--jpeg-quality", type=int, default=80, help="JPEG quality 1-100, default: 80")
    parser.add_argument("--no-detect", dest="detect", action="store_false", help="Disable black rectangle detection overlay")
    parser.set_defaults(detect=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    camera = parse_camera(args.camera)
    stop_event = threading.Event()
    store = FrameStore()

    thread = threading.Thread(
        target=capture_loop,
        args=(
            store,
            camera,
            args.width,
            args.height,
            args.fps,
            args.jpeg_quality,
            stop_event,
            args.detect,
            args.detect_fps,
            args.detect_scale,
        ),
        daemon=True,
    )
    thread.start()

    handler = make_handler(store, camera, args.port, args.fps)
    server = ThreadingHTTPServer((args.host, args.port), handler)

    def shutdown(signum, frame):
        request_shutdown(stop_event)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    print(f"Camera: {camera_label(camera)}", flush=True)
    print(f"Listening: http://{args.host}:{args.port}/", flush=True)
    print(f"Rectangle detection: {'on' if args.detect else 'off'}", flush=True)
    print("Use adb forward tcp:{0} tcp:{0} and open http://127.0.0.1:{0}/".format(args.port), flush=True)
    try:
        server.serve_forever()
    except SystemExit:
        pass
    finally:
        stop_event.set()
        server.server_close()


if __name__ == "__main__":
    main()
