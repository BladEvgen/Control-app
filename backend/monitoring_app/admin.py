from django.apps import apps
from django.contrib import admin
from django.db import models as django_models

admin.site.site_header = "Панель управления"
admin.site.index_title = "Администрирование сайта"
admin.site.site_title = "Администрирование"

exclude_models = []

for model in apps.get_models():
    if model not in exclude_models and model not in admin.site._registry:
        model_name = model.__name__
        admin_class_name = f"{model_name}Admin"
        admin_class = type(
            admin_class_name,
            (admin.ModelAdmin,),
            {
                "list_display": [field.name for field in model._meta.fields],
                "list_filter": [
                    field.name
                    for field in model._meta.fields
                    if isinstance(field, django_models.CharField)
                ],
                "search_fields": [
                    field.name
                    for field in model._meta.fields
                    if isinstance(field, django_models.CharField)
                ],
            },
        )
        admin.site.register(model, admin_class)
