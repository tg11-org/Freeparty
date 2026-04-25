from django.contrib import admin

from apps.social.models import Block, Bookmark, Follow, HiddenPost, Like, Mute, Repost


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
	list_display = ("follower", "followee", "state", "created_at")
	list_filter = ("state",)
	search_fields = ("follower__handle", "followee__handle")


admin.site.register(Block)
admin.site.register(Mute)
admin.site.register(Like)
admin.site.register(Repost)
admin.site.register(Bookmark)
admin.site.register(HiddenPost)
