from django.db import migrations


INITIAL_CATEGORIES = (
    "Cots",
    "Mattresses",
    "Sofas",
    "Pillows",
    "Blankets",
    "Others",
)


def seed_categories(apps, schema_editor):
    Company = apps.get_model("tenancy", "Company")
    ProductCategory = apps.get_model("leads", "ProductCategory")
    database = schema_editor.connection.alias
    company = Company.objects.using(database).get(name="Duroflex")

    for name in INITIAL_CATEGORIES:
        ProductCategory.objects.using(database).get_or_create(
            company_id=company.pk,
            name=name,
            defaults={"is_active": True},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("leads", "0001_initial"),
        ("tenancy", "0002_seed_mvp_tenant"),
    ]

    operations = [migrations.RunPython(seed_categories, migrations.RunPython.noop)]
