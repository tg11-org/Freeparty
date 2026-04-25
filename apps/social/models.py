import uuid

from django.db import models

from apps.core.models import TimeStampedModel


class Follow(TimeStampedModel):
	class FollowState(models.TextChoices):
		PENDING = "pending", "Pending"
		ACCEPTED = "accepted", "Accepted"
		REJECTED = "rejected", "Rejected"
		REMOVED = "removed", "Removed"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	follower = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="following_relations")
	followee = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="follower_relations")
	state = models.CharField(max_length=16, choices=FollowState.choices, default=FollowState.PENDING)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["follower", "followee"], name="uniq_follow_relation"),
			models.CheckConstraint(check=~models.Q(follower=models.F("followee")), name="prevent_self_follow"),
		]
		indexes = [models.Index(fields=["followee", "state"])]


class Block(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	blocker = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="blocks_sent")
	blocked = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="blocks_received")

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["blocker", "blocked"], name="uniq_block_relation"),
			models.CheckConstraint(check=~models.Q(blocker=models.F("blocked")), name="prevent_self_block"),
		]


class Mute(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	muter = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="mutes_sent")
	muted = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="mutes_received")

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["muter", "muted"], name="uniq_mute_relation"),
			models.CheckConstraint(check=~models.Q(muter=models.F("muted")), name="prevent_self_mute"),
		]


class Like(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	actor = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="likes")
	post = models.ForeignKey("posts.Post", on_delete=models.CASCADE, related_name="likes")

	class Meta:
		constraints = [models.UniqueConstraint(fields=["actor", "post"], name="uniq_like")]


class Dislike(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	actor = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="dislikes")
	post = models.ForeignKey("posts.Post", on_delete=models.CASCADE, related_name="dislikes")

	class Meta:
		constraints = [models.UniqueConstraint(fields=["actor", "post"], name="uniq_dislike")]


class Repost(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	actor = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="reposts")
	post = models.ForeignKey("posts.Post", on_delete=models.CASCADE, related_name="reposts")

	class Meta:
		constraints = [models.UniqueConstraint(fields=["actor", "post"], name="uniq_repost")]


class Bookmark(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	actor = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="bookmarks")
	post = models.ForeignKey("posts.Post", on_delete=models.CASCADE, related_name="bookmarks")

	class Meta:
		constraints = [models.UniqueConstraint(fields=["actor", "post"], name="uniq_bookmark")]


class HiddenPost(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	actor = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="hidden_posts")
	post = models.ForeignKey("posts.Post", on_delete=models.CASCADE, related_name="hidden_by")

	class Meta:
		constraints = [models.UniqueConstraint(fields=["actor", "post"], name="uniq_hidden_post")]

