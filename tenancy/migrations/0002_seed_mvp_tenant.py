from django.db import migrations


def create_mvp_tenant(apps, schema_editor):
    Company = apps.get_model("tenancy", "Company")
    Outlet = apps.get_model("tenancy", "Outlet")
    database = schema_editor.connection.alias

    company, _ = Company.objects.using(database).get_or_create(
        name="Duroflex",
        defaults={
            "contact_name": "",
            "contact_email": "",
            "contact_phone": "",
            "address": "",
            "gst_number": "",
        },
    )
    Outlet.objects.using(database).get_or_create(
        company_id=company.pk,
        name="Salem-outlet-1",
        defaults={"address": "", "phone": ""},
    )


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0001_initial")]

    operations = [migrations.RunPython(create_mvp_tenant, migrations.RunPython.noop)]
