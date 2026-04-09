from __future__ import annotations

import logging
import os
import warnings


def ml_third_party_stdout_verbose() -> bool:
    """Return True when InsightFace/DeepFace stdout chatter should stay visible.

    Controlled by ``CELERY_ML_VERBOSE_LOGS`` so operators can match Celery worker
    and one-off management commands.

    Returns:
        True if verbose stdout is requested.
    """
    return os.getenv("CELERY_ML_VERBOSE_LOGS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "on",
    )


def apply_ml_third_party_log_quiet(*, verbose: bool = False) -> None:
    """Silence routine ML stack chatter for worker and batch processes.

    When ``verbose`` is True, this function does nothing so full library output
    remains available for debugging.

    Side effects:
        * Sets ``ORT_LOG_SEVERITY_LEVEL`` to ``3`` (error) if unset, reducing
          ONNX Runtime provider spam.
        * Raises log level for ``insightface`` and ``onnxruntime`` family loggers.
        * Registers ``warnings`` filters for known noisy ``FutureWarning`` /
          ``UserWarning`` paths in InsightFace and DeepFace FasNet.

    Args:
        verbose: If True, skip all adjustments.
    """
    if verbose:
        return

    os.environ.setdefault("ORT_LOG_SEVERITY_LEVEL", "3")

    for name in (
        "insightface",
        "onnxruntime",
        "onnxruntime.capi",
        "onnxruntime.capi.onnxruntime_pybind11_state",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)

    warnings.filterwarnings(
        "ignore",
        category=FutureWarning,
        module=r"insightface\.utils\.transform",
    )
    warnings.filterwarnings(
        "ignore",
        category=FutureWarning,
        module=r"deepface\.models\.spoofing\.FasNet",
    )
    warnings.filterwarnings(
        "ignore",
        category=UserWarning,
        module=r"deepface\.models\.spoofing\.FasNet",
    )
