"""New accounts start in the operator's configured timezone, not UTC.

A default only applies to rows created after this runs, so existing accounts
keep whatever they already have - deliberately. Silently rewriting a live
account's timezone would change which calendar day its already-stored
`local_date` values are read against, and that choice belongs on the profile
page rather than in a migration.
"""


import apps.accounts.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_user_allow_partner_logging_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='timezone',
            field=models.CharField(default=apps.accounts.models.default_timezone, max_length=64),
        ),
    ]
