from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)

GROUPS = ("false_clean", "false_suspicious", "true_clean", "true_suspicious")


class Command(BaseCommand):
    help = "Run PAD (photo_pad.check_photo) on labeled image groups and print a summary table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--audit-synthetic",
            action="store_true",
            help=(
                "Run fixed synthetic _decide scenarios (see pad_synthetic_audit); "
                "prints per-scenario status, branch, and review-rate summary (no images)."
            ),
        )
        parser.add_argument(
            "--manifest",
            type=str,
            default=None,
            help="Path to JSON file with keys false_clean, false_suspicious, true_clean, true_suspicious (lists of paths).",
        )
        parser.add_argument(
            "--device",
            choices=("auto", "cpu", "cuda"),
            default="auto",
            help="Torch device hint for Faster R-CNN device detector.",
        )

    def handle(self, *args: Any, **options: Any):
        from monitoring_app.pad_synthetic_audit import (
            SYNTHETIC_REVIEW_RATE_AUDIT_SCENARIOS,
        )
        from monitoring_app.photo_pad import (
            PAD_MODEL_VERSION,
            STATUS_REVIEW,
            _decide,
            check_photo,
            normalize_device,
        )

        if options.get("audit_synthetic"):
            self.stdout.write(
                "Synthetic PAD review-rate audit (monitoring_app.pad_synthetic_audit)\n"
            )
            status_hist: dict[str, int] = {}
            branch_hist: dict[str, int] = {}
            review_n = 0
            for label, inp in SYNTHETIC_REVIEW_RATE_AUDIT_SCENARIOS:
                r = _decide(inp)
                status_hist[r.status] = status_hist.get(r.status, 0) + 1
                if r.status == STATUS_REVIEW:
                    review_n += 1
                branch = ""
                for t in r.tags:
                    if isinstance(t, str) and t.startswith("pad_rule:"):
                        branch = t[len("pad_rule:") :]
                        break
                branch_hist[branch or "(none)"] = (
                    branch_hist.get(branch or "(none)", 0) + 1
                )
                self.stdout.write(
                    f"{label}\t{r.status}\t{branch}\ttrust={r.trust_confirmed!r}"
                )
            total = len(SYNTHETIC_REVIEW_RATE_AUDIT_SCENARIOS)
            self.stdout.write(
                f"\n--- synthetic summary (n={total}) ---\n"
                f"status_counts: {status_hist!s}\n"
                f"review_rate: {review_n / total:.3f}\n"
                f"branch_histogram: {branch_hist!s}\n"
            )
            return

        manifest_opt = options.get("manifest")
        if not manifest_opt:
            raise CommandError("Provide --manifest or use --audit-synthetic")

        manifest_path = Path(manifest_opt).expanduser()
        if not manifest_path.is_file():
            raise CommandError(f"Manifest not found: {manifest_path}")

        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise CommandError("Manifest root must be a JSON object")

        resolved = normalize_device(options["device"])
        self.stdout.write(
            f"PAD_MODEL_VERSION={PAD_MODEL_VERSION} device={resolved} "
            f"manifest={manifest_path}\n"
            "(pad_struct:* tags carry JSON decision traces when using pad_v5+.)\n"
        )

        rows: list[tuple[str, str, str, float, str]] = []
        for group in GROUPS:
            paths = raw.get(group) or []
            if not isinstance(paths, list):
                raise CommandError(f"Manifest key {group!r} must be a list")
            for p in paths:
                path_str = str(p).strip()
                if not path_str:
                    continue
                pth = Path(path_str).expanduser()
                if not pth.is_file():
                    self.stdout.write(
                        self.style.WARNING(
                            f"skip missing file group={group} path={pth}"
                        )
                    )
                    continue
                try:
                    result = check_photo(str(pth), device=resolved)
                except Exception as exc:
                    logger.exception("evaluate_photo_pad failed path=%s", pth)
                    rows.append((group, str(pth), "error", 0.0, f"exception:{exc}"))
                    continue
                tag_summary = ",".join(result.tags[:8])
                if len(result.tags) > 8:
                    tag_summary += ",..."
                rows.append(
                    (
                        group,
                        str(pth),
                        result.status,
                        result.risk_score,
                        tag_summary,
                    )
                )

        summary: dict[str, dict[str, int]] = {g: {} for g in GROUPS}
        for group, _path, st, _risk, _tags in rows:
            summary[group][st] = summary[group].get(st, 0) + 1

        self.stdout.write("\n--- per-group status counts ---")
        for group in GROUPS:
            self.stdout.write(f"{group}: {summary[group]!s}")

        self.stdout.write("\n--- per-image ---")
        for group, path, st, risk, tags in rows:
            self.stdout.write(f"{group}\t{st}\t{risk:.3f}\t{path}\t{tags}")
