from django.contrib.auth.views import PasswordResetCompleteView, PasswordResetDoneView
from django.urls import path

from apps.accounts.views import (
    account_lifecycle_view,
    cancel_account_deletion_view,
    RateLimitedLoginView,
    RateLimitedLogoutView,
    RateLimitedPasswordResetView,
    RateLimitedPasswordResetConfirmView,
    reactivate_account_view,
    resend_verification_view,
    signup_view,
    verify_email_view,
)

app_name = "accounts"

urlpatterns = [
    path("", RateLimitedLoginView.as_view(), name="index"),
    path("signup/", signup_view, name="signup"),
    path("login/", RateLimitedLoginView.as_view(), name="login"),
    path("logout/", RateLimitedLogoutView.as_view(), name="logout"),
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
]
