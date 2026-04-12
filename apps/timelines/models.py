import uuid

from django.db import models


class TimelineEntry(models.Model):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	owner = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="timeline_entries")
	post = models.ForeignKey("posts.Post", on_delete=models.CASCADE, related_name="timeline_entries")
	inserted_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		unique_together = ("owner", "post")
		ordering = ["-inserted_at"]

