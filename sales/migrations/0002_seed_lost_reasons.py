from django.db import migrations


def seed_lost_reasons(apps, schema_editor):
    Company = apps.get_model("tenancy", "Company")
    LostReason = apps.get_model("sales", "LostReason")
    company = Company.objects.filter(name="Duroflex").first()
    if company is None:
        return
    for label in ("Price", "Chose competitor", "Not ready", "Other"):
        LostReason.objects.get_or_create(company_id=company.pk, label=label)


class Migration(migrations.Migration):
    dependencies = [
        ("leads", "0004_lead_lost_reason"),
        ("sales", "0001_initial"),
        ("tenancy", "0002_seed_mvp_tenant"),
    ]

    operations = [migrations.RunPython(seed_lost_reasons, migrations.RunPython.noop)]
