from django.contrib.auth.views import PasswordResetCompleteView, PasswordResetDoneView
from django.urls import path

from apps.accounts.views import (
    account_lifecycle_view,
    cancel_account_deletion_view,
    disable_totp_view,
    enroll_totp_view,
    logged_out_view,
    recovery_codes_view,
    regenerate_recovery_codes_view,
    RateLimitedLoginView,
    RateLimitedLogoutView,
    RateLimitedPasswordResetView,
    RateLimitedPasswordResetConfirmView,
    reactivate_account_view,
    resend_verification_view,
    signup_view,
    totp_confirm_login_view,
    verify_email_view,
)

app_name = "accounts"

urlpatterns = [
    path("", RateLimitedLoginView.as_view(), name="index"),
    path("signup/", signup_view, name="signup"),
    path("login/", RateLimitedLoginView.as_view(), name="login"),
    path("logout/", RateLimitedLogoutView.as_view(), name="logout"),
    path("logged-out/", logged_out_view, name="logged-out"),
    path("manage/", account_lifecycle_view, name="manage"),
    path("recover/reactivate/<str:token>/", reactivate_account_view, name="reactivate-account"),
    path("recover/cancel-delete/<str:token>/", cancel_account_deletion_view, name="cancel-account-deletion"),
    path("password-reset/", RateLimitedPasswordResetView.as_view(), name="password-reset"),
    path("password-reset/done/", PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"), name="password-reset-done"),
    path(
        "password-reset/<uidb64>/<token>/",
        RateLimitedPasswordResetConfirmView.as_view(template_name="accounts/password_reset_confirm.html"),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    path("verify/<str:token>/", verify_email_view, name="verify-email"),
    path("verify/resend/", resend_verification_view, name="resend-verification"),
    path("security/totp/enroll/", enroll_totp_view, name="totp-enroll"),
    path("security/totp/confirm/", totp_confirm_login_view, name="totp-confirm"),
    path("security/totp/disable/", disable_totp_view, name="totp-disable"),
    path("security/totp/recovery-codes/", recovery_codes_view, name="recovery-codes"),
    path("security/totp/recovery-codes/regenerate/", regenerate_recovery_codes_view, name="recovery-codes-regenerate"),
]
