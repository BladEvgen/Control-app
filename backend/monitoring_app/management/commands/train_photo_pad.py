"""Train the photo PAD head on operator verdicts.

Labels, strongest first:
  * ``models/pad_labels.json`` — {"<attendance id>": 0|1} reviewed by hand;
  * operator manual verdicts on ``LessonAttendance`` (clean=0, suspicious=1);
  * unreviewed auto-``clean`` rows as low-weight negatives.

Photos are deleted after ~31 days, so every embedding is cached in
``models/pad_clip_embeddings.npz`` and old labels keep training the model.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand

from monitoring_app import models
from monitoring_app.photo_pad import (
    EMBED_DIM,
    MANUAL_NONE,
    embed_bgr_batch,
    head_path,
    load_head,
    verdict_from_probability,
)

WEAK_NEGATIVE_WEIGHT = 0.2
C_REG = 0.03
TARGET_PRECISION = 0.97
REVIEW_BUDGET = 0.005


def models_dir() -> Path:
    return Path(settings.BASE_DIR) / "models"


def load_cache(path: Path) -> dict[int, np.ndarray]:
    if not path.is_file():
        return {}
    data = np.load(path)
    if data["emb"].shape[1:] != (EMBED_DIM,):
        return {}
    return {int(i): e for i, e in zip(data["ids"], data["emb"])}


def save_cache(path: Path, cache: dict[int, np.ndarray]) -> None:
    ids = np.array(sorted(cache), dtype=np.int64)
    emb = (
        np.stack([cache[i] for i in ids]).astype(np.float16)
        if len(ids)
        else np.zeros((0, EMBED_DIM), np.float16)
    )
    np.savez(path, ids=ids, emb=emb)


def fit_head(X: np.ndarray, y: np.ndarray, w: np.ndarray) -> tuple[Any, Any]:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(X)
    lr = LogisticRegression(C=C_REG, class_weight="balanced", max_iter=5000)
    return scaler, lr.fit(scaler.transform(X), y, sample_weight=w)


def pick_thresholds(p: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """``t_suspicious``: lowest cut whose auto-"suspicious" precision >= target.
    ``t_clean``: highest cut keeping the manual-review band within REVIEW_BUDGET."""
    order = np.argsort(-p)
    tp = np.cumsum(y[order] == 1)
    precision = tp / np.arange(1, len(p) + 1)
    ok = np.where((precision >= TARGET_PRECISION) & (y[order] == 1))[0]
    t_susp = float(p[order][ok.max()]) if len(ok) else 0.99
    below = np.sort(p[p < t_susp])
    k = max(0, len(below) - int(REVIEW_BUDGET * len(p)) - 1)
    t_clean = min(float(below[k]) if len(below) else 0.0, t_susp - 1e-3)
    return t_clean, t_susp


class Command(BaseCommand):
    help = "Train the CLIP-based photo PAD head from operator verdicts and write models/pad_clip_head.json."

    def add_arguments(self, parser):
        parser.add_argument("--weak-negatives", type=int, default=20000)
        parser.add_argument("--batch", type=int, default=32)
        parser.add_argument(
            "--dry-run", action="store_true", help="Print metrics, do not write the head."
        )

    def handle(self, *args: Any, **opts: Any):
        from sklearn.model_selection import StratifiedKFold

        la = models.LessonAttendance
        labels_path = models_dir() / "pad_labels.json"
        cache_path = models_dir() / "pad_clip_embeddings.npz"
        hand = (
            {int(k): int(v) for k, v in json.loads(labels_path.read_text()).items()}
            if labels_path.is_file()
            else {}
        )

        labels: dict[int, tuple[int, float]] = {}
        manual = la.objects.exclude(photo_manual_verdict=la.PHOTO_MANUAL_VERDICT_NONE)
        for pk, verdict in manual.values_list("id", "photo_manual_verdict"):
            labels[pk] = (int(verdict == la.PHOTO_MANUAL_VERDICT_SUSPICIOUS), 1.0)
        labels.update({pk: (y, 1.0) for pk, y in hand.items()})

        cache = load_cache(cache_path)
        weak = (
            la.objects.filter(
                photo_manual_verdict=la.PHOTO_MANUAL_VERDICT_NONE,
                photo_spoof_status=la.PHOTO_SPOOF_STATUS_CLEAN,
            )
            .exclude(id__in=list(hand))
            .order_by("-date_at", "-id")
            .values_list("id", flat=True)[: opts["weak_negatives"]]
        )
        for pk in weak:
            labels[pk] = (0, WEAK_NEGATIVE_WEIGHT)

        paths = dict(
            la.objects.filter(id__in=[pk for pk in labels if pk not in cache]).values_list(
                "id", "staff_image_path"
            )
        )
        todo = [(pk, p) for pk, p in paths.items() if p and os.path.isfile(p)]
        self.stdout.write(f"labels={len(labels)} cached={len(cache)} to_embed={len(todo)}")
        for i in range(0, len(todo), opts["batch"]):
            chunk = [(pk, cv2.imread(p)) for pk, p in todo[i : i + opts["batch"]]]
            chunk = [(pk, img) for pk, img in chunk if img is not None]
            if chunk:
                for (pk, _), e in zip(chunk, embed_bgr_batch([img for _, img in chunk])):
                    cache[pk] = e
            if i and i % (opts["batch"] * 20) == 0:
                save_cache(cache_path, cache)
                self.stdout.write(f"  embedded {i}/{len(todo)}")
        save_cache(cache_path, cache)

        ids = [pk for pk in labels if pk in cache]
        X = np.stack([cache[pk] for pk in ids]).astype(np.float32)
        y = np.array([labels[pk][0] for pk in ids])
        w = np.array([labels[pk][1] for pk in ids])
        n_pos = int(y.sum())
        self.stdout.write(f"train rows={len(ids)} spoof={n_pos} live={len(ids) - n_pos}")

        folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
        p_cv = np.zeros(len(y))
        for tr, te in folds.split(X, y):
            scaler, lr = fit_head(X[tr], y[tr], w[tr])
            p_cv[te] = lr.predict_proba(scaler.transform(X[te]))[:, 1]
        t_clean, t_susp = pick_thresholds(p_cv, y)

        strong = w >= 1
        for name, mask in (("all", np.ones_like(strong)), ("hand+operator", strong)):
            yy, pp = y[mask], p_cv[mask]
            self.stdout.write(
                f"[cv {name}] spoof->suspicious {np.mean(pp[yy == 1] >= t_susp):.3f}"
                f" spoof->review {np.mean((pp[yy == 1] > t_clean) & (pp[yy == 1] < t_susp)):.3f}"
                f" spoof->clean {np.mean(pp[yy == 1] <= t_clean):.3f} |"
                f" live->clean {np.mean(pp[yy == 0] <= t_clean):.3f}"
                f" live->review {np.mean((pp[yy == 0] > t_clean) & (pp[yy == 0] < t_susp)):.3f}"
                f" live->suspicious {np.mean(pp[yy == 0] >= t_susp):.3f}"
            )
        self.stdout.write(f"t_clean={t_clean:.4f} t_suspicious={t_susp:.4f}")
        if opts["dry_run"]:
            return

        scaler, lr = fit_head(X, y, w)
        head = {
            "arch": "ViT-L-14/openai",
            "coef": [round(float(c), 6) for c in np.asarray(lr.coef_)[0]],
            "intercept": float(np.asarray(lr.intercept_)[0]),
            "mean": [round(float(v), 6) for v in scaler.mean_],
            "scale": [round(float(v), 6) for v in scaler.scale_],
            "t_clean": round(t_clean, 4),
            "t_suspicious": round(t_susp, 4),
            "trained_at": datetime.now().isoformat(timespec="seconds"),
            "n_spoof": n_pos,
            "n_live": len(ids) - n_pos,
        }
        head_path().write_text(json.dumps(head))
        self.stdout.write(self.style.SUCCESS(f"wrote {head_path()}"))
        self.stdout.write(f"rescored {rescore_cached(cache)} auto verdicts from cached embeddings")


def rescore_cached(cache: dict[int, np.ndarray]) -> int:
    """Re-apply the fresh head to every cached photo without an operator verdict.

    Runs on cached embeddings, so it is seconds instead of hours and also covers
    rows whose photo file is already gone. Operator verdicts are never touched.
    """
    la = models.LessonAttendance
    head = load_head()
    judged = set(la.objects.exclude(photo_manual_verdict=MANUAL_NONE).values_list("id", flat=True))
    rows = [la(id=pk) for pk in sorted(cache) if pk not in judged]
    if not rows:
        return 0
    X = (np.stack([cache[r.id] for r in rows]).astype(np.float32) - head["_mean"]) / head["_scale"]
    probs = 1.0 / (1.0 + np.exp(-(X @ head["_coef"] + float(head["intercept"]))))
    for row, p in zip(rows, probs):
        for field, value in verdict_from_probability(float(p), head).to_update_kwargs().items():
            setattr(row, field, value)
    fields = list(verdict_from_probability(0.0, head).to_update_kwargs())
    la.objects.bulk_update(rows, fields, batch_size=500)
    return len(rows)
