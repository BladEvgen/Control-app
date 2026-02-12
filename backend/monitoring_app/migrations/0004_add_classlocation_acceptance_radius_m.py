# Generated manually for ClassLocation.acceptance_radius_m

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("monitoring_app", "0003_absentreason_monitoring__staff_i_7a2241_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="classlocation",
            name="acceptance_radius_m",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Переопределение: если задано, используется вместо вычисленного по соседям. 50–100 м типично для здания/двора.",
                null=True,
                verbose_name="Приёмный радиус (м)",
            ),
        ),
    ]
