from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import Http404
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.actors.models import Actor
from apps.profiles.forms import ProfileForm, ProfileLinkForm
from apps.profiles.models import Profile, ProfileEditHistory, ProfileLink


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
