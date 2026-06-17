from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cards", "0003_card_is_marked"),
    ]

    operations = [
        migrations.AddField(
            model_name="deck",
            name="show_tags_in_review",
            field=models.BooleanField(default=False),
        ),
    ]
