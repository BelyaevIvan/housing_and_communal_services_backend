# Generated by Django 4.2.4 on 2024-09-25 11:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main_screen', '0003_alter_orderservice_current_reading_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='orderservice',
            name='current_reading',
            field=models.CharField(blank=True, null=True, verbose_name='Текущие показания/Дата'),
        ),
    ]
