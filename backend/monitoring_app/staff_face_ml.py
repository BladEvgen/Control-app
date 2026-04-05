"""Face ML on-disk artifacts for Django admin (embeddings, checkpoints, augments).

Staff-specific files are stored next to the avatar (``dirname(avatar.path)``),
consistent with ``monitoring_app.ml``. Augment crops use ``settings.AUGMENT_ROOT``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, cast

from django.conf import settings
from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe


@dataclass(frozen=True)
class _FileInfo:
    """One logical file or folder row for the staff ML summary table."""

    label: str
    basename: str
    exists: bool
    size_bytes: int = 0
    mtime: Optional[datetime] = None
    detail: str = ""
    downloadable: bool = False


def staff_workspace_dir(staff) -> Optional[Path]:
    """Return the filesystem directory that holds the staff avatar (and ML sidecars).

    Args:
        staff: ``Staff`` instance with optional ``avatar``.

    Returns:
        Resolved parent of ``avatar.path`` if it exists, else ``None``.
    """
    avatar = getattr(staff, "avatar", None)
    if not avatar or not getattr(avatar, "path", None):
        return None
    try:
        p = Path(avatar.path).resolve().parent
    except Exception:
        return None
    return p if p.is_dir() else None


def augment_dir_for_pin(pin: str) -> Path:
    """Resolve the augment output directory for a PIN (``AUGMENT_ROOT`` template).

    Args:
        pin: Staff PIN substituted into ``AUGMENT_ROOT``.

    Returns:
        Absolute path to the augment directory.
    """
    root = str(settings.AUGMENT_ROOT).format(staff_pin=pin)
    return Path(root).expanduser().resolve()


def count_augment_images(pin: str) -> tuple[int, bool]:
    """Count augment image files for ``pin`` with expected filename prefixes.

    Args:
        pin: Staff PIN used in filenames (``{pin}_aug_*`` / legacy ``{pin}_augmented_*``).

    Returns:
        Tuple ``(count, dir_exists)`` where ``dir_exists`` means the augment folder is present.
    """
    d = augment_dir_for_pin(pin)
    if not d.is_dir():
        return 0, False
    n = 0
    for name in os.listdir(d):
        low = name.lower()
        if not low.endswith((".jpg", ".jpeg", ".png", ".webp")):
            continue
        if name.startswith(f"{pin}_aug_") or name.startswith(f"{pin}_augmented_"):
            n += 1
    return n, True


def _safe_mtime(path: Path) -> Optional[datetime]:
    """Return file/directory mtime or ``None`` on ``OSError``."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def _npy_shape_line(path: Path) -> str:
    """Human-readable shape line for a NumPy ``.npy`` file (mmap read)."""
    try:
        import numpy as np

        arr = np.load(str(path), mmap_mode="r")
        shp = arr.shape
        if len(shp) == 2:
            return f"векторов {shp[0]}, размерность {shp[1]}"
        return f"форма {shp}"
    except Exception as exc:
        return f"не читается: {exc}"


def allowed_ml_basenames(pin: str) -> frozenset[str]:
    """Basenames allowed for admin download/preview of staff ML files.

    Args:
        pin: Staff PIN embedded in filenames.

    Returns:
        Frozen set of whitelisted filenames next to the avatar.
    """
    return frozenset(
        {
            f"{pin}_embeddings.npy",
            f"{pin}_model.pt",
            f"{pin}_best_model.pt",
        }
    )


def allowed_augment_basename(pin: str, name: str) -> bool:
    """Return True if ``name`` is a safe augment image filename for ``pin``.

    Args:
        pin: Staff PIN prefix.
        name: Single path component (no slashes).

    Returns:
        ``True`` when the name matches augment conventions and image extension.
    """
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        return False
    low = name.lower()
    if not low.endswith((".jpg", ".jpeg", ".png", ".webp")):
        return False
    return name.startswith(f"{pin}_aug_") or name.startswith(f"{pin}_augmented_")


def list_augment_basenames(pin: str) -> list[str]:
    """Sorted list of augment image basenames under ``augment_dir_for_pin``."""
    d = augment_dir_for_pin(pin)
    if not d.is_dir():
        return []
    names: list[str] = []
    for fname in os.listdir(d):
        if allowed_augment_basename(pin, fname):
            names.append(fname)
    names.sort()
    return names


def media_url_for_file(path: Path) -> Optional[str]:
    """Public MEDIA URL for a file under ``MEDIA_ROOT``, if any.

    Args:
        path: Absolute file path.

    Returns:
        URL string or ``None`` if not under ``MEDIA_ROOT`` or not a file.
    """
    if not path.is_file():
        return None
    try:
        root = Path(settings.MEDIA_ROOT).resolve()
        rel = path.resolve().relative_to(root)
        base = str(settings.MEDIA_URL).rstrip("/")
        return f"{base}/{rel.as_posix()}"
    except Exception:
        return None


def collect_staff_face_ml_infos(staff) -> list[_FileInfo]:
    """Build table rows for embeddings, checkpoints, and augment folder summary.

    Args:
        staff: ``Staff`` instance.

    Returns:
        List of ``_FileInfo`` entries for admin display.
    """
    pin = staff.pin
    ws = staff_workspace_dir(staff)
    items: list[_FileInfo] = []

    def add_file(label: str, basename: str, *, npy_meta: bool = False) -> None:
        downloadable = basename in allowed_ml_basenames(pin)
        if ws is None:
            items.append(
                _FileInfo(label, basename, False, downloadable=downloadable)
            )
            return
        fp = ws / basename
        if not fp.is_file():
            items.append(
                _FileInfo(label, basename, False, downloadable=downloadable)
            )
            return
        st = fp.stat()
        detail = ""
        if npy_meta and basename.endswith(".npy"):
            detail = _npy_shape_line(fp)
        items.append(
            _FileInfo(
                label=label,
                basename=basename,
                exists=True,
                size_bytes=st.st_size,
                mtime=_safe_mtime(fp),
                detail=detail,
                downloadable=downloadable,
            )
        )

    add_file("Эмбеддинги галереи", f"{pin}_embeddings.npy", npy_meta=True)
    add_file("Чекпоинт обучения", f"{pin}_model.pt")
    add_file("Лучший чекпоинт", f"{pin}_best_model.pt")

    aug_n, aug_dir_exists = count_augment_images(pin)
    aug_path = augment_dir_for_pin(pin)
    mtime_aug = _safe_mtime(aug_path) if aug_dir_exists else None
    items.append(
        _FileInfo(
            label="Аугментации (счёт файлов)",
            basename=str(aug_path.name) + "/",
            exists=aug_dir_exists and aug_n > 0,
            size_bytes=0,
            mtime=mtime_aug,
            detail=f"{aug_n} файлов в {aug_path}" if aug_dir_exists else "каталога нет",
            downloadable=False,
        )
    )

    return items


def render_staff_face_ml_table(
    staff,
    *,
    file_download_url: Optional[str] = None,
    file_preview_url: Optional[str] = None,
    augment_gallery_url: Optional[str] = None,
) -> SafeString:
    """Render the readonly admin HTML table for staff ML artifacts.

    Args:
        staff: ``Staff`` instance.
        file_download_url: Base URL for ``?f=basename`` download (whitelisted files).
        file_preview_url: Base URL for HTML preview of ``.npy`` / ``.pt``.
        augment_gallery_url: URL opening the augment image gallery page.

    Returns:
        ``SafeString`` HTML fragment (Grappelli-compatible).
    """
    from urllib.parse import quote

    rows_html: list[str] = []
    pin = escape(staff.pin)
    ws = staff_workspace_dir(staff)
    ws_line = (
        f'<code style="font-size:11px;">{escape(str(ws))}</code>'
        if ws
        else '<span style="color:#94a3b8;">Нет аватара — каталог неизвестен</span>'
    )

    for info in collect_staff_face_ml_infos(staff):
        if info.exists:
            sz = info.size_bytes
            sz_s = (
                f"{sz / 1024 / 1024:.2f} MiB"
                if sz >= 1024 * 1024
                else f"{sz / 1024:.1f} KiB"
            )
            mt = (
                info.mtime.strftime("%Y-%m-%d %H:%M")
                if info.mtime
                else "—"
            )
            status = f'<span style="color:#15803d;font-weight:600;">есть</span> · {sz_s} · {mt}'
        else:
            status = '<span style="color:#b91c1c;">нет</span>'

        extra = ""
        if info.detail:
            extra = f'<div style="font-size:11px;color:#64748b;margin-top:2px;">{escape(info.detail)}</div>'

        link = ""
        if info.downloadable and file_download_url:
            q = quote(info.basename, safe="")
            href = f"{file_download_url}?f={q}"
            link = (
                f' <a href="{escape(href)}" style="font-size:12px;margin-left:6px;">'
                "скачать</a>"
            )
            if file_preview_url and info.basename.endswith((".npy", ".pt")):
                href_pv = f"{file_preview_url}?f={q}"
                link += (
                    f' <a href="{escape(href_pv)}" target="_blank" rel="noopener" '
                    f'style="font-size:12px;margin-left:6px;">просмотр</a>'
                )
        elif (
            info.exists
            and info.basename.endswith((".npy", ".pt"))
            and file_preview_url
        ):
            q = quote(info.basename, safe="")
            href_pv = f"{file_preview_url}?f={q}"
            link = (
                f' <a href="{escape(href_pv)}" target="_blank" rel="noopener" '
                f'style="font-size:12px;margin-left:6px;">просмотр</a>'
            )
        elif info.exists and info.basename.endswith((".npy", ".pt")):
            fp = (ws or Path()) / info.basename
            mu = media_url_for_file(fp)
            if mu:
                link = (
                    f' <a href="{escape(mu)}" target="_blank" rel="noopener" '
                    f'style="font-size:12px;margin-left:6px;">медиа</a>'
                )

        if (
            info.label.startswith("Аугментации")
            and info.exists
            and augment_gallery_url
        ):
            link += (
                f' <a href="{escape(augment_gallery_url)}" target="_blank" rel="noopener" '
                f'style="font-size:12px;margin-left:6px;">галерея</a>'
            )

        rows_html.append(
            "<tr>"
            f'<td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;white-space:nowrap;">'
            f"<strong>{escape(info.label)}</strong><br/>"
            f'<code style="font-size:10px;">{escape(info.basename)}</code></td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;">{status}{link}{extra}</td>'
            "</tr>"
        )

    table = (
        '<div class="grp-module" style="margin-bottom:12px;">'
        f'<p style="margin:0 0 8px 0;font-size:12px;color:#64748b;">PIN <strong>{pin}</strong> · {ws_line}</p>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        "<thead><tr>"
        '<th style="text-align:left;padding:8px 10px;background:#f8fafc;border-bottom:2px solid #e2e8f0;">'
        "Файл</th>"
        '<th style="text-align:left;padding:8px 10px;background:#f8fafc;border-bottom:2px solid #e2e8f0;">'
        "Статус</th>"
        "</tr></thead><tbody>"
        + "".join(rows_html)
        + "</tbody></table>"
        '<p style="margin:10px 0 0 0;font-size:11px;color:#94a3b8;">'
        "Эмбеддинги: больше строк — обычно богаче галерея (аугментации). Сравнивайте размер .npy и даты после "
        "переобучения. «Просмотр» — HTML-сводка (.npy) или описание чекпоинта (.pt); «Галерея» — картинки "
        "аугментаций (доступ только из админки). Скачивание .npy/.pt — только whitelisted имена из каталога сотрудника."
        "</p>"
        "</div>"
    )
    return cast(SafeString, mark_safe(table))


def face_ml_list_badge(staff) -> SafeString:
    """Compact colored badge for ``Staff`` changelist (emb/pt/best/aug counts).

    Args:
        staff: ``Staff`` instance.

    Returns:
        ``SafeString`` HTML span for ``list_display``.
    """
    ws = staff_workspace_dir(staff)
    pin = staff.pin
    emb = mask = best = False
    if ws:
        emb = (ws / f"{pin}_embeddings.npy").is_file()
        mask = (ws / f"{pin}_model.pt").is_file()
        best = (ws / f"{pin}_best_model.pt").is_file()
    n_aug, _ = count_augment_images(pin)

    parts = []
    parts.append(
        f'<span style="color:{"#16a34a" if emb else "#cbd5e1"};" title="embeddings.npy">emb</span>'
    )
    parts.append(
        f'<span style="color:{"#16a34a" if mask else "#cbd5e1"};" title="model.pt">pt</span>'
    )
    parts.append(
        f'<span style="color:{"#16a34a" if best else "#cbd5e1"};" title="best_model.pt">★</span>'
    )
    aug_color = "#16a34a" if n_aug >= 10 else ("#ca8a04" if n_aug else "#cbd5e1")
    parts.append(
        f'<span style="color:{aug_color};" title="аугментации">aug{n_aug}</span>'
    )
    html = (
        '<span style="font-size:11px;font-weight:600;letter-spacing:0.02em;">'
        + " ".join(parts)
        + "</span>"
    )
    return cast(SafeString, mark_safe(html))
