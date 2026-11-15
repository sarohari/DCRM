"""MVP application accounts for the Owner and Outlet Manager roles."""

import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from accounts.phone_numbers import normalize_email, normalize_phone
from tenancy.models import Company, Outlet


class UserRole(models.TextChoices):
    OWNER = "OWNER", "Owner"
    OUTLET_MANAGER = "OUTLET_MANAGER", "Outlet Manager"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(
        self,
        *,
        name,
        role,
        company,
        outlet,
        password,
        email=None,
        phone=None,
        **extra_fields,
    ):
        email = normalize_email(email) if email else None
        phone = normalize_phone(phone) if phone else None
        if not email and not phone:
            raise ValidationError("Provide an email address, a phone number, or both.")
        if not password:
            raise ValidationError("A password is required.")

        user = self.model(
            name=name.strip(),
            role=role,
            company=company,
            outlet=outlet,
            email=email,
            phone=phone,
            **extra_fields,
        )
        user.set_password(password)
        user.full_clean()
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="users")
    outlet = models.ForeignKey(Outlet, on_delete=models.PROTECT, related_name="users")
    role = models.CharField(max_length=20, choices=UserRole.choices)
    name = models.CharField(max_length=150)
    email = models.EmailField(max_length=254, unique=True, null=True, blank=True)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "id"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        ordering = ["role", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "role"],
                name="one_account_per_role_per_company",
            ),
            models.CheckConstraint(
                condition=(~Q(email__isnull=True) & ~Q(email=""))
                | (~Q(phone__isnull=True) & ~Q(phone="")),
                name="user_has_email_or_phone",
            ),
        ]

    def clean(self):
        super().clean()
        if self.email:
            self.email = normalize_email(self.email)
        if self.phone:
            self.phone = normalize_phone(self.phone)
        if self.company_id and self.outlet_id and self.outlet.company_id != self.company_id:
            raise ValidationError({"outlet": "The outlet must belong to the user's company."})
        if self.email is None and self.phone is None:
            raise ValidationError("Provide an email address, a phone number, or both.")

    def get_full_name(self):
        return self.name

    def get_short_name(self):
        return self.name.split(maxsplit=1)[0]

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"
