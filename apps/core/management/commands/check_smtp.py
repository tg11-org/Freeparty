"""
Management command: check_smtp
Verifies SMTP connectivity and authentication using the current Django email settings.
Exit code 0 = OK, 1 = failure (suitable for CI / container health checks).
"""

import smtplib
import ssl

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Check SMTP connectivity and authentication against the configured email backend."

    def add_arguments(self, parser):
        parser.add_argument(
            "--send-test",
            dest="recipient",
            default="",
            metavar="EMAIL",
            help="If supplied, send a test message to this address after auth succeeds.",
        )

    def handle(self, *args, **options):
        backend = getattr(settings, "EMAIL_BACKEND", "")
        if "smtp" not in backend.lower():
            self.stdout.write(
                self.style.WARNING(
                    f"EMAIL_BACKEND is not SMTP ({backend}). Nothing to check."
                )
            )
            return

        host = getattr(settings, "EMAIL_HOST", "")
        port = getattr(settings, "EMAIL_PORT", 587)
        use_tls = getattr(settings, "EMAIL_USE_TLS", True)
        use_ssl = getattr(settings, "EMAIL_USE_SSL", False)
        user = getattr(settings, "EMAIL_HOST_USER", "")
        password = getattr(settings, "EMAIL_HOST_PASSWORD", "")
        timeout = 10

        if not host:
            self.stderr.write(self.style.ERROR("EMAIL_HOST is not set."))
            raise SystemExit(1)

        self.stdout.write(f"Connecting to {host}:{port} (TLS={use_tls}, SSL={use_ssl}) …")
        try:
            if use_ssl:
                context = ssl.create_default_context()
                conn = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
            else:
                conn = smtplib.SMTP(host, port, timeout=timeout)
                conn.ehlo()
                if use_tls:
                    context = ssl.create_default_context()
                    conn.starttls(context=context)
                    conn.ehlo()

            if user:
                conn.login(user, password)
                self.stdout.write(self.style.SUCCESS(f"  Authenticated as {user}"))
            else:
                self.stdout.write(self.style.WARNING("  No EMAIL_HOST_USER set — skipping auth."))

            recipient = options["recipient"].strip()
            if recipient:
                from_addr = getattr(settings, "DEFAULT_FROM_EMAIL", user or "noreply@freeparty.local")
                conn.sendmail(
                    from_addr,
                    recipient,
                    f"Subject: Freeparty SMTP test\r\n\r\nSMTP connectivity test from Freeparty check_smtp command.",
                )
                self.stdout.write(self.style.SUCCESS(f"  Test message sent to {recipient}"))

            conn.quit()
        except smtplib.SMTPAuthenticationError as exc:
            self.stderr.write(self.style.ERROR(f"SMTP authentication failed: {exc}"))
            raise SystemExit(1) from exc
        except (smtplib.SMTPException, OSError) as exc:
            self.stderr.write(self.style.ERROR(f"SMTP connection error: {exc}"))
            raise SystemExit(1) from exc

        self.stdout.write(self.style.SUCCESS(f"SMTP check passed ({host}:{port})."))
