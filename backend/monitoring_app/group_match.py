from __future__ import annotations

from typing import Any

_UNICODE_DASHES: tuple[str, ...] = ("\u2013", "\u2014", "\u2212")

_UNICODE_SPACE_MAP: tuple[tuple[str, str], ...] = (
    ("\u00a0", " "),
    ("\u202f", " "),
    ("\u2009", " "),
    ("\u200b", ""),
    ("\ufeff", ""),
)

_CYRILLIC_LATIN_LOOKALIKE_TRANS = str.maketrans(
    {
        "\u0430": "a",
        "\u0432": "b",
        "\u0435": "e",
        "\u043a": "k",
        "\u043c": "m",
        "\u043e": "o",
        "\u0440": "p",
        "\u0441": "c",
        "\u0443": "y",
        "\u0445": "x",
    }
)


def _fold_cyrillic_latin_lookalikes(s: str) -> str:
    """Кириллица, похожая на латиницу → ASCII (Nitro «101-А» vs control «101 A»)."""
    return s.translate(_CYRILLIC_LATIN_LOOKALIKE_TRANS)


def normalize_group_label(raw: str) -> str:
    """Приводит строку группы к каноническому виду для отображения и сортировки.

    Выполняет: обрезка краёв, замена unicode-тире на ``-``, замена узких/NBSP
    пробелов на обычный пробел (или удаление zero-width), круглые скобки
    заменяются на пробел (Nitro: ``ФФ25(3ж)-104Б`` ↔ control: ``ФФ25 3ж 104Б``),
    схлопывание последовательностей пробелов в один.

    Args:
        raw: Исходная подпись группы или фрагмент запроса.

    Returns:
        Нормализованная строка; для пустого или только пробелов входа — ``""``.

    Example:
        >>> normalize_group_label("  ЖМ22–403\\u00a0А  ")
        'ЖМ22-403 А'
        >>> normalize_group_label("ФФ25(3ж)-104Б қ/б")
        'ФФ25 3ж -104Б қ/б'
    """
    if not raw:
        return ""

    s = raw
    for dash in _UNICODE_DASHES:
        s = s.replace(dash, "-")
    for old, new in _UNICODE_SPACE_MAP:
        s = s.replace(old, new)
    s = s.replace("(", " ").replace(")", " ")
    return " ".join(s.strip().split())


def compact_group_fingerprint(raw: str) -> str:
    """Компактный отпечаток без дефисов и пробелов (слэш ``/`` сохраняется).

    Example:
        >>> compact_group_fingerprint("жм22 424 б о/б") == compact_group_fingerprint(
        ...     "ЖМ22-424Б о/б"
        ... )
        True
    """
    s = _fold_cyrillic_latin_lookalikes(normalize_group_label(raw).casefold())
    return "".join(ch for ch in s if ch != "-" and not ch.isspace())


def compact_group_match_key(raw: str) -> str:
    """Ключ сопоставления: как fingerprint, плюс удаление ``/`` («о/б» ↔ «о б»).

    Example:
        >>> a = compact_group_match_key("СФ23-313-А о/б")
        >>> b = compact_group_match_key("СФ23 313 А о б")
        >>> a == b
        True
        >>> compact_group_match_key("ФФ25(3ж)-104Б қ/б") == compact_group_match_key(
        ...     "ФФ25 3ж 104Б қ б"
        ... )
        True
        >>> compact_group_match_key("GM25-101-А а/б") == compact_group_match_key(
        ...     "GM25 101 A а б"
        ... )
        True
    """
    s = _fold_cyrillic_latin_lookalikes(normalize_group_label(raw).casefold())
    return "".join(ch for ch in s if ch != "-" and ch != "/" and not ch.isspace())


def childdepartment_name_matches_group_query(
    dept_name: str,
    search_term: str,
    *,
    min_prefix_len: int = 3,
) -> bool:
    """Совпадение имени подотдела с поисковой строкой по компактному ключу.

    Учитывается равенство ключей и префикс (укороченный запрос вроде «СФ23 313»).

    Args:
        dept_name: Поле ``ChildDepartment.name``.
        search_term: Строка из поля поиска админки (уже ``strip`` снаружи не обязателен).
        min_prefix_len: Минимальная длина ключа запроса для сравнения по префиксу.

    Returns:
        ``True``, если строка поиска непустая и имя отдела подходит по правилам.

    Example:
        >>> childdepartment_name_matches_group_query(
        ...     "СФ23 313 А о б", "СФ23-313-А о/б"
        ... )
        True
        >>> childdepartment_name_matches_group_query(
        ...     "ФФ25 3ж 104Б қ б", "ФФ25(3ж)-104Б қ/б"
        ... )
        True
        >>> childdepartment_name_matches_group_query("СФ23 313 А о б", "СФ23 313")
        True
    """
    term = (search_term or "").strip()
    if not term:
        return False
    key = compact_group_match_key(term)
    if not key:
        return False
    nk = compact_group_match_key(dept_name or "")
    if nk == key:
        return True
    if len(key) < min_prefix_len:
        return False
    return nk.startswith(key) or key.startswith(nk)


def childdepartment_pks_for_group_style_search(
    queryset: Any,
    search_term: str,
    *,
    min_prefix_len: int = 3,
) -> list[Any]:
    """Возвращает первичные ключи отделов, чьё ``name`` совпало по :func:`childdepartment_name_matches_group_query`.

    Args:
        queryset: ``QuerySet`` без дополнительных ``.filter()`` по поиску (как в
            ``ModelAdmin.get_search_results``).
        search_term: Строка ``q`` из админки.

    Returns:
        Список ``pk`` (может быть пустым).
    """
    term = (search_term or "").strip()
    if not term or not compact_group_match_key(term):
        return []
    return [
        pk
        for pk, name in queryset.values_list("pk", "name")
        if childdepartment_name_matches_group_query(
            str(name) if name is not None else "",
            term,
            min_prefix_len=min_prefix_len,
        )
    ]


__all__ = (
    "normalize_group_label",
    "compact_group_fingerprint",
    "compact_group_match_key",
    "childdepartment_name_matches_group_query",
    "childdepartment_pks_for_group_style_search",
)


if __name__ == "__main__":
    import doctest

    doctest.testmod()
