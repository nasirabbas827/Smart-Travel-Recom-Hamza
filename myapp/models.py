from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):
    TRAVEL_STYLE_CHOICES = [
        ('adventure', 'Adventure'),
        ('nature', 'Nature'),
        ('luxury', 'Luxury'),
        ('historical', 'Historical'),
        ('family', 'Family'),
        ('solo', 'Solo'),
        ('romantic', 'Romantic'),
    ]

    BUDGET_CHOICES = [
        ('economy', 'Economy'),
        ('standard', 'Standard'),
        ('premium', 'Premium'),
    ]
    
    WEATHER_CHOICES = (
        ('Cold', 'Cold'),
        ('Warm', 'Warm'),
        ('Moderate', 'Moderate'),
        ('Hot', 'Hot'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    budget_range = models.CharField(max_length=20, choices=BUDGET_CHOICES , default='Standard')
    travel_style = models.CharField(max_length=20, choices=TRAVEL_STYLE_CHOICES, null=True, blank=True)
    duration = models.PositiveIntegerField(null=True, blank=True, help_text="Duration in days")
    preferred_destinations = models.ManyToManyField('Destination', blank=True)
    interests = models.JSONField(default=list, blank=True)
    weather = models.CharField(max_length=20, choices=WEATHER_CHOICES , default='Cold')

    def __str__(self):
        return f"{self.user.username}'s Profile"
    

# ---------------------------
# Destination Model
# ---------------------------
class Destination(models.Model):
    TRAVEL_TYPE_CHOICES = (
        ('Adventure', 'Adventure'),
        ('Relaxation', 'Relaxation'),
        ('Family', 'Family'),
        ('Cultural', 'Cultural'),
        ('Historical', 'Historical'),
        ('Romantic', 'Romantic'),
        ('Other', 'Other'),
    )

    WEATHER_CHOICES = (
        ('Cold', 'Cold'),
        ('Warm', 'Warm'),
        ('Moderate', 'Moderate'),
        ('Hot', 'Hot'),
    )

    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=TRAVEL_TYPE_CHOICES)
    region = models.CharField(max_length=100) 
    cost = models.PositiveIntegerField(help_text="Average trip cost in PKR")
    weather = models.CharField(max_length=20, choices=WEATHER_CHOICES)
    best_season = models.CharField(max_length=50)
    activities = models.JSONField(default=list, blank=True)
    safety_rating = models.DecimalField(max_digits=2, decimal_places=1)
    user_rating = models.DecimalField(max_digits=2, decimal_places=1)
    image = models.ImageField(upload_to='destinations/', null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.region})"
    

class Feedback(models.Model):
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]  # 1 to 5 stars

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='feedbacks')
    comment = models.TextField()
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.rating}/5)"


class SavedItinerary(models.Model):
    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_itineraries')
    destination = models.ForeignKey(Destination, on_delete=models.CASCADE)
    
    title = models.CharField(max_length=200, help_text="Custom name for this trip")
    days = models.PositiveIntegerField(default=3)
    
    # Store the full itinerary as JSON for flexibility
    itinerary_data = models.JSONField(default=dict, blank=True, 
                                     help_text="Day-by-day itinerary details")
    
    total_estimated_cost = models.PositiveIntegerField(help_text="Total cost in PKR")
    travel_style = models.CharField(max_length=50, null=True, blank=True)
    
    start_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Saved Itinerary"
        verbose_name_plural = "Saved Itineraries"

    def __str__(self):
        return f"{self.title} - {self.destination.name} ({self.days} days)"

    def get_itinerary_summary(self):
        """Helper to get a short summary"""
        if self.itinerary_data and 'daily_plan' in self.itinerary_data:
            return f"{len(self.itinerary_data['daily_plan'])} days planned"
        return f"{self.days} days"