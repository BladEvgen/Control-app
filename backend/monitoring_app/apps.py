from django.apps import AppConfig


class MonitoringAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "monitoring_app"
    verbose_name = "Система мониторинга"

    def ready(self):
        import monitoring_app.signals
        # Load ArcFace at startup and warm-up once
        try:
            from monitoring_app import ml
            ml.load_arcface_model()
            # Enable cudnn benchmark for speed on GPU
            try:
                import torch
                if torch.cuda.is_available():
                    if hasattr(torch.backends, "cudnn"):
                        torch.backends.cudnn.benchmark = True
            except Exception:
                pass
        except Exception:
            # Avoid startup crash if model init fails; runtime will retry on first use
            pass
