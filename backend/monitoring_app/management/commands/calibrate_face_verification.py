from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Mapping
from itertools import combinations
from statistics import mean, median
from typing import Any, Optional, TypedDict, cast

import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from monitoring_app import face_parsing, ml, models


class ThresholdRow(TypedDict):
    threshold: float
    far: float | None
    frr: float | None
    false_accepts: int | None
    false_rejects: int | None


def _float_or_none(value: object) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _required_float(row: Mapping[str, object], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _required_int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _string_list_from_mapping(row: Mapping[str, object], key: str) -> list[str]:
    value = row.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _option_int(options: Mapping[str, Any], key: str, default: int) -> int:
    value = options.get(key, default)
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _option_float(options: Mapping[str, Any], key: str, default: float) -> float:
    value = options.get(key, default)
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _pct(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=np.float64), q))


def _describe(values: list[float]) -> dict[str, object]:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "min": round(min(values), 6),
        "p01": round(cast(float, _pct(values, 1)), 6),
        "p05": round(cast(float, _pct(values, 5)), 6),
        "p25": round(cast(float, _pct(values, 25)), 6),
        "median": round(median(values), 6),
        "mean": round(mean(values), 6),
        "p75": round(cast(float, _pct(values, 75)), 6),
        "p95": round(cast(float, _pct(values, 95)), 6),
        "p99": round(cast(float, _pct(values, 99)), 6),
        "max": round(max(values), 6),
    }


def _threshold_table(
    genuine_scores: list[float],
    impostor_scores: list[float],
    *,
    start: float,
    stop: float,
    step: float,
) -> list[ThresholdRow]:
    out: list[ThresholdRow] = []
    if step <= 0:
        step = 0.005
    thresholds = np.arange(start, stop + (step / 2), step, dtype=np.float64)
    gen = np.asarray(genuine_scores, dtype=np.float64)
    imp = np.asarray(impostor_scores, dtype=np.float64)
    for thr in thresholds:
        far = float(np.mean(imp >= thr)) if imp.size else None
        frr = float(np.mean(gen < thr)) if gen.size else None
        out.append(
            {
                "threshold": round(float(thr), 4),
                "far": None if far is None else round(far, 6),
                "frr": None if frr is None else round(frr, 6),
                "false_accepts": None if imp.size == 0 else int(np.sum(imp >= thr)),
                "false_rejects": None if gen.size == 0 else int(np.sum(gen < thr)),
            }
        )
    return out


def _recommend_thresholds(
    table: list[ThresholdRow],
    *,
    targets: list[float],
    min_threshold: float,
) -> dict[str, object]:
    recommendations: dict[str, object] = {}
    rows_with_both = [
        row for row in table if row["far"] is not None and row["frr"] is not None
    ]
    if rows_with_both:
        eer_row = min(
            rows_with_both,
            key=lambda row: abs(cast(float, row["far"]) - cast(float, row["frr"])),
        )
        recommendations["eer_like"] = eer_row

    for target in targets:
        eligible = [
            row
            for row in table
            if row["far"] is not None
            and row["far"] <= float(target)
            and row["threshold"] >= float(min_threshold)
        ]
        key = f"far_lte_{target:g}"
        if eligible:
            recommendations[key] = min(
                eligible,
                key=lambda row: (
                    row["frr"] if row["frr"] is not None else 1.0,
                    row["threshold"],
                ),
            )
        elif table:
            recommendations[key] = table[-1]
    return recommendations


def _staff_label(staff: "models.Staff") -> str:
    return " ".join(
        part
        for part in (str(getattr(staff, "surname", "") or ""), str(getattr(staff, "name", "") or ""))
        if part
    ).strip()


class Command(BaseCommand):
    help = (
        "Калибрует face verification на реальных эталонах: genuine/impostor пары, "
        "очки↔без очков, качество кадров и рекомендуемые пороги."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--pin", default="", help="Фокусный PIN для подробного отчёта."
        )
        parser.add_argument("--max-staff", type=int, default=250)
        parser.add_argument("--max-images-per-staff", type=int, default=6)
        parser.add_argument("--max-impostor-pairs", type=int, default=30000)
        parser.add_argument("--threshold-start", type=float, default=0.60)
        parser.add_argument("--threshold-stop", type=float, default=0.92)
        parser.add_argument("--threshold-step", type=float, default=0.005)
        parser.add_argument(
            "--min-recommend-threshold",
            type=float,
            default=0.72,
            help="Не рекомендовать рабочий порог ниже этого значения.",
        )
        parser.add_argument(
            "--target-far",
            default="0.001,0.005,0.01",
            help="Comma-separated FAR targets for threshold recommendation.",
        )
        parser.add_argument(
            "--output",
            default="",
            help=(
                "JSON output path. Default: "
                "GENERAL_MODELS_ROOT/face_verification_calibration.json"
            ),
        )

    def _image_sources_for_staff(
        self,
        staff: "models.Staff",
        *,
        max_images: int,
    ) -> list[dict[str, object]]:
        out: list[dict[str, object]] = []
        seen: set[str] = set()

        avatar = cast(Any, getattr(staff, "avatar", None))
        try:
            avatar_path = str(getattr(avatar, "path", "") or "")
        except (OSError, ValueError):
            avatar_path = ""
        if avatar_path and os.path.isfile(avatar_path):
            out.append({"path": avatar_path, "source": "avatar", "angle": "avatar"})
            seen.add(os.path.abspath(avatar_path))

        sample_qs = (
            cast(Any, models.StaffFaceSample)
            .objects.filter(staff=staff, is_active=True, is_trusted=True)
            .order_by("-created_at", "-id")
        )
        for sample in sample_qs.iterator(chunk_size=20):
            if len(out) >= max_images:
                break
            path = str(getattr(sample.image, "path", "") or "")
            if not path or not os.path.isfile(path):
                continue
            ap = os.path.abspath(path)
            if ap in seen:
                continue
            seen.add(ap)
            out.append(
                {
                    "path": path,
                    "source": "staff_face_sample",
                    "angle": str(sample.angle or ""),
                    "with_glasses_db": bool(sample.with_glasses),
                    "probe_eyeglasses_likely_db": sample.probe_eyeglasses_likely,
                }
            )
        return out[:max_images]

    def _embedding_record(
        self,
        *,
        staff: "models.Staff",
        source: dict[str, object],
    ) -> Optional[dict[str, object]]:
        path = str(source.get("path") or "")
        image = ml.imread_bgr(path)
        if image is None:
            return None
        image = ml.preprocess_image(image)
        embedding, meta = ml.create_face_encoding_with_probe_meta(image, use_tta=True)
        if embedding is None:
            return None
        row = np.asarray(embedding, dtype=np.float64).reshape(-1)
        norm = float(np.linalg.norm(row))
        if norm < 1e-10:
            return None
        parsing = face_parsing.probe_bgr(image)
        glasses = parsing.get("eyeglasses_likely")
        return {
            "staff_pk": int(staff.pk),
            "pin": str(staff.pin),
            "label": _staff_label(staff),
            "path": path,
            "source": str(source.get("source") or ""),
            "angle": str(source.get("angle") or ""),
            "embedding": row / norm,
            "quality_pass": bool(meta.get("quality_pass")),
            "quality_reason_codes": _string_list_from_mapping(
                meta,
                "quality_reason_codes",
            ),
            "det_score": _float_or_none(meta.get("det_score")),
            "face_area_ratio": _float_or_none(meta.get("face_area_ratio")),
            "blur_laplacian_var": _float_or_none(meta.get("blur_laplacian_var")),
            "brightness_mean": _float_or_none(meta.get("brightness_mean")),
            "pose_yaw": _float_or_none(meta.get("pose_yaw")),
            "pose_pitch": _float_or_none(meta.get("pose_pitch")),
            "eyeglasses_likely": glasses if isinstance(glasses, bool) else None,
            "eyeglasses_area_frac": _float_or_none(parsing.get("eyeglasses_area_frac")),
        }

    def _mask_embedding_records(
        self,
        staff: "models.Staff",
        *,
        cap: int,
    ) -> list[dict[str, object]]:
        if cap <= 0:
            return []
        try:
            fm = cast(Any, getattr(staff, "face_mask", None))
            matrix = ml._mask_json_to_matrix(getattr(fm, "mask_encoding", None))
        except Exception:
            matrix = None
        if matrix is None or matrix.size == 0:
            return []
        rows = ml._l2_normalize_embedding_rows(matrix)
        out: list[dict[str, object]] = []
        for idx in range(min(cap, int(rows.shape[0]))):
            out.append(
                {
                    "staff_pk": int(staff.pk),
                    "pin": str(staff.pin),
                    "label": _staff_label(staff),
                    "path": "",
                    "source": "face_mask",
                    "angle": f"mask_{idx}",
                    "embedding": rows[idx],
                    "quality_pass": True,
                    "quality_reason_codes": [],
                    "det_score": None,
                    "face_area_ratio": None,
                    "blur_laplacian_var": None,
                    "brightness_mean": None,
                    "pose_yaw": None,
                    "pose_pitch": None,
                    "eyeglasses_likely": None,
                    "eyeglasses_area_frac": None,
                }
            )
        return out

    def handle(self, *args, **options):
        opt = cast(Mapping[str, Any], options)
        pin_filter = str(opt.get("pin") or "").strip()
        max_staff = max(1, _option_int(opt, "max_staff", 250))
        max_images = max(1, _option_int(opt, "max_images_per_staff", 6))
        max_impostor_pairs = max(1, _option_int(opt, "max_impostor_pairs", 30000))
        targets = [
            float(x)
            for x in str(options.get("target_far") or "").split(",")
            if x.strip()
        ]
        output = str(opt.get("output") or "").strip()
        if not output:
            output = os.path.join(
                str(settings.GENERAL_MODELS_ROOT),
                "face_verification_calibration.json",
            )

        ml.load_arcface_model()

        staff_manager = cast(Any, models.Staff).objects
        qs = (
            staff_manager.filter(
                Q(face_mask__isnull=False) | (Q(avatar__isnull=False) & ~Q(avatar=""))
            )
            .order_by("pin")
            .select_related("department", "face_mask")
        )
        if pin_filter:
            focused = list(qs.filter(pin=pin_filter)[:1])
            others = list(qs.exclude(pin=pin_filter)[: max_staff - len(focused)])
            staff_rows = focused + others
        else:
            staff_rows = list(qs[:max_staff])

        records: list[dict[str, object]] = []
        skipped_by_reason: Counter[str] = Counter()
        for staff in staff_rows:
            records.extend(
                self._mask_embedding_records(
                    staff,
                    cap=min(2, max_images),
                )
            )
            sources = self._image_sources_for_staff(staff, max_images=max_images)
            if not sources:
                if not any(r.get("pin") == str(staff.pin) for r in records):
                    skipped_by_reason["no_sources"] += 1
                continue
            for source in sources:
                rec = self._embedding_record(staff=staff, source=source)
                if rec is None:
                    skipped_by_reason["embedding_failed"] += 1
                    continue
                records.append(rec)

        by_staff: dict[int, list[dict[str, object]]] = {}
        for rec in records:
            by_staff.setdefault(_required_int(rec, "staff_pk"), []).append(rec)

        genuine: list[dict[str, object]] = []
        for staff_records in by_staff.values():
            if len(staff_records) < 2:
                continue
            for a, b in combinations(staff_records, 2):
                score = float(
                    cast(np.ndarray, a["embedding"])
                    @ cast(np.ndarray, b["embedding"])
                )
                genuine.append(
                    {
                        "score": score,
                        "pin": a["pin"],
                        "glasses_pair": (
                            "mixed"
                            if a.get("eyeglasses_likely") != b.get("eyeglasses_likely")
                            else str(a.get("eyeglasses_likely"))
                        ),
                    }
                )

        impostor: list[dict[str, object]] = []
        staff_items = list(by_staff.items())
        for i, (_pk_a, rows_a) in enumerate(staff_items):
            if len(impostor) >= max_impostor_pairs:
                break
            for _pk_b, rows_b in staff_items[i + 1 :]:
                if len(impostor) >= max_impostor_pairs:
                    break
                for a in rows_a:
                    if len(impostor) >= max_impostor_pairs:
                        break
                    for b in rows_b:
                        score = float(
                            cast(np.ndarray, a["embedding"])
                            @ cast(np.ndarray, b["embedding"])
                        )
                        impostor.append(
                            {
                                "score": score,
                                "pin_a": a["pin"],
                                "pin_b": b["pin"],
                            }
                        )
                        if len(impostor) >= max_impostor_pairs:
                            break

        genuine_scores = [_required_float(x, "score") for x in genuine]
        impostor_scores = [_required_float(x, "score") for x in impostor]
        table = _threshold_table(
            genuine_scores,
            impostor_scores,
            start=_option_float(opt, "threshold_start", 0.60),
            stop=_option_float(opt, "threshold_stop", 0.92),
            step=_option_float(opt, "threshold_step", 0.005),
        )

        focus_report: dict[str, object] = {}
        if pin_filter:
            focus_records = [r for r in records if r["pin"] == pin_filter]
            focus_scores = [x for x in genuine if x["pin"] == pin_filter]
            focus_impostors = sorted(
                [
                    x
                    for x in impostor
                    if x.get("pin_a") == pin_filter or x.get("pin_b") == pin_filter
                ],
                key=lambda row: _required_float(row, "score"),
                reverse=True,
            )[:10]
            focus_report = {
                "pin": pin_filter,
                "image_count": len(focus_records),
                "runtime_gallery": {},
                "images": [
                    {
                        key: value
                        for key, value in rec.items()
                        if key not in {"embedding"}
                    }
                    for rec in focus_records
                ],
                "genuine_scores": _describe(
                    [_required_float(x, "score") for x in focus_scores]
                ),
                "nearest_impostors": focus_impostors,
            }
            if focus_records:
                staff = (
                    cast(Any, models.Staff)
                    .objects.filter(pin=pin_filter)
                    .first()
                )
                if staff is not None:
                    rich, rich_bd = ml.build_runtime_gallery_embeddings(
                        staff,
                        rich_variants=True,
                    )
                    lean, lean_bd = ml.build_runtime_gallery_embeddings(
                        staff,
                        rich_variants=False,
                    )
                    focus_report["runtime_gallery"] = {
                        "rich_shape": None if rich is None else list(rich.shape),
                        "rich_breakdown": rich_bd,
                        "lean_shape": None if lean is None else list(lean.shape),
                        "lean_breakdown": lean_bd,
                    }

        quality_reasons: Counter[str] = Counter()
        for rec in records:
            for reason in _string_list_from_mapping(rec, "quality_reason_codes"):
                quality_reasons[str(reason)] += 1

        result: dict[str, object] = {
            "version": "face_verify_calibration_v1",
            "inputs": {
                "staff_count": len(staff_rows),
                "embedding_records": len(records),
                "max_images_per_staff": max_images,
                "max_impostor_pairs": max_impostor_pairs,
                "pin_filter": pin_filter or None,
            },
            "skipped_by_reason": dict(skipped_by_reason),
            "quality": {
                "quality_pass_count": sum(1 for r in records if r.get("quality_pass")),
                "quality_fail_count": sum(1 for r in records if not r.get("quality_pass")),
                "quality_reasons": dict(quality_reasons),
                "blur": _describe(
                    [
                        _required_float(r, "blur_laplacian_var")
                        for r in records
                        if isinstance(r.get("blur_laplacian_var"), (int, float))
                    ]
                ),
                "face_area": _describe(
                    [
                        _required_float(r, "face_area_ratio")
                        for r in records
                        if isinstance(r.get("face_area_ratio"), (int, float))
                    ]
                ),
            },
            "glasses": dict(Counter(str(r.get("eyeglasses_likely")) for r in records)),
            "genuine": {
                "overall": _describe(genuine_scores),
                "same_glasses": _describe(
                    [
                        _required_float(x, "score")
                        for x in genuine
                        if x.get("glasses_pair") != "mixed"
                    ]
                ),
                "mixed_glasses": _describe(
                    [
                        _required_float(x, "score")
                        for x in genuine
                        if x.get("glasses_pair") == "mixed"
                    ]
                ),
            },
            "impostor": {
                "overall": _describe(impostor_scores),
                "top10": sorted(
                    impostor,
                    key=lambda row: _required_float(row, "score"),
                    reverse=True,
                )[:10],
            },
            "threshold_table": table,
            "recommendations": _recommend_thresholds(
                table,
                targets=targets,
                min_threshold=_option_float(opt, "min_recommend_threshold", 0.72),
            ),
            "focus": focus_report,
        }

        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)

        genuine_summary = cast(dict[str, object], cast(dict[str, object], result["genuine"])["overall"])
        impostor_summary = cast(dict[str, object], cast(dict[str, object], result["impostor"])["overall"])
        recommendations = result["recommendations"]
        self.stdout.write(
            f"records={len(records)} genuine={len(genuine)} impostor={len(impostor)}"
        )
        self.stdout.write(f"genuine={genuine_summary}")
        self.stdout.write(f"impostor={impostor_summary}")
        self.stdout.write(
            f"recommendations={json.dumps(recommendations, ensure_ascii=False)}"
        )
        if focus_report:
            self.stdout.write(
                f"focus={json.dumps(focus_report, ensure_ascii=False)[:4000]}"
            )
        self.stdout.write(f"saved={output}")
