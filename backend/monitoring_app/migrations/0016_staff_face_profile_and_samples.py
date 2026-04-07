# Manual migration: Staff.face_profile_state + StaffFaceSample

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

import monitoring_app.models as monitoring_models


class Migration(migrations.Migration):

    dependencies = [
        ("monitoring_app", "0015_alter_lessonattendance_photo_manual_verdict_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="staff",
            name="face_profile_state",
            field=models.CharField(
                choices=[
                    ("ready", "Галерея для обычной верификации"),
                    ("weak_gallery", "Слабая галерея"),
                    ("bootstrap_required", "Нужен базовый сбор углов"),
                ],
                db_index=True,
                default="ready",
                max_length=24,
                verbose_name="Состояние профиля Face ID",
            ),
        ),
        migrations.CreateModel(
            name="StaffFaceSample",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "image",
                    models.ImageField(
                        upload_to=monitoring_models.staff_face_sample_upload_to,
                        validators=[
                            django.core.validators.FileExtensionValidator(
                                allowed_extensions=["jpg", "jpeg", "png"]
                            )
                        ],
                        verbose_name="Кадр",
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("bootstrap_capture", "Сбор Face Lab"),
                            ("admin_capture", "Админ / карточка"),
                            ("successful_verify_capture", "Успешная верификация"),
                            ("lesson_attendance", "Посещаемость"),
                            ("avatar", "Аватар"),
                        ],
                        default="bootstrap_capture",
                        max_length=32,
                        verbose_name="Источник",
                    ),
                ),
                (
                    "angle",
                    models.CharField(
                        choices=[
                            ("front", "Фронт"),
                            ("left", "Чуть влево"),
                            ("right", "Чуть вправо"),
                            ("unknown", "Не указан"),
                        ],
                        db_index=True,
                        default="unknown",
                        max_length=16,
                        verbose_name="Ракурс",
                    ),
                ),
                (
                    "with_glasses",
                    models.BooleanField(default=False, verbose_name="Очки на кадре"),
                ),
                (
                    "pad_status",
                    models.CharField(
                        blank=True, default="", max_length=32, verbose_name="PAD статус"
                    ),
                ),
                (
                    "quality_passed",
                    models.BooleanField(default=False, verbose_name="Качество пройдено"),
                ),
                (
                    "is_trusted",
                    models.BooleanField(default=True, verbose_name="Доверенный"),
                ),
                (
                    "is_active",
                    models.BooleanField(db_index=True, default=True, verbose_name="Активен"),
                ),
                (
                    "embedding_ready",
                    models.BooleanField(
                        default=False,
                        verbose_name="Эмбеддинг учтён в gallery_real (после команды)",
                    ),
                ),
                (
                    "probe_eyeglasses_likely",
                    models.BooleanField(
                        blank=True,
                        null=True,
                        verbose_name="Парсер: вероятны очки",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Создано"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Обновлено"),
                ),
                (
                    "staff",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="face_samples",
                        to="monitoring_app.staff",
                        verbose_name="Сотрудник",
                    ),
                ),
            ],
            options={
                "verbose_name": "Эталонный кадр лица",
                "verbose_name_plural": "Эталонные кадры лица",
            },
        ),
        migrations.AddIndex(
            model_name="stafffacesample",
            index=models.Index(
                fields=["staff", "is_active", "is_trusted"],
                name="m_app_sfs_staff_act_tr_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="stafffacesample",
            index=models.Index(
                fields=["staff", "angle", "is_active"],
                name="m_app_sfs_staff_ang_act_idx",
            ),
        ),
    ]
