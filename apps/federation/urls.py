from django.urls import path

from apps.federation.views import inbox

app_name = "federation"

urlpatterns = [
	path("inbox/", inbox, name="inbox"),
]