from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    # User Authentication
    path('register/', views.register_view, name='user_register'),
    path('login/', views.login_view, name='user_login'),
    path('logout/', views.logout_view, name='logout'),
    # Dashboard
    path('', views.home, name='dashboard'),
    path('dashboard/', views.home, name='dashboard'),
    path('feedback/', views.feedback_view, name='feedback'),
    # User Profile 
    path('profile/', views.user_profile, name='user_profile'),
    path('plan-trip/<int:destination_id>/', views.plan_trip, name='plan_trip'),
    path('my-trips/', views.my_trips, name='my_trips'),
    path('save-itinerary/', views.save_itinerary, name='save_itinerary'),
    path('delete-itinerary/<int:itinerary_id>/', views.delete_itinerary, name='delete_itinerary'),
    path('itinerary/update/<int:itinerary_id>/', views.update_itinerary, name='update_itinerary'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
