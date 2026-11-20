# Copyright (c) 2026-present Orbit contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Prepare a fresh Orbit server so nobody else can claim it.

Creates (or updates) the instance admin, the workspace the AI agent works in, and the API key the agent
uses. Idempotent: safe to run on every deployment. Settings come from the environment:

    ORBIT_ADMIN_EMAIL, ORBIT_ADMIN_PASSWORD, ORBIT_ADMIN_NAME (optional)
    ORBIT_WORKSPACE_SLUG, ORBIT_WORKSPACE_NAME (optional)
    ORBIT_AGENT_API_KEY
"""

import os
import uuid

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from plane.db.models import APIToken, Profile, User, Workspace, WorkspaceMember
from plane.license.models import Instance, InstanceAdmin


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise CommandError(f"{name} is not set")
    return value


class Command(BaseCommand):
    help = "Create the Orbit instance admin, the agent's workspace and its API key (idempotent)"

    def handle(self, *args, **options):
        email = _required("ORBIT_ADMIN_EMAIL").lower()
        password = _required("ORBIT_ADMIN_PASSWORD")
        name = os.environ.get("ORBIT_ADMIN_NAME", "Admin").strip() or "Admin"
        slug = _required("ORBIT_WORKSPACE_SLUG")
        workspace_name = os.environ.get("ORBIT_WORKSPACE_NAME", "Orbit").strip() or "Orbit"
        api_key = _required("ORBIT_AGENT_API_KEY")

        instance = Instance.objects.first()
        if instance is None:
            raise CommandError("The instance is not registered yet: start the api service first")

        with transaction.atomic():
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create(
                    email=email,
                    username=uuid.uuid4().hex,
                    first_name=name,
                    display_name=email.split("@")[0],
                    password=make_password(password),
                    is_password_autoset=False,
                    is_active=True,
                    token_updated_at=timezone.now(),
                )
                self.stdout.write(f"admin created: {email}")
            elif not user.check_password(password):
                user.password = make_password(password)
                user.is_password_autoset = False
                user.save(update_fields=["password", "is_password_autoset"])
                self.stdout.write(f"admin password updated: {email}")

            InstanceAdmin.objects.get_or_create(user=user, instance=instance, defaults={"role": 20})
            if not instance.is_setup_done:
                instance.is_setup_done = True
                instance.instance_name = "Orbit"
                instance.save(update_fields=["is_setup_done", "instance_name"])
                self.stdout.write("instance setup marked as done")

            workspace = Workspace.objects.filter(slug=slug).first()
            if workspace is None:
                workspace = Workspace.objects.create(name=workspace_name, slug=slug, owner=user)
                self.stdout.write(f"workspace created: {slug}")
            WorkspaceMember.objects.update_or_create(
                workspace=workspace, member=user, defaults={"role": 20, "is_active": True}
            )

            profile, _ = Profile.objects.get_or_create(user=user)
            if not profile.is_onboarded:
                profile.is_onboarded = True
                profile.onboarding_step = {
                    "profile_complete": True,
                    "workspace_create": True,
                    "workspace_invite": True,
                    "workspace_join": True,
                }
                profile.last_workspace_id = workspace.id
                profile.save(update_fields=["is_onboarded", "onboarding_step", "last_workspace_id"])

            token, created = APIToken.objects.get_or_create(
                token=api_key,
                defaults={"user": user, "workspace": workspace, "label": "Orbit AI agent", "is_active": True},
            )
            if not created and (token.workspace_id != workspace.id or not token.is_active):
                token.workspace, token.user, token.is_active = workspace, user, True
                token.save(update_fields=["workspace", "user", "is_active"])
            if created:
                self.stdout.write("agent API key created")

        self.stdout.write(self.style.SUCCESS(f"Orbit ready: workspace '{slug}', admin {email}"))
