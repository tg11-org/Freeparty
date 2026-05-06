from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


GROUP_PERMISSIONS = {
    # =========================================================================
    # Organisational labels — no permissions; used for filtering and identity
    # =========================================================================
    "Brand Account": [],           # Official brand/company presence
    "Verified Artist": [],         # Musicians, performers, promoters
    "Press": [],                   # Journalists and media outlets
    "Sponsor": [],                 # Commercial sponsors and partners
    "Beta Tester": [],             # Opted-in testers for pre-release features
    "Early Adopter": [],           # Users from the founding cohort
    "Partner Organisation": [],    # NGOs, venues, collectives with formal partnership

    # =========================================================================
    # Staff permission groups — ordered by access tier (lowest → highest)
    # =========================================================================

    # -------------------------------------------------------------------------
    # Tier 1 — User-facing support: account lookups and lifecycle actions
    # -------------------------------------------------------------------------
    "Support": [
        "accounts.view_user",
        "accounts.view_emailverificationtoken",
        "accounts.view_accountactiontoken",
        "accounts.view_support_user_info",
        "accounts.resend_verification_email",
        "accounts.manage_account_lifecycle_support",
        "core.view_asynctaskexecution",
        "core.view_asynctaskfailure",
        "core.view_support_diagnostics",
    ],
    # -------------------------------------------------------------------------
    # Tier 2 — Content review: read-only dashboard access for junior reviewers
    # -------------------------------------------------------------------------
    "Content Reviewer": [
        "moderation.view_report",
        "moderation.view_moderationaction",
        "moderation.view_moderationnote",
        "posts.view_attachment",
        "moderation.access_moderation_dashboard",
    ],
    # -------------------------------------------------------------------------
    # Tier 2 — Full moderation: review and action on reports
    # -------------------------------------------------------------------------
    "Moderator": [
        "moderation.view_report",
        "moderation.change_report",
        "moderation.view_moderationaction",
        "moderation.add_moderationaction",
        "moderation.view_moderationnote",
        "moderation.add_moderationnote",
        "posts.view_attachment",
        "posts.change_attachment",
        "moderation.access_moderation_dashboard",
        "moderation.review_reports",
        "moderation.manage_moderation_actions",
        "moderation.view_audit_summary",
    ],
    # -------------------------------------------------------------------------
    # Tier 2 — Community management: moderation + user visibility, no security
    # -------------------------------------------------------------------------
    "Community Manager": [
        "accounts.view_user",
        "accounts.view_support_user_info",
        "moderation.view_report",
        "moderation.change_report",
        "moderation.view_moderationaction",
        "moderation.add_moderationaction",
        "moderation.view_moderationnote",
        "moderation.add_moderationnote",
        "posts.view_attachment",
        "posts.change_attachment",
        "moderation.access_moderation_dashboard",
        "moderation.review_reports",
        "moderation.manage_moderation_actions",
    ],
    # -------------------------------------------------------------------------
    # Tier 2 — Minor safety: CSAM/NCII-focused moderation + account restriction
    # -------------------------------------------------------------------------
    "Minor Safety Specialist": [
        "accounts.view_user",
        "accounts.view_support_user_info",
        "accounts.manage_account_lifecycle_support",
        "moderation.view_report",
        "moderation.change_report",
        "moderation.view_moderationaction",
        "moderation.add_moderationaction",
        "moderation.view_moderationnote",
        "moderation.add_moderationnote",
        "posts.view_attachment",
        "posts.change_attachment",
        "moderation.access_moderation_dashboard",
        "moderation.review_reports",
        "moderation.manage_moderation_actions",
    ],
    # -------------------------------------------------------------------------
    # Tier 3 — Federation management: allow/block instances and actor oversight
    # -------------------------------------------------------------------------
    "Federation Manager": [
        "federation.view_instance",
        "federation.add_instance",
        "federation.change_instance",
        "federation.view_remoteactor",
        "federation.view_federationobject",
        "federation.view_federationdelivery",
        "federation.manage_federation_allowlist",
        "federation.view_federation_health",
        "actors.view_actor",
        "actors.manage_actor_verification",
        "actors.suspend_actor",
    ],
    # -------------------------------------------------------------------------
    # Tier 3 — Security analyst: read-only view of security and trust signals
    # -------------------------------------------------------------------------
    "Security Analyst": [
        "moderation.view_securityauditevent",
        "moderation.view_trustsignal",
        "moderation.view_security_audit_events",
        "core.view_security_posture",
    ],
    # -------------------------------------------------------------------------
    # Tier 3 — Trust & Safety Admin: full moderation + security posture
    # -------------------------------------------------------------------------
    "Trust & Safety Admin": [
        "moderation.view_report",
        "moderation.change_report",
        "moderation.view_moderationaction",
        "moderation.add_moderationaction",
        "moderation.view_moderationnote",
        "moderation.add_moderationnote",
        "posts.view_attachment",
        "posts.change_attachment",
        "moderation.access_moderation_dashboard",
        "moderation.review_reports",
        "moderation.manage_moderation_actions",
        "moderation.view_audit_summary",
        "moderation.view_securityauditevent",
        "moderation.view_trustsignal",
        "moderation.change_trustsignal",
        "moderation.view_security_audit_events",
        "moderation.manage_trust_signals",
        "core.view_security_posture",
        "core.run_email_diagnostics",
    ],
    # -------------------------------------------------------------------------
    # Tier 3 — DevOps/SRE: operational health, no user or moderation data
    # -------------------------------------------------------------------------
    "DevOps/SRE": [
        "core.view_asynctaskexecution",
        "core.view_asynctaskfailure",
        "core.view_support_diagnostics",
        "core.run_email_diagnostics",
        "core.view_security_posture",
        "federation.view_instance",
        "federation.view_federationdelivery",
        "federation.view_federation_health",
    ],
    # -------------------------------------------------------------------------
    # Tier 4 — Read-Only Auditor: compliance/legal read-only across all domains
    # -------------------------------------------------------------------------
    "Read-Only Auditor": [
        "accounts.view_user",
        "accounts.view_emailverificationtoken",
        "accounts.view_accountactiontoken",
        "accounts.view_support_user_info",
        "moderation.view_report",
        "moderation.view_moderationaction",
        "moderation.view_moderationnote",
        "moderation.view_securityauditevent",
        "moderation.view_trustsignal",
        "moderation.access_moderation_dashboard",
        "moderation.view_audit_summary",
        "moderation.view_security_audit_events",
        "core.view_asynctaskexecution",
        "core.view_asynctaskfailure",
        "core.view_support_diagnostics",
        "core.view_security_posture",
        "federation.view_instance",
        "federation.view_remoteactor",
        "federation.view_federationdelivery",
        "federation.view_federation_health",
        "actors.view_actor",
        "posts.view_attachment",
    ],
    # -------------------------------------------------------------------------
    # Tier 5 — Administrator: full operational access across all subsystems
    # -------------------------------------------------------------------------
    "Administrator": [
        "auth.view_group",
        "auth.add_group",
        "auth.change_group",
        "auth.delete_group",
        "accounts.view_user",
        "accounts.add_user",
        "accounts.change_user",
        "accounts.view_emailverificationtoken",
        "accounts.view_accountactiontoken",
        "accounts.view_support_user_info",
        "accounts.resend_verification_email",
        "accounts.manage_account_lifecycle_support",
        "moderation.view_report",
        "moderation.change_report",
        "moderation.view_moderationaction",
        "moderation.add_moderationaction",
        "moderation.view_moderationnote",
        "moderation.add_moderationnote",
        "moderation.view_securityauditevent",
        "moderation.view_trustsignal",
        "moderation.change_trustsignal",
        "moderation.access_moderation_dashboard",
        "moderation.review_reports",
        "moderation.manage_moderation_actions",
        "moderation.view_audit_summary",
        "moderation.view_security_audit_events",
        "moderation.manage_trust_signals",
        "posts.view_attachment",
        "posts.change_attachment",
        "core.view_asynctaskexecution",
        "core.view_asynctaskfailure",
        "core.view_support_diagnostics",
        "core.view_security_posture",
        "core.run_email_diagnostics",
        "federation.view_instance",
        "federation.add_instance",
        "federation.change_instance",
        "federation.delete_instance",
        "federation.view_remoteactor",
        "federation.view_federationobject",
        "federation.view_federationdelivery",
        "federation.manage_federation_allowlist",
        "federation.view_federation_health",
        "actors.view_actor",
        "actors.change_actor",
        "actors.manage_actor_verification",
        "actors.suspend_actor",
    ],
}


class Command(BaseCommand):
    help = "Create or update the default Freeparty staff groups and their permissions."

    def handle(self, *args, **options):
        for group_name, permission_names in GROUP_PERMISSIONS.items():
            group, _created = Group.objects.get_or_create(name=group_name)
            permissions = []
            for permission_name in permission_names:
                app_label, codename = permission_name.split(".", 1)
                permissions.append(Permission.objects.get(content_type__app_label=app_label, codename=codename))
            group.permissions.set(permissions)
            self.stdout.write(self.style.SUCCESS(f"Synced {group_name} ({len(permissions)} permissions)"))