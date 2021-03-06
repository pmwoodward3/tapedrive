# Generated by Django 2.0.5 on 2018-06-01 19:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('podcasts', '0005_episode_shownotes'),
    ]

    operations = [
        migrations.AddField(
            model_name='listener',
            name='image_security_policy',
            field=models.CharField(choices=[('a', 'Allow All'), ('f', 'Allow First-Party'), ('n', 'Allow None')], default='f', help_text='How to load external images in show notes, etc.', max_length=1, verbose_name='Image Security Policy'),
        ),
    ]
