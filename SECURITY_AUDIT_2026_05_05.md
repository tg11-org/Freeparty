# Freeparty Security Audit - 2026-05-05

Target: https://freeparty.tg11.org  
Codebase: U:\Projects\Freeparty  
Framework: Django 5.x, PostgreSQL, Redis, Celery, Channels, Docker Compose, Apache reverse proxy  

## Executive Summary

No confirmed critical source-code issue was found in this pass. The previous oEmbed XSS, SSRF, direct-message deduplication, and bootstrap hardening work is present in this checkout, but the audit found two high-priority application issues and one high-priority dependency exposure:

| ID | Severity | Area | Finding |
| --- | --- | --- | --- |
| FP-001 | High | SSRF / federation | Redirects are followed before redirect targets are validated in federation fetches and deliveries. |
| FP-002 | High | Broken access control | Comment API does not filter comments by post visibility. |
| FP-003 | High | Supply chain / uploads | Pillow 10.4.0 is vulnerable to multiple 2026 image-processing CVEs while uploads can reach image processing. |
| FP-004 | Medium | Uploads | Post upload validation trusts client MIME type and Apache serves media directly. |
| FP-005 | Medium | Authentication / MFA | TOTP confirmation step has no rate limit. |
| FP-006 | Medium | Authentication | Signup form does not call Django password validators. |
| FP-007 | Medium | SSRF | DNS is validated before `urlopen`, but the actual connection can re-resolve. |
| FP-008 | Medium | Deployment config | ASGI defaults to development settings if `DJANGO_SETTINGS_MODULE` is missing. |
| FP-009 | Medium | Abuse controls | Like action is classified and recorded as a dislike. |
| FP-010 | Medium | Supply chain | Twisted 25.5.0 is flagged for CVE-2026-42304 DoS. |
| FP-011 | Low | Security headers | CSP is report-only by default and allows inline scripts/styles. |
| FP-012 | Low | Operational disclosure | Public readiness endpoints expose database/cache health. |
| FP-013 | Low | XSS hardening | `mark_safe()` in mention linkification is currently escaped, but should stay regression-tested. |
| FP-014 | Low | Configuration | Compose/base settings retain local fallback credentials. |
| FP-015 | Informational | Positive controls | No `csrf_exempt`, unsafe deserialization, dynamic raw SQL, or unauthenticated WebSocket access found. |

## Methodology

- Static review of `apps/`, `config/`, `templates/`, `deploy/`, and `scripts/`.
- Pattern scans for `mark_safe`, `|safe`, `urlopen`, raw SQL, `csrf_exempt`, deserialization, subprocess use, broad exception handling, and hardcoded secrets.
- Live passive checks against `https://freeparty.tg11.org`.
- `bandit -r apps config -x "*/tests.py,*/migrations/*"`.
- `pip-audit -r requirements.txt`.
- `manage.py check --deploy` under production settings with a local SQLite override.

Live observations:

- HTTPS GET `/` returned 200 with `Strict-Transport-Security`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and `Referrer-Policy`.
- HTTP redirects to HTTPS.
- `/.env` returned 404.
- `/health/ready/` and `/api/v1/health/ready/` publicly return database/cache readiness.

## Findings

### FP-001 - Federation redirects can reach unvalidated targets before validation

Severity: High  
OWASP: SSRF, Security Misconfiguration  
Locations:

- `apps/core/network.py:75-90`
- `apps/federation/services.py:28-30`
- `apps/federation/tasks.py:63-69`

Description:

`safe_urlopen(..., allow_redirects=True)` validates the original URL, calls `urllib.request.urlopen()`, and only validates `response.geturl()` after the response object is returned. With urllib's default redirect behavior, the redirected URL has already been requested before that final validation runs.

Proof of concept / attack scenario:

An allowlisted federation instance can return `302 Location: https://127.0.0.1/admin/` or an internal metadata URL. The current helper validates the allowlisted origin, follows the redirect, then rejects the final URL after the internal request has already happened.

Recommended fix:

Do not follow redirects for federation, or implement a redirect handler that validates the `Location` before following.

```diff
diff --git a/apps/federation/services.py b/apps/federation/services.py
@@
-    with safe_urlopen(request, timeout=10, allowed_domain=expected_domain, allow_http=False, allow_redirects=True) as response:
+    with safe_urlopen(request, timeout=10, allowed_domain=expected_domain, allow_http=False, allow_redirects=False) as response:
```

```diff
diff --git a/apps/federation/tasks.py b/apps/federation/tasks.py
@@
-                allow_redirects=True,
+                allow_redirects=False,
```

If redirects are required for federation compatibility, move redirect validation into `HTTPRedirectHandler.redirect_request()` and validate `newurl` before returning a follow-up request.

### FP-002 - Comment API leaks comments across post visibility boundaries

Severity: High  
OWASP: Broken Access Control, IDOR  
Location: `apps/posts/api_views.py:119-128`

Description:

`CommentViewSet.get_queryset()` returns every non-deleted comment and optionally filters by `post_id`. It does not apply the post visibility checks used elsewhere (`can_view_post()` / selectors). Anonymous users can list comments, and authenticated users can query comments for posts they are not allowed to view if they know or guess the post UUID.

Proof of concept / attack scenario:

```http
GET /api/v1/comments/?post=<private-or-followers-only-post-uuid>
```

Expected behavior: 404 or an empty result unless the requester can view the post.  
Current code path: `Comment.objects.filter(deleted_at__isnull=True, post_id=...)`.

Recommended fix:

Create a queryset-level selector for posts visible to the current actor and filter comments by it.

```diff
diff --git a/apps/posts/api_views.py b/apps/posts/api_views.py
@@
-from apps.posts.selectors import visible_public_posts_for_actor
+from apps.posts.selectors import visible_posts_for_actor, visible_public_posts_for_actor
@@
     def get_queryset(self):
-        qs = Comment.objects.filter(deleted_at__isnull=True).select_related("author", "post", "post__author")
+        actor = self.request.user.actor if self.request.user.is_authenticated and hasattr(self.request.user, "actor") else None
+        visible_posts = visible_posts_for_actor(actor)
+        qs = Comment.objects.filter(
+            deleted_at__isnull=True,
+            post__in=visible_posts,
+        ).select_related("author", "post", "post__author")
```

Add a regression test where user B cannot list comments on user A's private or followers-only post.

### FP-003 - Pillow dependency has known high-impact CVEs

Severity: High  
OWASP: Vulnerable and Outdated Components, File Uploads  
Locations:

- `requirements.txt:14`
- Installed package: `pillow==10.4.0`

Description:

`pip-audit` found Pillow 10.4.0 affected by:

- CVE-2026-25990, fixed in 12.1.1
- CVE-2026-40192, fixed in 12.2.0
- CVE-2026-42308, fixed in 12.2.0
- CVE-2026-42310, fixed in 12.2.0
- CVE-2026-42311, fixed in 12.2.0

This matters because Freeparty accepts user media and uses Pillow-adjacent image handling paths. GitHub's Pillow advisories describe OOB writes and decompression-bomb style denial of service in affected versions.

Proof of concept / attack scenario:

An authenticated user uploads a crafted image-like file that reaches image parsing or thumbnail generation. Depending on the image format and code path, this can trigger memory corruption or process-level denial of service.

Recommended fix:

Upgrade Pillow and retest upload/media processing.

```diff
diff --git a/requirements.txt b/requirements.txt
@@
-Pillow>=10.4,<10.5
+Pillow>=12.2,<12.3
```

If the app must remain on older Pillow temporarily, explicitly reject PSD, FITS, PDF, and font formats before any image parsing.

### FP-004 - File upload validation trusts user-supplied MIME type

Severity: Medium  
OWASP: File Upload Vulnerabilities, XSS, DoS  
Locations:

- `apps/posts/forms.py:32-45`
- `apps/posts/api_views.py:57-80`
- `deploy/apache/freeparty.site.conf:34-46`

Description:

Post uploads accept files based on `upload.content_type.startswith("image/")` or `"video/"`. Django's docs warn that uploaded `content_type` is user-supplied and should not be trusted. Apache also serves `/media/` directly, and `LimitRequestBody 0` removes reverse-proxy request size limits.

Proof of concept / attack scenario:

Upload `payload.html` or `payload.svg` while sending `Content-Type: image/png`. The app records it as an image/video attachment. If served directly from `/media/` with an active browser MIME type, it can become stored XSS or a content-sniffing problem. Large crafted files can also stress the app or media processors.

Recommended fix:

Centralize media validation. Enforce extension allowlists, magic-byte validation, generated storage names, and proxy-level request limits.

```diff
diff --git a/apps/posts/forms.py b/apps/posts/forms.py
@@
-        content_type = getattr(upload, "content_type", "") or ""
-        allowed = {"image/", "video/"}
-        if not any(content_type.startswith(prefix) for prefix in allowed):
+        from apps.posts.upload_validation import validate_post_media_upload
+        try:
+            validate_post_media_upload(upload)
+        except ValueError as exc:
+            raise forms.ValidationError(str(exc))
-            raise forms.ValidationError("Only image and video uploads are supported.")
```

```apache
LimitRequestBody 30000000
<Directory /var/www/Freeparty/media>
    Require all granted
    Header set X-Content-Type-Options "nosniff"
    RemoveHandler .php .phtml .phar .cgi .pl .py
</Directory>
```

### FP-005 - TOTP second-factor confirmation is not rate limited

Severity: Medium  
OWASP: Identification and Authentication Failures, Rate Limiting  
Location: `apps/accounts/views.py:415-452`

Description:

The primary login view is rate-limited, but the second-step TOTP confirmation view is not. Once an attacker has a pending MFA session from a valid password, they can repeatedly attempt TOTP or recovery codes.

Proof of concept / attack scenario:

After a password compromise, repeatedly POST to `/accounts/security/totp/confirm/` with 6-digit codes. Without an endpoint-specific throttle, success probability grows with volume.

Recommended fix:

Apply a strict rate limit keyed by session plus IP.

```diff
@@
+@ratelimit(key="ip", rate="10/5m", method="POST", block=True)
 @require_http_methods(["GET", "POST"])
 def totp_confirm_login_view(request: HttpRequest) -> HttpResponse:
```

Also consider invalid-attempt counters stored in the session and clear `_TOTP_PENDING_SESSION_KEY` after too many failures.

### FP-006 - Signup form bypasses configured password validators

Severity: Medium  
OWASP: Identification and Authentication Failures  
Locations:

- `apps/accounts/forms.py:13-31`
- `config/settings/base.py:151-156`

Description:

`AUTH_PASSWORD_VALIDATORS` are configured, but `SignUpForm.clean()` only checks that `password1` and `password2` match. Django documents `validate_password()` for custom password-setting forms.

Proof of concept / attack scenario:

Signup can accept weak passwords like `password`, `12345678`, or a username-similar password if they match in both fields.

Recommended fix:

```diff
diff --git a/apps/accounts/forms.py b/apps/accounts/forms.py
@@
 from django.contrib.auth import get_user_model
+from django.contrib.auth.password_validation import validate_password
@@
         if cleaned_data.get("password1") != cleaned_data.get("password2"):
             raise forms.ValidationError("Passwords do not match.")
+        password = cleaned_data.get("password1")
+        if password:
+            validate_password(password, self.instance)
```

### FP-007 - SSRF DNS validation has a connect-time re-resolution gap

Severity: Medium  
OWASP: SSRF  
Location: `apps/core/network.py:29-93`

Description:

`validate_remote_url()` resolves all A/AAAA records and rejects private/reserved addresses, which is a good improvement over IPv4-only checks. However, `urllib` performs the actual connection after validation and can resolve the hostname again. An attacker controlling DNS can pass validation with a public address, then return a private address on the connection lookup.

Proof of concept / attack scenario:

Attacker-controlled DNS returns a public IP during `socket.getaddrinfo()`, then flips to `127.0.0.1` or `169.254.169.254` before urllib connects.

Recommended fix:

For high-risk fetches, use an HTTP client/transport that pins the validated resolved address for the connection while preserving the original `Host` and TLS SNI, or route remote fetches through an egress proxy with network-level private range blocking. Also keep redirects disabled unless pre-validated.

### FP-008 - ASGI defaults to development settings

Severity: Medium  
OWASP: Security Misconfiguration  
Location: `config/asgi.py:16`

Description:

If `DJANGO_SETTINGS_MODULE` is missing, ASGI boots `config.settings.development`. In a production process manager or container misconfiguration, this can enable development behavior.

Proof of concept / attack scenario:

Start Daphne/ASGI without `DJANGO_SETTINGS_MODULE`. The app imports development settings instead of failing closed.

Recommended fix:

```diff
diff --git a/config/asgi.py b/config/asgi.py
@@
-os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
+os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
```

Alternatively, raise a startup error if the variable is unset outside local development.

### FP-009 - Like action is classified as dislike

Severity: Medium  
OWASP: Security Logging and Monitoring Failures  
Location: `apps/social/views.py:271-288`

Description:

`like_toggle_view()` passes `action_name="dislike"` and calls `ActionVelocityTracker.record_dislike(actor)` when a like is created. This weakens abuse-control classification and makes metrics misleading.

Proof of concept / attack scenario:

A user repeatedly likes posts. Abuse controls and telemetry count those actions as dislikes, which can either over-throttle dislikes or under-observe likes.

Recommended fix:

```diff
@@
-            action_name="dislike",
+            action_name="like",
@@
-        ActionVelocityTracker.record_dislike(actor)
+        ActionVelocityTracker.record_like(actor)
```

### FP-010 - Twisted dependency has CVE-2026-42304

Severity: Medium  
OWASP: Vulnerable and Outdated Components  
Installed package: `Twisted==25.5.0`

Description:

`pip-audit` flagged Twisted 25.5.0 for CVE-2026-42304, fixed in 26.4.0rc2. Twisted's release notes describe a `twisted.names` resource-exhaustion DoS fix during DNS name decompression. Freeparty does not appear to expose a Twisted DNS server directly, so exploitability is lower than the raw dependency alert, but it is still in the deployed Python environment.

Recommended fix:

Upgrade when a stable patched Twisted release is available, or pin to the patched release candidate only if compatible with Daphne/Channels in your stack.

### FP-011 - CSP is report-only and permits inline script/style

Severity: Low  
OWASP: XSS, Security Misconfiguration  
Location: `config/settings/production.py:26-34`

Description:

Production currently sets `CSP_REPORT_ONLY_ENABLED=True` by default and the policy contains `script-src 'self' 'unsafe-inline'` and `style-src 'self' 'unsafe-inline'`. This is understandable with existing inline templates, but it means CSP is not an active mitigation for stored/reflected XSS.

Recommended fix:

Move inline scripts/styles to static files, or use nonces/hashes, then enforce CSP.

```diff
-CSP_REPORT_ONLY_ENABLED = env.bool("CSP_REPORT_ONLY_ENABLED", default=True)
+CSP_REPORT_ONLY_ENABLED = env.bool("CSP_REPORT_ONLY_ENABLED", default=False)
```

### FP-012 - Public readiness endpoints disclose infrastructure health

Severity: Low  
OWASP: Security Misconfiguration  
Locations:

- `apps/core/api_views.py:14-40`
- `apps/core/views.py:103-141`
- Live: `/health/ready/` and `/api/v1/health/ready/`

Description:

Public readiness endpoints return whether database and cache checks pass. This is not a direct compromise, but it gives attackers useful timing and outage information.

Recommended fix:

Keep `/health/live/` public and move detailed readiness behind localhost, an internal reverse-proxy ACL, or staff auth.

### FP-013 - `mark_safe()` remains in mention rendering

Severity: Low  
OWASP: XSS  
Location: `apps/core/templatetags/mention_tags.py:35-75`

Description:

Bandit reports `mark_safe()` at line 75. The current implementation escapes normal text, labels, and generated href values before joining, so this is not an immediate confirmed XSS. The risk is future maintenance drift.

Recommended fix:

Add regression tests with hostile URL, mention, and hashtag payloads. Prefer `format_html()` / `format_html_join()` for generated anchors.

### FP-014 - Local fallback credentials remain in configuration

Severity: Low  
OWASP: Security Misconfiguration  
Locations:

- `compose.yaml:24-26`
- `config/settings/base.py:144-148`

Description:

Local defaults use `freeparty/freeparty` for PostgreSQL. The production checks catch weak `SECRET_KEY` and production origin issues, but not fallback database credentials.

Recommended fix:

Require explicit `POSTGRES_PASSWORD` for non-development compose profiles or add a Django system check for production DB passwords.

### FP-015 - Positive controls and non-findings

Severity: Informational

- CSRF: no `csrf_exempt` usage found in application code.
- Injection: no dynamic raw SQL, `RawSQL`, `.raw()`, or `.extra()` findings found. Health checks use static `SELECT 1`.
- Deserialization: no `pickle` or unsafe `yaml.load()` usage found in application code.
- WebSockets: notification and direct-message consumers close anonymous users; DM sockets check conversation membership before accepting.
- Secrets: `.env` and `.env.remote` exist locally but are not tracked by git; `.dockerignore` excludes `.env` and `.env.*`.
- oEmbed XSS: `apps/posts/tasks.py:149-166` sanitizes provider HTML with `bleach`, only allows iframe markup, strips comments, and blocks `javascript:`, `data:`, and `srcdoc` before `templates/partials/post_card.html:176` renders `embed_html|safe`.

## Dependency Scan Results

`pip-audit -r requirements.txt` found 6 vulnerabilities:

| Package | Installed / constrained | CVE | Fixed |
| --- | --- | --- | --- |
| pillow | 10.4.0 / `>=10.4,<10.5` | CVE-2026-25990 | 12.1.1 |
| pillow | 10.4.0 / `>=10.4,<10.5` | CVE-2026-40192 | 12.2.0 |
| pillow | 10.4.0 / `>=10.4,<10.5` | CVE-2026-42308 | 12.2.0 |
| pillow | 10.4.0 / `>=10.4,<10.5` | CVE-2026-42310 | 12.2.0 |
| pillow | 10.4.0 / `>=10.4,<10.5` | CVE-2026-42311 | 12.2.0 |
| twisted | 25.5.0 | CVE-2026-42304 | 26.4.0rc2 |

`bandit` found:

- Medium: `apps/core/templatetags/mention_tags.py:75` - `mark_safe()`.
- Low: `apps/core/test_browser_smoke.py:76` - hardcoded test token in test code.

## OWASP Top 10 Coverage

| OWASP category | Result |
| --- | --- |
| A01 Broken Access Control | FP-002 comment API visibility issue. Most HTML views and DM views use object checks. |
| A02 Cryptographic Failures | No direct crypto secret exposure found. E2E DM key flows were not cryptographically audited. |
| A03 Injection | No dynamic SQL or command injection found. XSS risks covered in FP-004, FP-011, FP-013. |
| A04 Insecure Design | Federation redirect handling and public readiness disclosure need tighter design boundaries. |
| A05 Security Misconfiguration | FP-008, FP-011, FP-012, FP-014. |
| A06 Vulnerable Components | FP-003 and FP-010. |
| A07 Identification/Auth Failures | FP-005 and FP-006. |
| A08 Software/Data Integrity Failures | No unsafe deserialization found. Federation signature behavior should be reviewed for raw payload canonicalization. |
| A09 Logging/Monitoring Failures | FP-009. Broad exception catches in health/task paths should continue to log safely. |
| A10 SSRF | FP-001 and FP-007. Link unfurling uses guarded fetches with redirects disabled. |

## Deployment Safety Notes

- `git status --short` was clean before this report file was added.
- `manage.py check --deploy` passed when explicit production-safe values were supplied:
  - `DJANGO_SETTINGS_MODULE=config.settings.production`
  - `ALLOWED_HOSTS=freeparty.tg11.org`
  - `CSRF_TRUSTED_ORIGINS=https://freeparty.tg11.org`
  - `CORS_ALLOWED_ORIGINS=https://freeparty.tg11.org`
  - `DATABASE_URL=sqlite:///test-security.sqlite3`
- The same check failed against the local `.env` because local values included production-incompatible host/origin settings. Since `.env` is untracked, verify the remote server `.env` before restarting production.

## References

- Django password validation docs: https://docs.djangoproject.com/en/5.1/topics/auth/passwords/
- Django deployment checklist: https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/
- Django uploaded file docs: https://docs.djangoproject.com/en/dev/ref/files/uploads/
- Pillow CVE-2026-25990 advisory: https://github.com/python-pillow/Pillow/security/advisories/GHSA-cfh3-3jmp-rvhc
- Pillow CVE-2026-40192 advisory: https://github.com/python-pillow/Pillow/security/advisories/GHSA-whj4-6x5x-4v2j
- Pillow CVE-2026-42311 advisory: https://github.com/python-pillow/Pillow/security/advisories/GHSA-pwv6-vv43-88gr
- Pillow 12.2.0 release notes: https://pillow.readthedocs.io/en/latest/releasenotes/12.2.0.html
- Twisted 26.4.0rc2 release notes: https://github.com/twisted/twisted/releases/tag/twisted-26.4.0rc2
