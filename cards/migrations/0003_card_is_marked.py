from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cards", "0002_card_image_card_image_face_card_image_mime_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="card",
            name="is_marked",
            field=models.BooleanField(default=False),
        ),
    ]
