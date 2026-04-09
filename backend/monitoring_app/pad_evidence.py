from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def face_bbox_to_xyxy(
    face_bbox: tuple[int, int, int, int],
    img_w: int,
    img_h: int,
) -> tuple[float, float, float, float]:
    """Convert face box ``(x, y, w, h)`` to inclusive float xyxy clipped to the image.

    Args:
        face_bbox: OpenCV-style face rectangle.
        img_w: Image width in pixels.
        img_h: Image height in pixels.

    Returns:
        Tuple ``(x1, y1, x2, y2)`` with ``x2 > x1`` and ``y2 > y1``.
    """
    x, y, w, h = face_bbox
    x1 = float(max(0, x))
    y1 = float(max(0, y))
    x2 = float(min(img_w - 1, x + w))
    y2 = float(min(img_h - 1, y + h))
    if x2 <= x1:
        x2 = x1 + 1.0
    if y2 <= y1:
        y2 = y1 + 1.0
    return x1, y1, x2, y2


def expand_xyxy(
    xyxy: tuple[float, float, float, float],
    scale: float,
    img_w: int,
    img_h: int,
) -> tuple[float, float, float, float]:
    """Uniformly scale a box about its center and clip to image bounds.

    Args:
        xyxy: Input box ``(x1, y1, x2, y2)``.
        scale: Multiplier applied to width and height (>= 1 expands the box).
        img_w: Image width.
        img_h: Image height.

    Returns:
        Expanded and clipped ``(x1, y1, x2, y2)``.
    """
    x1, y1, x2, y2 = xyxy
    cx = 0.5 * (x1 + x2)
    cy = 0.5 * (y1 + y2)
    w = (x2 - x1) * scale
    h = (y2 - y1) * scale
    nx1 = max(0.0, cx - 0.5 * w)
    ny1 = max(0.0, cy - 0.5 * h)
    nx2 = min(float(img_w - 1), cx + 0.5 * w)
    ny2 = min(float(img_h - 1), cy + 0.5 * h)
    if nx2 <= nx1:
        nx2 = nx1 + 1.0
    if ny2 <= ny1:
        ny2 = ny1 + 1.0
    return nx1, ny1, nx2, ny2


def iou_xyxy(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    """Intersection-over-union for two axis-aligned rectangles."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    aa = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    ba = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    denom = aa + ba - inter
    return float(inter / denom) if denom > 1e-6 else 0.0


def intersection_area_xyxy(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    """Area of intersection of two axis-aligned rectangles."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    return float(iw * ih)


def face_center_in_xyxy(
    face_xyxy: tuple[float, float, float, float],
    box: tuple[float, float, float, float],
) -> bool:
    """Return True if the face center lies inside ``box``."""
    x1, y1, x2, y2 = face_xyxy
    cx = 0.5 * (x1 + x2)
    cy = 0.5 * (y1 + y2)
    bx1, by1, bx2, by2 = box
    return bool(bx1 <= cx <= bx2 and by1 <= cy <= by2)


def device_presentation_relevant(
    face_bbox: Optional[tuple[int, int, int, int]],
    dev_xyxy: tuple[float, float, float, float],
    img_w: int,
    img_h: int,
    *,
    expand_scale: float,
    iou_min: float,
    cover_ratio_min: float,
) -> tuple[bool, str]:
    """Return whether a COCO device box plausibly hosts the attendance face.

    Args:
        face_bbox: Primary face ``(x, y, w, h)`` or None.
        dev_xyxy: Detector box ``(x1, y1, x2, y2)``.
        img_w: Image width.
        img_h: Image height.
        expand_scale: Factor to expand the face box before IoU tests.
        iou_min: Minimum IoU between expanded face and device for relevance.
        cover_ratio_min: Minimum fraction of face area overlapped by device.

    Returns:
        ``(relevant, short_reason_code)``.
    """
    if face_bbox is None:
        return False, "no_face"
    face_xy = face_bbox_to_xyxy(face_bbox, img_w, img_h)
    face_area = max(
        1.0,
        (face_xy[2] - face_xy[0]) * (face_xy[3] - face_xy[1]),
    )
    expanded = expand_xyxy(face_xy, expand_scale, img_w, img_h)
    diou = iou_xyxy(expanded, dev_xyxy)
    if diou >= iou_min:
        return True, f"device_gate_iou>={iou_min}"
    inter = intersection_area_xyxy(face_xy, dev_xyxy)
    cover = inter / face_area
    if cover >= cover_ratio_min:
        return True, f"device_gate_cover>={cover_ratio_min}"
    if face_center_in_xyxy(face_xy, dev_xyxy) and cover >= cover_ratio_min * 0.55:
        return True, "device_gate_center_in_box"
    return False, "device_background_context"


def frame_quad_face_relevant(
    face_bbox: Optional[tuple[int, int, int, int]],
    qx: int,
    qy: int,
    qw: int,
    qh: int,
    img_w: int,
    img_h: int,
    *,
    expand_scale: float,
    iou_min: float,
) -> tuple[bool, str]:
    """Return whether a Canny quad is spatially tied to the face (presentation)."""
    if face_bbox is None:
        return False, "no_face"
    face_xy = face_bbox_to_xyxy(face_bbox, img_w, img_h)
    quad_xyxy = (float(qx), float(qy), float(qx + qw), float(qy + qh))
    expanded = expand_xyxy(face_xy, expand_scale, img_w, img_h)
    qiou = iou_xyxy(expanded, quad_xyxy)
    if qiou >= iou_min:
        return True, f"frame_gate_iou>={iou_min}"
    cx = 0.5 * (face_xy[0] + face_xy[2])
    cy = 0.5 * (face_xy[1] + face_xy[3])
    x1, y1, x2, y2 = quad_xyxy
    if x1 <= cx <= x2 and y1 <= cy <= y2:
        return True, "frame_gate_face_center_inside"
    return False, "frame_background_context"


def _inner_face_crop_bgr(
    img_bgr: np.ndarray,
    face_bbox: tuple[int, int, int, int],
    inner_scale: float,
) -> Optional[np.ndarray]:
    """Crop a central fraction of the face box to reduce background leakage.

    Args:
        img_bgr: Full BGR image.
        face_bbox: Face ``(x, y, w, h)``.
        inner_scale: Linear fraction ``(0, 1]`` of face width/height to keep.

    Returns:
        BGR crop or None if degenerate.
    """
    x, y, fw, fh = face_bbox
    cx = x + 0.5 * fw
    cy = y + 0.5 * fh
    iw = max(2, int(fw * inner_scale))
    ih = max(2, int(fh * inner_scale))
    x1 = int(max(0, round(cx - 0.5 * iw)))
    y1 = int(max(0, round(cy - 0.5 * ih)))
    x2 = int(min(img_bgr.shape[1], round(cx + 0.5 * iw)))
    y2 = int(min(img_bgr.shape[0], round(cy + 0.5 * ih)))
    if x2 <= x1 + 1 or y2 <= y1 + 1:
        return None
    return img_bgr[y1:y2, x1:x2].copy()


def signal_recapture_face_roi(
    img_bgr: np.ndarray,
    face_bbox: Optional[tuple[int, int, int, int]],
    *,
    inner_face_scale: float,
    fft_ring_inner: int,
    fft_ring_outer: int,
    fft_baseline: float,
    fft_scale: float,
    sobel_aniso_min: float,
    sobel_aniso_scale: float,
    min_laplacian_var: float,
    blur_dampen_factor: float,
) -> tuple[float, list[str]]:
    """Estimate screen/recapture likelihood from inner-face texture (FFT + gradients).

    Uses a central face crop (not a large padded square), rejects very blurry crops,
    measures FFT peakiness instead of raw ring-energy mass, and requires agreement
    between FFT periodicity and Sobel anisotropy so a single noisy channel cannot
    dominate the score.

    Args:
        img_bgr: Full BGR image.
        face_bbox: Face ``(x, y, w, h)`` or None.
        inner_face_scale: Fraction ``(0,1]`` of the face box kept as the core ROI.
        fft_ring_inner: Inner radius (px) of the FFT magnitude ring (excluding DC).
        fft_ring_outer: Outer radius (px) of the FFT magnitude ring.
        fft_baseline: FFT peakiness offset before scaling to ``[0, 1]``.
        fft_scale: Divisor for FFT peakiness normalization.
        sobel_aniso_min: Sobel horizontal/vertical ratio offset.
        sobel_aniso_scale: Divisor for anisotropy normalization.
        min_laplacian_var: Minimum Laplacian variance on the resized patch;
            below this, the score is dampened (blur / noise).
        blur_dampen_factor: Multiplier applied when Laplacian variance is low.

    Returns:
        ``(score_0_1, diagnostic_tags)``.
    """
    if face_bbox is None:
        return 0.0, []

    inner = _inner_face_crop_bgr(img_bgr, face_bbox, inner_face_scale)
    if inner is None or inner.size < 120:
        return 0.0, []

    crop = inner
    if crop.size < 300 or crop.shape[0] < 12 or crop.shape[1] < 12:
        return 0.0, []

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    g = cv2.resize(gray, (128, 128), interpolation=cv2.INTER_AREA).astype(np.float32)
    std = float(g.std()) + 1e-6
    g = (g - float(g.mean())) / std

    f2 = np.fft.fftshift(np.fft.fft2(g))
    mag = np.abs(f2)
    h, w = mag.shape
    cy_i, cx_i = h // 2, w // 2
    yy, xx = np.ogrid[:h, :w]
    dist = np.sqrt((yy - cy_i) ** 2 + (xx - cx_i) ** 2)
    dc = dist < 3
    mag_m = mag.copy()
    mag_m[dc] = 0.0
    ring = (dist >= fft_ring_inner) & (dist <= fft_ring_outer)
    ring_values = np.log1p(mag_m[ring])
    ring_median = float(np.quantile(ring_values, 0.50))
    ring_high = float(np.quantile(ring_values, 0.90))
    ring_peak = float(np.quantile(ring_values, 0.98))
    fft_peakiness = max(
        0.0,
        (ring_peak - ring_high) / max(ring_median, 1e-6),
    )
    fft_score = min(1.0, max(0.0, (fft_peakiness - fft_baseline) / fft_scale))

    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    ex = float(np.mean(np.abs(gx))) + 1e-6
    ey = float(np.mean(np.abs(gy))) + 1e-6
    ratio = max(ex, ey) / min(ex, ey)
    aniso_score = min(1.0, max(0.0, (ratio - sobel_aniso_min) / sobel_aniso_scale))

    combined = max(0.0, min(fft_score, aniso_score))

    if lap_var < min_laplacian_var:
        combined *= blur_dampen_factor
        tags_blur = ["recapture_blur_dampened"]
    else:
        tags_blur = []

    tags: list[str] = []
    if fft_score >= 0.22:
        tags.append("recapture_fft_periodicity")
    if aniso_score >= 0.24:
        tags.append("recapture_gradient_aniso")
    if combined >= 0.22:
        tags.append("recapture_combined")
    tags.extend(tags_blur)
    return float(min(1.0, max(0.0, combined))), tags
