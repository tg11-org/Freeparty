# Freeparty Security Re-Audit - 2026-05-06

Target: https://freeparty.tg11.org  
Codebase: U:\Projects\Freeparty  
Scope: follow-up audit after remediation of `SECURITY_AUDIT_2026_05_05.md`

## Summary

The previous Critical/High application findings appear remediated in the current checkout. No new Critical or High application vulnerability was confirmed in this follow-up pass.

| ID | Severity | Area | Status |
| --- | --- | --- | --- |
| RE-001 | Medium | Supply chain | Twisted CVE-2026-42304 remains open, intentionally noted in `requirements.txt`. |
| RE-002 | Resolved | Verification | `apps/accounts/tests.py` now compiles and the account/auth security slice passes. |
| RE-003 | Resolved | Verification | Federation tests now patch `safe_fetch` and the federation inbound fetch slice passes. |
| RE-004 | Low | XSS hardening | `mark_safe()` remains in mention linkification; current escaping is defensive, but Bandit still flags it. |
| RE-005 | Resolved | Operational disclosure | `/health/` remains public but now exposes only a generic overall status (no component-level DB/cache details); readiness JSON remains protected. |
| RE-006 | Resolved | Raw SQL/deprecation | Staff security dashboard aggregation now uses ORM `TruncDate` instead of `.extra(...)`. |

## Remediation Verification

### Previously High: federation redirect SSRF

Status: addressed.

Evidence:

- `apps/federation/services.py:29-37` now calls `safe_fetch(...)`.
- `apps/federation/tasks.py:57-65` now calls `safe_fetch(...)`.
- `apps/core/network.py:129-157` uses `httpx.Client(..., follow_redirects=False)`.
- `apps/core/network.py:83-126` implements an IP-pinned transport for the actual connection.

Smoke checks:

- `safe_fetch("https://example.com/")` returned HTTP 200.
- `safe_fetch("http://127.0.0.1/")` raised `UnsafeRemoteURL`.
- `safe_fetch("http://169.254.169.254/")` raised `UnsafeRemoteURL`.
- `safe_fetch("file:///etc/passwd")` raised `UnsafeRemoteURL`.

Residual note:

`safe_urlopen()` still has an `allow_redirects=True` branch at `apps/core/network.py:172-176`. Current app scans did not find active callers using `allow_redirects=True`, but future code should use `safe_fetch()` instead or remove that branch.

### Previously High: comment API visibility/IDOR

Status: addressed in source.

Evidence:

- `apps/posts/selectors.py:10-40` adds `visible_posts_for_actor()`.
- `apps/posts/api_views.py:113-120` filters `CommentViewSet` comments through `visible_posts_for_actor(actor=actor)`.
- Regression tests exist at `apps/posts/tests.py:313` and `apps/posts/tests.py:327`.

Live note:

`/api/v1/comments/` is still public for comments on visible posts, which is expected. This passive check cannot prove private-post comment hiding without authenticated private test data, but the source-level query now enforces visibility.

### Previously High: Pillow vulnerable dependency

Status: addressed in requirements.

Evidence:

- `requirements.txt:15` now pins `Pillow>=12.2,<12.3`.
- `pip-audit -r requirements.txt` no longer reports Pillow CVEs.

### Previously Medium: upload MIME trust

Status: addressed with residual hardening opportunity.

Evidence:

- `apps/posts/upload_validation.py:44-70` centralizes extension, size, client MIME family, and magic-byte validation.
- `apps/posts/forms.py:38-45` uses `validate_post_media_upload()`.
- `apps/posts/api_views.py:56-69` uses `validate_post_media_upload()` and stores canonical MIME types.
- `deploy/apache/freeparty.site.conf:34` sets `LimitRequestBody 30000000`.
- `deploy/apache/freeparty.site.conf:46-47` adds `X-Content-Type-Options: nosniff` and removes executable handlers under media.

Residual note:

This validates signatures but does not re-encode uploaded images or transcode videos. For stronger media isolation, re-encode images server-side and serve downloads from a cookieless media domain.

### Previously Medium: TOTP brute force window

Status: addressed.

Evidence:

- `apps/accounts/views.py:415` adds `@ratelimit(key="ip", rate="10/5m", method="POST", block=True)` to the TOTP confirm view.

### Previously Medium: signup password validators

Status: addressed.

Evidence:

- `apps/accounts/forms.py:4` imports `validate_password`.
- `apps/accounts/forms.py:30-32` calls `validate_password(password, self.instance)`.

### Previously Medium: ASGI development default

Status: addressed.

Evidence:

- `config/asgi.py:16` now defaults to `config.settings.production`.

### Previously Medium: like telemetry classified as dislike

Status: addressed.

Evidence:

- `apps/social/views.py:273` now uses `action_name="like"`.
- `apps/social/views.py:288` now calls `ActionVelocityTracker.record_like(actor)`.

### Previously Low: CSP report-only / inline policy

Status: improved on live site.

Evidence:

- Live responses now include enforced `Content-Security-Policy`, not only report-only.
- Live policy observed: `default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; img-src 'self' data: https:; object-src 'none'; script-src 'self'; style-src 'self'`.

Source note:

- `config/settings/production.py:27-30` keeps a `legacy-report-only` default unless production env selects stricter rollout mode. The live site appears configured stricter than the source default.

### Previously Low: public readiness detail

Status: mostly addressed.

Evidence:

- Live `/health/ready/` returns 404.
- Live `/api/v1/health/ready/` returns 404.
- `apps/core/views.py:112-114` and `apps/core/api_views.py:18-20` call `is_ready_endpoint_authorized()`.
- `config/settings/production.py:33` defaults `HEALTH_READY_PUBLIC=False`.

Residual:

- `/health/` remains public by design but now exposes only generic overall status, reducing operational detail leakage.

## Current Findings

### RE-001 - Twisted CVE-2026-42304 remains open

Severity: Medium  
Location: `requirements.txt:16-17`  
OWASP: Vulnerable and Outdated Components

Description:

`pip-audit -r requirements.txt` reports one remaining advisory:

```text
twisted 25.5.0  CVE-2026-42304  26.4.0rc2
```

The requirement file explicitly notes this exception because the fixed version is a release candidate rather than a stable release.

Proof of concept / attack scenario:

The Twisted release notes describe a `twisted.names` resource-exhaustion DoS fix. I did not find Freeparty exposing Twisted DNS directly, so practical exploitability looks lower than a network-facing DNS service, but the vulnerable package remains in the environment through the async stack.

Recommended fix:

Keep the current note, monitor Twisted stable releases, then upgrade when a stable fixed version compatible with Daphne/Channels is available.

```diff
-# FP-010: Twisted CVE-2026-42304 fixed in 26.4.0rc2 (not yet on stable PyPI as of 2026-05-06).
+# TODO: Upgrade Twisted to the first stable release containing the CVE-2026-42304 fix.
```

### RE-002 - Account/auth test file had a syntax error

Status: Resolved  
Location: `apps/accounts/tests.py:322-330`  
OWASP: Security Logging and Monitoring Failures / verification gap

Description:

`apps/accounts/tests.py` was syntactically invalid. The method `test_under_18_signup_requires_guardian_email` started a POST payload and was cut off before `class ResendVerificationViewTests` began. This is now fixed.

Verification:

```text
python -m py_compile apps\accounts\tests.py apps\federation\tests.py apps\posts\tests.py apps\core\tests.py
OK
```

### RE-003 - Federation tests mocked the old network path

Status: Resolved  
Location: `apps/federation/tests.py:103,118,150,168,188`  
OWASP: SSRF verification gap

Description:

Federation services now use `safe_fetch()`/`httpx`; tests previously patched `apps.federation.services.urllib.request.urlopen`, which no longer intercepted network calls. The tests now patch `safe_fetch` and return `httpx.Response` objects.

Verification:

```text
python manage.py test apps.federation.tests.FederationInboundFetchTests
Ran 6 tests
OK
```

### RE-004 - `mark_safe()` remains in mention linkification

Severity: Low  
Location: `apps/core/templatetags/mention_tags.py:35-75`  
OWASP: XSS

Description:

Bandit still flags `mark_safe()` at line 75. The implementation escapes text, URLs, handles, and hashtags before joining, and tests include hostile HTML escaping coverage, so this is a low residual risk.

Recommended fix:

Prefer `format_html()` / `format_html_join()` when the helper is next touched, or suppress Bandit with the correct B703 nosec marker after review.

### RE-005 - Public `/health/` page disclosure reduced

Status: Resolved  
Locations:

- `templates/core/health_status.html`
- live `/health/`

Description:

The public HTML health page now shows only a general service summary and no longer discloses component-level database/cache status. Readiness JSON remains protected.

Verification:

```http
GET https://freeparty.tg11.org/health/
```

Expected: generic overall service status only (no DB/cache breakdown).

### RE-006 - Legacy `.extra()` usage in staff security dashboard

Status: Resolved  
Locations:

- `apps/core/views.py:290`
- `apps/core/views.py:425`

Description:

Daily aggregation in staff security dashboards now uses ORM `TruncDate`, removing legacy `.extra()` usage.

Verification:

```text
SecurityAuditEvent queryset now uses .annotate(day=TruncDate("created_at"))
```

## Scanner Results

### Bandit

Command:

```powershell
.\.venv\Scripts\python.exe -m bandit -r apps config -x "*/tests.py,*/migrations/*" -f txt
```

Results:

- Medium: `apps/core/templatetags/mention_tags.py:75` - `mark_safe()`.
- Low: `apps/core/test_browser_smoke.py:76` - hardcoded test token in test code.
- No High findings.

### pip-audit

Command:

```powershell
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt
```

Results:

- One finding: `twisted 25.5.0`, `CVE-2026-42304`, fixed in `26.4.0rc2`.
- No Pillow findings remain.

### Django deploy check

Command:

```powershell
$env:DATABASE_URL='sqlite:///test-security.sqlite3'
$env:DJANGO_SETTINGS_MODULE='config.settings.production'
$env:ALLOWED_HOSTS='freeparty.tg11.org'
$env:CSRF_TRUSTED_ORIGINS='https://freeparty.tg11.org'
$env:CORS_ALLOWED_ORIGINS='https://freeparty.tg11.org'
.\.venv\Scripts\python.exe manage.py check --deploy
```

Result:

```text
System check identified no issues (0 silenced).
```

### Test verification

Passed:

- `python -m py_compile apps\accounts\tests.py apps\federation\tests.py apps\posts\tests.py apps\core\tests.py`
- `manage.py test apps.federation.tests.FederationInboundFetchTests apps.accounts.tests.SignupLegalConsentTests apps.accounts.tests.RecoveryCodeFlowTests apps.posts.tests.CommentApiParityTests apps.core.tests.MentionAndHashtagLinkifyTests apps.core.tests.RootPathAndHealthStatusTests apps.core.tests.SecurityHeadersMiddlewareTests` ran 43 tests and passed.
- `manage.py check --deploy` passed with production-safe env overrides.
- Live HTTPS headers include enforced CSP, HSTS, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and `Referrer-Policy`.
- Live `/.env` returns 404.
- Live `/health/ready/` returns 404.
- Live `/api/v1/health/ready/` returns 404.
- `safe_fetch()` blocks loopback, metadata host, and non-HTTP schemes.

## OWASP Follow-Up

| OWASP category | Re-audit result |
| --- | --- |
| A01 Broken Access Control | Previous comment API issue appears fixed in source. |
| A02 Cryptographic Failures | No new issue found in this pass. E2E cryptography was not deeply reviewed. |
| A03 Injection | No user-controlled raw SQL found. Legacy `.extra()` usage was removed from staff dashboard aggregation. |
| A04 Insecure Design | Public `/health/` now presents only generic overall service status without component-level detail. |
| A05 Security Misconfiguration | ASGI default and readiness endpoint defaults improved. Live CSP is enforced. |
| A06 Vulnerable Components | Twisted remains open; Pillow is addressed. |
| A07 Identification/Auth Failures | TOTP throttling and password validators are addressed. Auth security tests now compile and pass. |
| A08 Software/Data Integrity Failures | No unsafe deserialization found. |
| A09 Logging/Monitoring Failures | Like/dislike telemetry fixed. Security-adjacent test slices now pass. |
| A10 SSRF | Federation now uses `safe_fetch` and no redirects. Federation tests now patch the correct network helper and pass. |

## References

- Twisted 26.4.0rc2 release notes: https://github.com/twisted/twisted/releases/tag/twisted-26.4.0rc2
- Django deployment checklist: https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/
- Django password validation: https://docs.djangoproject.com/en/5.1/topics/auth/passwords/
- Django file upload docs: https://docs.djangoproject.com/en/dev/ref/files/uploads/

