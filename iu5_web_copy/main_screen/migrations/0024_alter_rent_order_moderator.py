# Generated by Django 4.2.4 on 2024-10-29 17:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main_screen', '0023_alter_rent_order_moderator'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rent_order',
            name='moderator',
            field=models.CharField(default='Moderator1', max_length=255, verbose_name='Модератор'),
        ),
    ]
