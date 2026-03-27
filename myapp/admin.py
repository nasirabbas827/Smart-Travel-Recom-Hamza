from django.contrib import admin
from .models import Profile, Destination, Feedback, SavedItinerary


# ================================
# Profile Admin
# ================================
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'travel_style', 'budget_range', 'duration', 'weather')
    list_filter = ('travel_style', 'budget_range', 'weather')
    search_fields = ('user__username',)
    filter_horizontal = ('preferred_destinations',)

    fieldsets = (
        ("User Info", {
            'fields': ('user',)
        }),
        ("Preferences", {
            'fields': ('travel_style', 'budget_range', 'duration', 'weather')
        }),
        ("Advanced Preferences", {
            'fields': ('preferred_destinations', 'interests')
        }),
    )


# ================================
# Destination Admin
# ================================
@admin.register(Destination)
class DestinationAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'region', 'type', 'cost',
        'weather', 'user_rating', 'safety_rating'
    )
    list_filter = ('type', 'weather', 'region')
    search_fields = ('name', 'region')
    ordering = ('-user_rating',)

    readonly_fields = ('image_preview',)

    fieldsets = (
        ("Basic Info", {
            'fields': ('name', 'region', 'type', 'image', 'image_preview')
        }),
        ("Details", {
            'fields': ('cost', 'weather', 'best_season')
        }),
        ("Ratings", {
            'fields': ('user_rating', 'safety_rating')
        }),
        ("Extras", {
            'fields': ('activities',)
        }),
    )

    def image_preview(self, obj):
        if obj.image:
            return f'<img src="{obj.image.url}" width="100" />'
        return "No Image"
    image_preview.allow_tags = True
    image_preview.short_description = "Preview"


# ================================
# Feedback Admin
# ================================
@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('user', 'rating', 'short_comment', 'submitted_at')
    list_filter = ('rating', 'submitted_at')
    search_fields = ('user__username', 'comment')
    ordering = ('-submitted_at',)

    def short_comment(self, obj):
        return obj.comment[:50] + "..." if len(obj.comment) > 50 else obj.comment
    short_comment.short_description = "Comment"


# ================================
# Saved Itinerary Admin
# ================================
@admin.register(SavedItinerary)
class SavedItineraryAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'user', 'destination',
        'days', 'total_estimated_cost',
        'status', 'created_at'
    )
    list_filter = ('status', 'created_at', 'destination')
    search_fields = ('title', 'user__username', 'destination__name')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    fieldsets = (
        ("Trip Info", {
            'fields': ('title', 'user', 'destination', 'status')
        }),
        ("Schedule", {
            'fields': ('days', 'start_date')
        }),
        ("Budget", {
            'fields': ('total_estimated_cost', 'travel_style')
        }),
        ("Itinerary Data", {
            'fields': ('itinerary_data',)
        }),
        ("Timestamps", {
            'fields': ('created_at', 'updated_at')
        }),
    )

    readonly_fields = ('created_at', 'updated_at')
