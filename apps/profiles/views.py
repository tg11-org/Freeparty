from datetime import timedelta
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.core.mail import send_mail
from django.http import Http404
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.actors.models import Actor
from apps.profiles.forms import GuardianMinorSettingsForm, ProfileForm, ProfileLinkForm
from apps.profiles.models import (
	GuardianEmailVerificationToken,
	GuardianManagementAccessToken,
	ParentalControlChangeRequest,
	Profile,
	ProfileEditHistory,
	ProfileLink,
)


TOKEN_TTL_HOURS = 24
MANAGEMENT_LINK_TTL_HOURS = 24 * 7
PROTECTED_PARENTAL_FIELDS = {
	"is_private_account",
	"auto_reveal_spoilers",
	"show_follower_count",
	"show_following_count",
}
LOCK_CONFIGURATION_FIELDS = {"is_minor_account", "parental_controls_enabled", "guardian_email"}
BASIC_PROFILE_FIELDS = {"bio", "website_url", "location"}


def _issue_guardian_management_access(profile: Profile) -> GuardianManagementAccessToken:
	token = secrets.token_urlsafe(32)
	return GuardianManagementAccessToken.objects.create(
		profile=profile,
		guardian_email=profile.guardian_email,
		token=token,
		expires_at=timezone.now() + timedelta(hours=MANAGEMENT_LINK_TTL_HOURS),
	)


def _issue_guardian_verification(request: HttpRequest, profile: Profile) -> None:
	if not profile.guardian_email:
		return
	token = secrets.token_urlsafe(32)
	verification = GuardianEmailVerificationToken.objects.create(
		profile=profile,
		guardian_email=profile.guardian_email,
		token=token,
		expires_at=timezone.now() + timedelta(hours=TOKEN_TTL_HOURS),
	)
	verify_path = reverse("profiles:verify_guardian_email", kwargs={"token": verification.token})
	verify_url = request.build_absolute_uri(verify_path)
	child_handle = profile.actor.handle
	send_mail(
		subject="Freeparty guardian email verification",
		message=(
			f"A Freeparty account (@{child_handle}) added this address as a guardian contact.\n\n"
			f"Verify this guardian email by visiting: {verify_url}\n\n"
			"After verification, you will be redirected to the guardian controls page where you can set age details and content permissions.\n\n"
			"If you did not expect this request, you can ignore this email."
		),
		from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
		recipient_list=[profile.guardian_email],
		fail_silently=True,
	)


def initialize_minor_profile_for_signup(request: HttpRequest, profile: Profile, guardian_email: str) -> None:
	profile.is_minor_account = True
	profile.parental_controls_enabled = True
	profile.guardian_email = guardian_email.strip().lower()
	profile.guardian_email_verified_at = None
	profile.save(update_fields=["is_minor_account", "parental_controls_enabled", "guardian_email", "guardian_email_verified_at", "updated_at"])
	_issue_guardian_verification(request, profile)


def _issue_parental_change_approval(request: HttpRequest, profile: Profile, requested_by, cleaned_data: dict) -> None:
	token = secrets.token_urlsafe(32)
	approval = ParentalControlChangeRequest.objects.create(
		profile=profile,
		requested_by=requested_by,
		guardian_email=profile.guardian_email,
		token=token,
		expires_at=timezone.now() + timedelta(hours=TOKEN_TTL_HOURS),
		proposed_is_private_account=bool(cleaned_data.get("is_private_account")),
		proposed_auto_reveal_spoilers=bool(cleaned_data.get("auto_reveal_spoilers")),
		proposed_show_follower_count=bool(cleaned_data.get("show_follower_count")),
		proposed_show_following_count=bool(cleaned_data.get("show_following_count")),
		proposed_is_minor_account=bool(cleaned_data.get("is_minor_account")),
		proposed_parental_controls_enabled=bool(cleaned_data.get("parental_controls_enabled")),
		proposed_guardian_email=(cleaned_data.get("guardian_email") or "").strip(),
		proposed_bio=(cleaned_data.get("bio") or "").strip(),
		proposed_location=(cleaned_data.get("location") or "").strip(),
		proposed_website_url=(cleaned_data.get("website_url") or "").strip(),
	)
	approve_path = reverse("profiles:approve_parental_change", kwargs={"token": approval.token})
	approve_url = request.build_absolute_uri(approve_path)
	child_handle = profile.actor.handle
	send_mail(
		subject="Freeparty parental controls change approval",
		message=(
			f"A protected settings change was requested for Freeparty account @{child_handle}.\n\n"
			f"Review and approve this change: {approve_url}\n\n"
			"If this request is unexpected, ignore this email and no changes will be applied."
		),
		from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
		recipient_list=[profile.guardian_email],
		fail_silently=True,
	)


def _is_non_minor_guardian_user(user) -> bool:
	if not getattr(user, "is_authenticated", False):
		return False
	if not user.email:
		return False
	actor = getattr(user, "actor", None)
	if actor is None:
		return False
	profile, _ = Profile.objects.get_or_create(actor=actor)
	return not profile.is_minor_account


def _guardian_can_manage_profile(user, profile: Profile) -> bool:
	if not _is_non_minor_guardian_user(user):
		return False
	if not profile.guardian_email or not profile.guardian_email_verified_at:
		return False
	return bool(user.email and user.email.lower() == profile.guardian_email.lower())


def _guardian_request_ready(profile: Profile) -> bool:
	return bool(profile.is_minor_account and profile.guardian_email)


def _locked_fields_for_profile(profile: Profile) -> set[str]:
	if not _guardian_request_ready(profile):
		return set()

	locked_fields = set()
	if profile.guardian_locks_account_protection:
		locked_fields.update(LOCK_CONFIGURATION_FIELDS)

	# Minor account safety defaults: these visibility/content fields require guardian approval
	# whenever a guardian email is configured for a minor account, regardless of toggle position.
	if profile.is_minor_account or profile.guardian_locks_visibility_settings:
		locked_fields.update(PROTECTED_PARENTAL_FIELDS)

	if profile.guardian_locks_basic_profile:
		locked_fields.update(BASIC_PROFILE_FIELDS)

	return locked_fields


@login_required
@require_http_methods(["GET", "POST"])
def edit_profile_view(request: HttpRequest) -> HttpResponse:
	actor = getattr(request.user, "actor", None)
	if actor is None:
		messages.error(request, "No actor linked to your account.")
		return redirect("home")
	profile, _ = Profile.objects.get_or_create(actor=actor)

	form = ProfileForm(request.POST or None, request.FILES or None, instance=profile)
	can_manage_linked_minors = _is_non_minor_guardian_user(request.user)
	if request.method == "POST" and form.is_valid():
		locked_changes_queued = False
		restricted_fields = _locked_fields_for_profile(profile)
		guardian_approval_possible = bool(profile.guardian_email)
		previous_bio = profile.bio
		previous_location = profile.location
		previous_website_url = profile.website_url
		changed_fields = set(form.changed_data)
		locked_field_changes = {
			field_name
			for field_name in restricted_fields
			if field_name in form.cleaned_data and form.cleaned_data.get(field_name) != getattr(profile, field_name)
		}
		updated_profile = form.save(commit=False)

		if "guardian_email" in changed_fields and "guardian_email" not in restricted_fields:
			updated_profile.guardian_email_verified_at = None

		if guardian_approval_possible and locked_field_changes:
			for field_name in locked_field_changes:
				setattr(updated_profile, field_name, getattr(profile, field_name))
			updated_profile.guardian_email_verified_at = profile.guardian_email_verified_at
			locked_changes_queued = True

		updated_profile.save()

		if "guardian_email" in changed_fields and not locked_changes_queued and updated_profile.guardian_email:
			_issue_guardian_verification(request, updated_profile)
			messages.info(request, "Guardian verification email sent. Parental lock activates after verification.")

		if locked_changes_queued:
			_issue_parental_change_approval(request, updated_profile, request.user, form.cleaned_data)
			messages.warning(
				request,
				"Protected settings were not changed yet. A guardian approval email was sent.",
			)

		if {"bio", "location", "website_url"}.intersection(changed_fields):
			ProfileEditHistory.objects.create(
				profile=updated_profile,
				editor=request.user,
				previous_bio=previous_bio,
				new_bio=updated_profile.bio,
				previous_location=previous_location,
				new_location=updated_profile.location,
				previous_website_url=previous_website_url,
				new_website_url=updated_profile.website_url,
			)
		if locked_changes_queued:
			messages.success(request, "Profile updated. Guardian approval is pending for protected changes.")
		else:
			messages.success(request, "Profile updated.")
		return redirect("actors:detail", handle=actor.handle)

	return render(
		request,
		"profiles/edit.html",
		{
			"form": form,
			"profile": profile,
			"can_manage_linked_minors": can_manage_linked_minors,
		},
	)


@require_http_methods(["GET"])
def verify_guardian_email_view(request: HttpRequest, token: str) -> HttpResponse:
	token_obj = GuardianEmailVerificationToken.objects.select_related("profile", "profile__actor").filter(token=token).first()
	if token_obj is None or not token_obj.is_usable:
		messages.error(request, "Guardian verification link is invalid or expired.")
		return redirect("home")

	profile = token_obj.profile
	if not profile.guardian_email or profile.guardian_email.lower() != token_obj.guardian_email.lower():
		messages.error(request, "Guardian verification link is no longer valid for the current guardian email.")
		return redirect("home")

	now = timezone.now()
	token_obj.used_at = now
	token_obj.save(update_fields=["used_at", "updated_at"])
	profile.guardian_email_verified_at = now
	profile.save(update_fields=["guardian_email_verified_at", "updated_at"])
	manage_token = _issue_guardian_management_access(profile)

	messages.success(request, f"Guardian email verified for @{profile.actor.handle}.")
	return redirect("profiles:guardian_manage", token=manage_token.token)


@require_http_methods(["GET", "POST"])
def approve_parental_change_view(request: HttpRequest, token: str) -> HttpResponse:
	change_request = ParentalControlChangeRequest.objects.select_related("profile", "profile__actor").filter(token=token).first()
	if change_request is None or not change_request.is_usable:
		messages.error(request, "Parental approval link is invalid or expired.")
		return redirect("home")

	profile = change_request.profile
	if not profile.guardian_email or profile.guardian_email.lower() != change_request.guardian_email.lower():
		messages.error(request, "Parental approval link is no longer valid for the current guardian email.")
		return redirect("home")

	if request.method == "GET":
		current_values = {
			"is_private_account": profile.is_private_account,
			"auto_reveal_spoilers": profile.auto_reveal_spoilers,
			"show_follower_count": profile.show_follower_count,
			"show_following_count": profile.show_following_count,
			"is_minor_account": profile.is_minor_account,
			"parental_controls_enabled": profile.parental_controls_enabled,
			"guardian_email": profile.guardian_email,
			"bio": profile.bio,
			"location": profile.location,
			"website_url": profile.website_url,
		}
		proposed_values = {
			"is_private_account": change_request.proposed_is_private_account,
			"auto_reveal_spoilers": change_request.proposed_auto_reveal_spoilers,
			"show_follower_count": change_request.proposed_show_follower_count,
			"show_following_count": change_request.proposed_show_following_count,
			"is_minor_account": change_request.proposed_is_minor_account,
			"parental_controls_enabled": change_request.proposed_parental_controls_enabled,
			"guardian_email": change_request.proposed_guardian_email,
			"bio": change_request.proposed_bio,
			"location": change_request.proposed_location,
			"website_url": change_request.proposed_website_url,
		}
		return render(
			request,
			"profiles/guardian_approval_review.html",
			{
				"profile": profile,
				"change_request": change_request,
				"current_values": current_values,
				"proposed_values": proposed_values,
			},
		)

	now = timezone.now()
	profile.is_private_account = change_request.proposed_is_private_account
	profile.auto_reveal_spoilers = change_request.proposed_auto_reveal_spoilers
	profile.show_follower_count = change_request.proposed_show_follower_count
	profile.show_following_count = change_request.proposed_show_following_count
	profile.is_minor_account = change_request.proposed_is_minor_account
	profile.parental_controls_enabled = change_request.proposed_parental_controls_enabled
	profile.bio = change_request.proposed_bio
	profile.location = change_request.proposed_location
	profile.website_url = change_request.proposed_website_url
	guardian_email_changed = profile.guardian_email != change_request.proposed_guardian_email
	profile.guardian_email = change_request.proposed_guardian_email
	if guardian_email_changed:
		profile.guardian_email_verified_at = None
	profile.save(
		update_fields=[
			"is_private_account",
			"auto_reveal_spoilers",
			"show_follower_count",
			"show_following_count",
			"is_minor_account",
			"parental_controls_enabled",
			"bio",
			"location",
			"website_url",
			"guardian_email",
			"guardian_email_verified_at",
			"updated_at",
		],
	)

	change_request.used_at = now
	change_request.save(update_fields=["used_at", "updated_at"])

	if guardian_email_changed and profile.guardian_email:
		_issue_guardian_verification(request, profile)
		messages.info(request, "Guardian email changed. A new verification email was sent.")

	messages.success(request, f"Parental controls update approved for @{profile.actor.handle}.")
	return redirect("home")


@require_http_methods(["GET", "POST"])
def guardian_manage_minor_view(request: HttpRequest, token: str) -> HttpResponse:
	access = GuardianManagementAccessToken.objects.select_related("profile", "profile__actor").filter(token=token).first()
	if access is None or not access.is_usable:
		messages.error(request, "Guardian management link is invalid or expired.")
		return redirect("home")

	profile = access.profile
	if not profile.guardian_email or profile.guardian_email.lower() != access.guardian_email.lower():
		messages.error(request, "Guardian management link is no longer valid for the current guardian email.")
		return redirect("home")

	form = GuardianMinorSettingsForm(request.POST or None, profile=profile)
	if request.method == "POST" and form.is_valid():
		profile = form.apply(profile)
		profile.save(
			update_fields=[
				"minor_birthdate_precision",
				"minor_age_range",
				"minor_age_years",
				"minor_age_recorded_at",
				"minor_birth_year",
				"minor_birth_month",
				"minor_birth_day",
				"guardian_allows_nsfw_underage",
				"guardian_allows_16plus_underage",
				"guardian_locks_basic_profile",
				"guardian_locks_visibility_settings",
				"guardian_locks_account_protection",
				"guardian_restrict_dms_to_teens",
				"updated_at",
			],
		)
		messages.success(request, f"Guardian settings saved for @{profile.actor.handle}.")
		return redirect("profiles:guardian_manage", token=access.token)

	return render(
		request,
		"profiles/guardian_manage.html",
		{
			"form": form,
			"profile": profile,
			"access": access,
			"back_to_guardian_minors": False,
		},
	)


@login_required
@require_http_methods(["GET"])
def guardian_linked_minors_view(request: HttpRequest) -> HttpResponse:
	if not _is_non_minor_guardian_user(request.user):
		messages.error(request, "Guardian account access requires a non-minor account.")
		return redirect("profiles:edit")

	linked_profiles = Profile.objects.select_related("actor").filter(
		is_minor_account=True,
		guardian_email__iexact=request.user.email,
		guardian_email_verified_at__isnull=False,
	).order_by("actor__handle")

	return render(
		request,
		"profiles/guardian_linked_minors.html",
		{
			"linked_profiles": linked_profiles,
		},
	)


@login_required
@require_http_methods(["GET", "POST"])
def guardian_manage_linked_minor_view(request: HttpRequest, profile_id) -> HttpResponse:
	profile = get_object_or_404(Profile.objects.select_related("actor"), id=profile_id)
	if not _guardian_can_manage_profile(request.user, profile):
		messages.error(request, "You are not allowed to manage this minor profile.")
		return redirect("profiles:guardian_minors")

	form = GuardianMinorSettingsForm(request.POST or None, profile=profile)
	if request.method == "POST" and form.is_valid():
		profile = form.apply(profile)
		profile.save(
			update_fields=[
				"minor_birthdate_precision",
				"minor_age_range",
				"minor_age_years",
				"minor_age_recorded_at",
				"minor_birth_year",
				"minor_birth_month",
				"minor_birth_day",
				"guardian_allows_nsfw_underage",
				"guardian_allows_16plus_underage",
				"guardian_locks_basic_profile",
				"guardian_locks_visibility_settings",
				"guardian_locks_account_protection",
				"guardian_restrict_dms_to_teens",
				"updated_at",
			],
		)
		messages.success(request, f"Guardian settings saved for @{profile.actor.handle}.")
		return redirect("profiles:guardian_manage_linked_minor", profile_id=profile.id)

	return render(
		request,
		"profiles/guardian_manage.html",
		{
			"form": form,
			"profile": profile,
			"access": None,
			"back_to_guardian_minors": True,
		},
	)


@login_required
@require_http_methods(["GET", "POST"])
def edit_profile_links_view(request: HttpRequest) -> HttpResponse:
	actor = getattr(request.user, "actor", None)
	if actor is None:
		messages.error(request, "No actor linked to your account.")
		return redirect("home")

	profile, _ = Profile.objects.get_or_create(actor=actor)
	if request.method == "POST" and request.POST.get("action") == "delete":
		link_id = request.POST.get("link_id", "")
		ProfileLink.objects.filter(id=link_id, profile=profile).delete()
		messages.success(request, "Link removed.")
		return redirect("profiles:links_edit")

	if request.method == "POST":
		form = ProfileLinkForm(request.POST)
		if form.is_valid():
			link = form.save(commit=False)
			link.profile = profile
			if link.display_order == 0:
				max_order = profile.links.aggregate(max_order=Max("display_order"))["max_order"] or 0
				link.display_order = max_order + 1
			link.save()
			messages.success(request, "Link added.")
			return redirect("profiles:links_edit")
	else:
		form = ProfileLinkForm()

	links = profile.links.all()
	return render(
		request,
		"profiles/edit_links.html",
		{
			"profile": profile,
			"form": form,
			"links": links,
			"public_link_page_url": f"/profiles/{actor.handle}/links/",
		},
	)


@require_http_methods(["GET"])
def public_profile_links_view(request: HttpRequest, handle: str) -> HttpResponse:
	actor = get_object_or_404(Actor.objects.all(), handle=handle, state=Actor.ActorState.ACTIVE)
	profile = Profile.objects.filter(actor=actor).first()
	if profile is None:
		raise Http404("Profile not found")

	links = profile.links.filter(is_active=True)
	return render(
		request,
		"profiles/links_page.html",
		{
			"actor": actor,
			"profile": profile,
			"links": links,
		},
	)
