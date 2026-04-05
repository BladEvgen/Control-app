"""HTML fragments and matplotlib figures for staff ML file preview in Django admin.

Builds layperson-friendly explanations plus optional developer ``<details>`` blocks.
"""
from __future__ import annotations

import base64
import io
from pathlib import Path

from django.utils.html import escape


def _figure_to_data_uri(fig) -> str:
    """Serialize a matplotlib figure to a PNG ``data:image/png;base64,...`` URI.

    Args:
        fig: Matplotlib figure.

    Returns:
        Data URI suitable for embedding in ``<img src="...">``.
    """
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor="#fafafa")
    plt.close(fig)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")


def _technical_block(title: str, content: str) -> str:
    """Wrap escaped text in a collapsible HTML ``<details>`` block.

    Args:
        title: Summary line (shown to the user).
        content: Raw text placed inside ``<pre>`` (HTML-escaped).

    Returns:
        HTML string.
    """
    safe = escape(content)
    return (
        f'<details style="margin-top:16px;border:1px solid #e2e8f0;border-radius:8px;padding:8px 12px;background:#fff;">'
        f'<summary style="cursor:pointer;font-size:13px;color:#475569;">{escape(title)}</summary>'
        f'<pre style="margin:10px 0 0 0;font-size:11px;overflow:auto;background:#0f172a;color:#e2e8f0;padding:10px;border-radius:6px;">{safe}</pre>'
        "</details>"
    )


def build_npy_embeddings_preview_body(path: Path, fname: str) -> str:
    """Build HTML body for embedding matrix preview (heatmap + PCA scatter).

    Args:
        path: Absolute path to ``*_embeddings.npy``.
        fname: Display basename (escaped internally where needed).

    Returns:
        HTML fragment (no ``<html>`` wrapper).
    """
    import numpy as np

    fname_e = escape(fname)
    arr = np.load(str(path), mmap_mode="r")
    parts: list[str] = []

    parts.append(
        '<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:14px 16px;margin-bottom:16px;">'
        "<p style=\"margin:0 0 8px 0;font-size:15px;font-weight:600;color:#1e3a8a;\">Что вы видите</p>"
        "<p style=\"margin:0;font-size:14px;line-height:1.5;color:#1e293b;\">"
        "Это <strong>не фотография</strong>, а сохранённые <strong>числовые «отпечатки» лица</strong> для системы доступа. "
        "Каждая <strong>строка</strong> — один вариант лица (фото или аугментация); в каждой строке <strong>много чисел</strong> "
        "(обычно 512) — так модель описывает черты лица. Ниже — наглядная «карта» этих чисел и схема, насколько варианты похожи друг на друга."
        "</p></div>"
    )

    if arr.ndim != 2:
        parts.append(
            f"<p><strong>{fname_e}</strong> — массив формы <code>{escape(str(arr.shape))}</code> "
            "(ожидалась таблица «варианты × признаки»).</p>"
        )
        parts.append(
            _technical_block(
                "Технические детали",
                f"dtype: {arr.dtype}\nrepr: {arr!r}"[:2000],
            )
        )
        return "".join(parts)

    n, d = int(arr.shape[0]), int(arr.shape[1])
    parts.append(
        f'<p style="font-size:14px;color:#334155;"><strong>Файл:</strong> {fname_e}<br/>'
        f"<strong>В галерее вариантов:</strong> {n} · <strong>Чисел на один вариант:</strong> {d}</p>"
    )

    chart_html = ""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        data = np.asarray(arr, dtype=np.float32)
        lim = float(np.nanpercentile(np.abs(data), 98)) or 1.0

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 7.2), height_ratios=[1.35, 1.0])
        im = ax1.imshow(data, aspect="auto", cmap="RdBu_r", vmin=-lim, vmax=lim)
        ax1.set_title("Карта значений (тёмное/светлое — разные признаки лица)", fontsize=11)
        ax1.set_ylabel("Варианты в галерее (сверху вниз)")
        ax1.set_xlabel("Номер признака (упорядочены, как выдал нейросеть)")
        fig.colorbar(im, ax=ax1, fraction=0.035, pad=0.02, label="Значение")

        ax2.set_title("Насколько варианты похожи между собой (2D-упрощение)", fontsize=11)
        if n >= 2:
            X = np.asarray(arr, dtype=np.float64)
            from sklearn.decomposition import PCA

            k = min(2, n - 1, X.shape[1])
            if k >= 2:
                xy = PCA(n_components=2).fit_transform(X)
            else:
                pca1 = PCA(n_components=1).fit_transform(X).ravel()
                xy = np.column_stack([pca1, np.zeros_like(pca1)])
            ax2.scatter(
                xy[:, 0],
                xy[:, 1],
                c=np.arange(n),
                cmap="tab20",
                alpha=0.85,
                edgecolors="white",
                linewidths=0.6,
                s=55,
            )
            ax2.set_xlabel("Направление А")
            ax2.set_ylabel("Направление Б")
            ax2.grid(True, alpha=0.25)
        else:
            ax2.text(0.5, 0.5, "Нужно минимум 2 варианта", ha="center", va="center")
            ax2.axis("off")

        fig.suptitle("Галерея лиц в виде чисел", fontsize=12, y=1.02)
        uri = _figure_to_data_uri(fig)
        chart_html = (
            f'<figure style="margin:12px 0;"><img src="{uri}" alt="" '
            'style="max-width:100%;height:auto;border:1px solid #e2e8f0;border-radius:10px;background:#fff;"/>'
            '<figcaption style="font-size:12px;color:#64748b;margin-top:8px;">'
            "Верхняя картинка — как «штрих-код» признаков; ниже — если точки близко, модель считает эти варианты похожими."
            "</figcaption></figure>"
        )
    except Exception as exc:
        chart_html = (
            f'<p style="color:#b45309;font-size:13px;">График временно недоступен ({escape(str(exc))}). '
            "Числа в файле на месте — можно скачать .npy.</p>"
        )

    parts.append(chart_html)

    try:
        rn, cm = min(6, n), min(10, d)
        block = np.asarray(arr[:rn, :cm])
        sample = np.array2string(
            block,
            precision=4,
            suppress_small=True,
            max_line_width=100,
        )
        parts.append(
            _technical_block(
                "Сырые числа (фрагмент, для специалистов)",
                sample,
            )
        )
    except Exception:
        pass

    return "".join(parts)


def build_pt_checkpoint_preview_body(path: Path, fname: str, download_url: str) -> str:
    """Build HTML body for a PyTorch ``state_dict`` checkpoint overview.

    Args:
        path: Absolute path to ``.pt`` file.
        fname: Display basename.
        download_url: Absolute or relative URL to download the same file.

    Returns:
        HTML fragment (no ``<html>`` wrapper).
    """
    fname_e = escape(fname)
    dl_e = escape(download_url)

    parts: list[str] = []
    parts.append(
        '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:14px 16px;margin-bottom:16px;">'
        "<p style=\"margin:0 0 8px 0;font-size:15px;font-weight:600;color:#14532d;\">Что это за файл</p>"
        "<p style=\"margin:0;font-size:14px;line-height:1.5;color:#1e293b;\">"
        "Это <strong>сохранённые настройки нейросети</strong> после обучения: коэффициенты («веса»), которые переводят "
        "512 чисел эмбеддинга в решение «похоже на этого сотрудника / нет». "
        "<strong>Это не изображение</strong> и не фото — открыть «как картинку» нельзя; ниже — схема, сколько чисел в каждом блоке модели."
        "</p></div>"
    )

    tech_lines: list[str] = []
    chart_html = ""

    try:
        import torch

        try:
            sd = torch.load(str(path), map_location="cpu", weights_only=True)
        except TypeError:
            sd = torch.load(str(path), map_location="cpu")

        if not isinstance(sd, dict):
            parts.append(
                f"<p><strong>{fname_e}</strong> — внутри не словарь весов PyTorch, а <code>{escape(type(sd).__name__)}</code>.</p>"
            )
        else:
            rows: list[tuple[str, int, tuple[int, ...]]] = []
            total = 0
            for k, v in sd.items():
                if hasattr(v, "numel") and hasattr(v, "shape"):
                    ne = int(v.numel())
                    total += ne
                    shp = tuple(int(x) for x in v.shape)
                    rows.append((k, ne, shp))
            rows.sort(key=lambda x: -x[1])
            tech_lines.append(f"Блоков (тензоров): {len(rows)}")
            tech_lines.append(f"Всего обучаемых чисел (параметров): {total:,}".replace(",", " "))
            for name, ne, shp in rows[:25]:
                tech_lines.append(f"  {name}: {ne:,} чисел, форма {shp}".replace(",", " "))
            if len(rows) > 25:
                tech_lines.append(f"  … ещё {len(rows) - 25} блоков")

            parts.append(
                f'<p style="font-size:14px;color:#334155;"><strong>Файл:</strong> {fname_e}<br/>'
                f"<strong>Всего чисел в модели:</strong> {total:,}".replace(",", " ")
                + "</p>"
            )

            try:
                import matplotlib

                matplotlib.use("Agg")
                import matplotlib.pyplot as plt

                top = rows[: min(14, len(rows))]
                if top:
                    labels_plain = [k[:40] for k, _, _ in top]
                    vals = [ne for _, ne, _ in top]
                    fig, ax = plt.subplots(figsize=(8, max(3.0, 0.35 * len(top))))
                    y = range(len(top))
                    ax.barh(list(y), vals, color="#059669", alpha=0.85)
                    ax.set_yticks(list(y))
                    ax.set_yticklabels(labels_plain, fontsize=8)
                    ax.invert_yaxis()
                    ax.set_xlabel("Сколько чисел в блоке")
                    ax.set_title("Крупнейшие куски обученной модели", fontsize=11)
                    ax.grid(True, axis="x", alpha=0.25)
                    uri = _figure_to_data_uri(fig)
                    chart_html = (
                        f'<figure style="margin:12px 0;"><img src="{uri}" alt="" '
                        'style="max-width:100%;height:auto;border:1px solid #e2e8f0;border-radius:10px;background:#fff;"/>'
                        '<figcaption style="font-size:12px;color:#64748b;margin-top:8px;">'
                        "Длинные полосы — слои, в которых больше всего коэффициентов."
                        "</figcaption></figure>"
                    )
            except Exception as exc:
                chart_html = f'<p style="color:#b45309;">Диаграмма не построена: {escape(str(exc))}</p>'

            parts.append(chart_html)
    except Exception as exc:
        parts.append(
            f"<p>Не удалось прочитать чекпоинт: <code>{escape(str(exc))}</code>. "
            f'Можно <a href="{dl_e}">скачать файл</a> и открыть в PyTorch.</p>'
        )
        return "".join(parts)

    try:
        st = path.stat()
        sz = st.st_size
        sz_s = f"{sz / 1024 / 1024:.2f} МиБ" if sz >= 1024 * 1024 else f"{sz / 1024:.1f} КиБ"
    except OSError:
        sz_s = "—"

    parts.append(
        f'<p style="font-size:14px;margin-top:12px;">Размер на диске: <strong>{escape(sz_s)}</strong>. '
        f'Полная копия для специалистов: <a href="{dl_e}">скачать {fname_e}</a>.</p>'
    )

    if tech_lines:
        parts.append(
            _technical_block(
                "Список слоёв (для разработчиков)",
                "\n".join(tech_lines),
            )
        )

    return "".join(parts)
