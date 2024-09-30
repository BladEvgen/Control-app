import os
from django.core.management import call_command

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_settings.settings")

import django

django.setup()
os.environ["PATH"] += os.pathsep + "C:/Program Files/Graphviz/bin"

call_command("graph_models", "-a", "-o", "models.png", "--pydot")
