from django.conf import settings

PALETTE_COOKIE_NAME = "admin_palette"


def selected_palette(request):
    palette = request.COOKIES.get(PALETTE_COOKIE_NAME)
    return palette if palette in settings.ADMIN_PALETTES else settings.ADMIN_PRIMARY_COLOR


def primary_colors(request):
    palette = settings.ADMIN_PALETTES[selected_palette(request)]
    return {
        shade: f"oklch({color})"
        for shade, color in zip(settings.ADMIN_COLOR_SHADES, palette, strict=True)
    }


PALETTE_LABELS = {
    "teal": "Бирюза",
    "sky": "Небо",
    "emerald": "Изумруд",
    "cyan": "Циан",
    "blue": "Синий",
    "indigo": "Индиго",
    "violet": "Фиалка",
    "fuchsia": "Фуксия",
    "rose": "Рубин",
    "orange": "Апельсин",
    "amber": "Янтарь",
    "lime": "Лайм",
}


def palette_choices(request):
    selected = selected_palette(request)
    choices = []
    for name, values in settings.ADMIN_PALETTES.items():
        colors = dict(zip(settings.ADMIN_COLOR_SHADES, values, strict=True))
        choices.append(
            {
                "name": name,
                "label": PALETTE_LABELS.get(name, name.replace("_", " ").capitalize()),
                "selected": name == selected,
                "style": ";".join(
                    f"--palette-{shade}:oklch({colors[shade]})" for shade in ("300", "500", "700")
                ),
            }
        )
    return choices
