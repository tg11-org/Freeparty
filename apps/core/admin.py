from django.contrib import admin

from apps.core.models import AsyncTaskExecution, AsyncTaskFailure


class ImmutableAdminMixin:
	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False


@admin.register(AsyncTaskExecution)
class AsyncTaskExecutionAdmin(ImmutableAdminMixin, admin.ModelAdmin):
	list_display = ("task_name", "status", "attempt_count", "correlation_id", "created_at", "completed_at")
	list_filter = ("status", "task_name")
	search_fields = ("task_name", "idempotency_key", "task_id", "correlation_id")
	readonly_fields = (
		"id",
		"task_name",
		"idempotency_key",
		"task_id",
		"correlation_id",
		"status",
		"attempt_count",
		"payload",
		"last_error",
		"last_traceback",
		"completed_at",
		"created_at",
		"updated_at",
	)


@admin.register(AsyncTaskFailure)
class AsyncTaskFailureAdmin(ImmutableAdminMixin, admin.ModelAdmin):
	list_display = ("task_name", "is_terminal", "attempt", "max_retries", "correlation_id", "created_at")
	list_filter = ("is_terminal", "task_name")
	search_fields = ("task_name", "task_id", "idempotency_key", "correlation_id", "error_message")
	readonly_fields = (
		"id",
		"task_name",
		"task_id",
		"correlation_id",
		"idempotency_key",
		"attempt",
		"max_retries",
		"is_terminal",
		"error_message",
		"traceback",
		"payload",
		"created_at",
		"updated_at",
	)

# Register your models here.
