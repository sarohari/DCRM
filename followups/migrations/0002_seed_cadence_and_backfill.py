from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db import migrations
from django.utils import timezone


def seed_cadence_and_backfill(apps, schema_editor):
    Company = apps.get_model("tenancy", "Company")
    FollowUpCadence = apps.get_model("followups", "FollowUpCadence")
    FollowUpCadenceDay = apps.get_model("followups", "FollowUpCadenceDay")
    FollowUp = apps.get_model("followups", "FollowUp")
    Lead = apps.get_model("leads", "Lead")

    company = Company.objects.filter(name="Duroflex").first()
    if company is None:
        return
    cadence, _created = FollowUpCadence.objects.get_or_create(
        company_id=company.pk,
        is_active=True,
    )
    for offset in (1, 3, 7):
        FollowUpCadenceDay.objects.get_or_create(cadence_id=cadence.pk, day_offset=offset)

    tz = ZoneInfo("Asia/Kolkata")
    open_leads = Lead.objects.filter(company_id=company.pk).exclude(status__in=["CONVERTED", "LOST"])
    for lead in open_leads.iterator():
        if FollowUp.objects.filter(lead_id=lead.pk).exists():
            continue
        visit = lead.visit
        visit_date = timezone.localtime(visit.visited_at, tz).date()
        FollowUp.objects.bulk_create(
            [
                FollowUp(
                    company_id=lead.company_id,
                    outlet_id=lead.outlet_id,
                    lead_id=lead.pk,
                    assigned_to_id=lead.assigned_to_id,
                    scheduled_date=visit_date + timedelta(days=offset),
                    channel="CALL",
                    created_by_id=lead.created_by_id,
                )
                for offset in (1, 3, 7)
            ]
        )


class Migration(migrations.Migration):
    dependencies = [
        ("followups", "0001_initial"),
        ("leads", "0002_seed_product_categories"),
        ("tenancy", "0002_seed_mvp_tenant"),
    ]

    operations = [migrations.RunPython(seed_cadence_and_backfill, migrations.RunPython.noop)]
