from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.profiles.forms import ProfileForm
from apps.profiles.models import Profile, ProfileEditHistory


@login_required
@require_http_methods(["GET", "POST"])
def edit_profile_view(request: HttpRequest) -> HttpResponse:
	actor = getattr(request.user, "actor", None)
	if actor is None:
		messages.error(request, "No actor linked to your account.")
		return redirect("home")
	profile, _ = Profile.objects.get_or_create(actor=actor)

	form = ProfileForm(request.POST or None, request.FILES or None, instance=profile)
	if request.method == "POST" and form.is_valid():
		previous_bio = profile.bio
		previous_location = profile.location
		previous_website_url = profile.website_url
		changed_fields = set(form.changed_data)
		updated_profile = form.save()
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
		messages.success(request, "Profile updated.")
		return redirect("actors:detail", handle=actor.handle)

	return render(request, "profiles/edit.html", {"form": form, "profile": profile})
