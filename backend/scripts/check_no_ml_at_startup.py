import os
import resource
import sys

BUDGET_MB = 250
HEAVY = ("torch", "torchvision", "sklearn", "pandas", "cv2", "insightface")


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_settings.settings")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    import django

    django.setup()
    __import__("django_settings.asgi")
    from django.urls import get_resolver

    get_resolver().url_patterns

    leaked = sorted(m for m in HEAVY if m in sys.modules)
    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

    print(f"RSS после старта ASGI: {rss_mb:.0f} MB (бюджет {BUDGET_MB} MB)")
    if leaked:
        print(f"ПРОВАЛ: на старте загружены {', '.join(leaked)} — верни импорт внутрь функции")
        return 1
    if rss_mb > BUDGET_MB:
        print(f"ПРОВАЛ: превышен бюджет памяти на {rss_mb - BUDGET_MB:.0f} MB")
        return 1
    print("OK: ML-стек не тронут, бюджет соблюдён")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
