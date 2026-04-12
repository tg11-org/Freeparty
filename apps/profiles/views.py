from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.profiles.forms import ProfileForm
from apps.profiles.models import Profile


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
		form.save()
		messages.success(request, "Profile updated.")
		return redirect("actors:detail", handle=actor.handle)

	return render(request, "profiles/edit.html", {"form": form, "profile": profile})
