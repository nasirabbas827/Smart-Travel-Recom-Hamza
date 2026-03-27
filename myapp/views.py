from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib import messages
from django.contrib.auth.forms import PasswordChangeForm
from .forms import (
    CustomUserChangeForm, ProfileForm, CustomUserCreationForm,
    CustomAuthenticationForm
)
from .models import Profile, Destination, Feedback
import re
from .services import get_destination_weather, get_local_events, get_ai_itinerary_adjustment

# =====================================================
# Auth & Profile Views
# =====================================================

def register_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Registration successful! Please log in.")
            return redirect('user_login')
    else:
        form = CustomUserCreationForm()
    return render(request, 'register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user:
                login(request, user)
                messages.success(request, "Logged in successfully!")
                return redirect('dashboard')  # or 'home' if you prefer
            else:
                form.add_error(None, "Invalid username or password.")
    else:
        form = CustomAuthenticationForm()
    return render(request, 'login.html', {'form': form})


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('user_login')


# =====================================================
# Simple Query Parser
# =====================================================
def parse_query(query):
    if not query:
        return {}

    query_lower = query.lower()

    # Days - more flexible patterns
    days_patterns = [
        r'(\d+)-day',                     # 3-day
        r'(\d+)\s*(?:day|days|d|day trip|days trip)',  # 5 days, 4 day trip
        r'(?:for|over|about|around)\s*(\d+)\s*(?:day|days|d)',  # for 7 days
        r'(\d+)\s*(?:night|nights)',      # sometimes people say nights
    ]
    days = None
    for pat in days_patterns:
        match = re.search(pat, query_lower)
        if match:
            days = int(match.group(1))
            break

    # Budget
    budget_match = re.search(r'(?:under|below|within|budget|max|maximum)\s*([\d,]+)', query_lower)
    budget = int(budget_match.group(1).replace(',', '')) if budget_match else None

    # Region - improved to catch more cases
    region_patterns = [
        r'trip to\s+([a-z\s]+?)(?:\s*(?:under|for|budget|\.|in|valley|$))',
        r'(?:in|to|for)\s+([a-z\s]+?)(?:\s*(?:under|for|budget|\.|trip|$))',
        r'([a-z\s]+?)\s*(?:valley|mountains|region|area|trip)',
    ]
    region = None
    for pat in region_patterns:
        match = re.search(pat, query_lower)
        if match:
            region = match.group(1).strip().title()
            break

    return {
        'days': days,
        'budget': budget,
        'region': region,
    }


# =====================================================
# Recommendation Engine (Content-based scoring)
# =====================================================
def recommend_destinations(user=None, query_params=None):
    destinations = list(Destination.objects.all())
    if not destinations:
        return []

    # Hard filters first
    if query_params:
        if query_params.get('budget'):
            destinations = [d for d in destinations if d.cost <= query_params['budget']]
        if query_params.get('region'):
            reg = query_params['region'].lower()
            destinations = [
                d for d in destinations
                if reg in d.region.lower() or reg in d.name.lower()
            ]

    # User preferences (if logged in)
    user_style = None
    if user and user.is_authenticated and hasattr(user, 'profile'):
        profile = user.profile
        if profile.travel_style:
            user_style = profile.travel_style.lower()

    # Scoring
    scored = []
    for dest in destinations:
        score = 0.0

        # Prefer cheaper within budget
        if dest.cost > 0:
            score += 5000 / (dest.cost + 1)  # avoid division by zero

        # Match travel style strongly
        if user_style and dest.type.lower() == user_style:
            score += 60

        # Bonus for high ratings & safety
        score += float(dest.user_rating) * 12
        score += float(dest.safety_rating) * 8

        scored.append((score, dest))

    # Sort descending by score
    scored.sort(reverse=True, key=lambda x: x[0])

    # If too few results → add popular ones as fallback
    if len(scored) < 6:
        popular = Destination.objects.order_by('-user_rating', '-safety_rating')[:12]
        for dest in popular:
            if dest not in [d for _, d in scored]:
                scored.append((0, dest))
                if len(scored) >= 6:
                    break

    # Take top 6
    return [dest for _, dest in scored][:6]


from django.shortcuts import render
from .models import Destination
from .services import get_destination_weather, get_local_events, get_ai_itinerary_adjustment, geocode_location
from math import radians, sin, cos, sqrt, atan2


# =====================================================
# Distance Calculator (Haversine)
# =====================================================
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in KM
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))

    return round(R * c, 2)


# =====================================================
# Home View (FULL UPDATED)
# =====================================================
def home(request):
    query = request.GET.get('q', '').strip()
    parsed_query = parse_query(query) if query else {}

    # 1. Personalized Greeting
    user_greeting = "Where to next, Explorer?"
    
    if request.user.is_authenticated:
        user_name = request.user.first_name or request.user.username
        
        if query and parsed_query.get('region'):
            user_greeting = f"Great choice, {user_name}! Let's refine your trip to {parsed_query['region']}."
        else:
            user_greeting = f"Welcome back, {user_name}! Ready for your next adventure?"

    # 2. Recommendations
    recommendations = recommend_destinations(
        user=request.user if request.user.is_authenticated else None,
        query_params=parsed_query
    )

    # =====================================================
    # 3. MAP + DISTANCE LOGIC (NEW)
    # =====================================================
    user_lat, user_lng = 24.8607, 67.0011  # Karachi fallback

    map_destinations = []

    for dest in recommendations:
        try:
            lat, lng = geocode_location(dest.name + ", Pakistan")

            if lat and lng:
                distance = calculate_distance(user_lat, user_lng, lat, lng)

                # Optional time estimation
                time_hours = round(distance / 60, 1)

                map_destinations.append({
                    'name': dest.name,
                    'lat': lat,
                    'lng': lng,
                    'cost': dest.cost,
                    'distance': distance,
                    'time': time_hours
                })

        except Exception as e:
            print(f"Map Error for {dest.name}: {e}")

    # =====================================================
    # 4. TOP DESTINATION API DATA
    # =====================================================
    top_destination_data = None
    if recommendations:
        top_dest = recommendations[0]

        weather = get_destination_weather(top_dest.name)
        events = get_local_events(top_dest.name)
        ai_advice = get_ai_itinerary_adjustment(top_dest.name, weather)

        top_destination_data = {
            'destination': top_dest,
            'weather': weather,
            'events': events,
            'ai_advice': ai_advice
        }

    # =====================================================
    # 5. TRAVEL SUGGESTIONS
    # =====================================================
    budget_label = parsed_query.get('budget', 20000)
    suggestions = [
        f"Top Adventure Spots under {budget_label:,} PKR",
        "Best Weekend Getaways from Karachi",
        "Popular Family-Friendly Destinations",
        "Hidden Gems in Northern Pakistan",
    ]

    # =====================================================
    # 6. BUDGET CALCULATION
    # =====================================================
    days = parsed_query.get('days') or 3
    multiplier = max(1, days / 3.0)

    base_hotel = 1000 
    base_travel = 4000
    base_meals = 3000 

    hotel_cost = int(base_hotel * multiplier)
    travel_cost = int(base_travel * multiplier * 0.9)
    meal_cost = int(base_meals * multiplier)
    total_cost = hotel_cost + travel_cost + meal_cost

    # =====================================================
    # 7. CONTEXT
    # =====================================================
    context = {
        'greeting': user_greeting,
        'query': query,
        'parsed_query': parsed_query,
        'recommendations': recommendations,
        'top_destination_data': top_destination_data,
        'travel_suggestions': suggestions,
        'budget_summary': {
            'Hotel': f"{hotel_cost:,}",
            'Travel': f"{travel_cost:,}",
            'Meals': f"{meal_cost:,}",
        },
        'total_budget': f"{total_cost:,}",
        'is_authenticated': request.user.is_authenticated,

        # NEW MAP DATA
        'map_destinations': map_destinations,
        'user_location': {
            'lat': user_lat,
            'lng': user_lng
        }
    }

    return render(request, 'home.html', context)

@login_required
def user_profile(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    user_form = CustomUserChangeForm(instance=request.user)
    profile_form = ProfileForm(instance=profile)

    if request.method == 'POST':
        user_form = CustomUserChangeForm(request.POST, instance=request.user)
        profile_form = ProfileForm(request.POST, instance=profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, "Profile updated successfully!")
            return redirect('user_profile')

    return render(request, 'user_profile.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'profile': profile
    })





@login_required
def feedback_view(request):
    if request.method == 'POST':
        comment = request.POST.get('comment', '').strip()
        rating = request.POST.get('rating')
        if comment and rating:
            Feedback.objects.create(
                user=request.user,
                comment=comment,
                rating=int(rating)
            )
            messages.success(request, "Feedback submitted successfully!")
            return redirect('feedback')
        else:
            messages.error(request, "Please provide both comment and rating.")

    feedback_list = Feedback.objects.all().order_by('-submitted_at')
    return render(request, 'feedback.html', {'feedback_list': feedback_list})


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import random
from .services import (
    get_destination_weather, 
    get_local_events, 
    get_ai_itinerary_adjustment
)


# =====================================================
# Trip Planning View - FULL IMPLEMENTATION
# =====================================================
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import random

from .services import (
    get_destination_weather, 
    get_local_events, 
    get_ai_itinerary_adjustment,
    generate_ai_itinerary
)


@login_required
def plan_trip(request, destination_id):
    """
    Optimized Plan Trip View with Groq AI + Budget & Days awareness
    """
    destination = get_object_or_404(Destination, id=destination_id)
    # Add this in plan_trip view (after destination = get_object_or_404...)

    # Calculate distance from user's location (Karachi)
    user_lat, user_lng = 24.8607, 67.0011  # Karachi

    dest_lat = getattr(destination, 'lat', None)
    dest_lng = getattr(destination, 'lon', None)

    distance_info = None

    if dest_lat and dest_lng:
        distance = calculate_distance(user_lat, user_lng, dest_lat, dest_lng)
        time_hours = round(distance / 60, 1)  # Rough driving time estimate
        
        distance_info = {
            'distance': distance,
            'time': time_hours
        }
    else:
        # Try geocoding if lat/lon not in model
        dest_lat, dest_lng = geocode_location(destination.name + ", Pakistan")
        if dest_lat and dest_lng:
            distance = calculate_distance(user_lat, user_lng, dest_lat, dest_lng)
            distance_info = {
                'distance': distance,
                'time': round(distance / 60, 1)
            }

    # Get days and budget from URL parameters
    try:
        days = int(request.GET.get('days', 3))
        days = max(2, min(days, 10))
    except ValueError:
        days = 3

    # Budget from URL (user can pass ?budget=25000)
    try:
        budget = int(request.GET.get('budget')) if request.GET.get('budget') else None
    except (ValueError, TypeError):
        budget = None

    # Fetch real-time data
    weather = get_destination_weather(destination.name)
    events = get_local_events(destination.name)

    # User profile style
    travel_style = None
    if hasattr(request.user, 'profile') and request.user.profile.travel_style:
        travel_style = request.user.profile.travel_style

    # Groq AI adjustment note
    ai_advice = get_ai_itinerary_adjustment(
        destination_name=destination.name,
        weather_data=weather,
        days=days,
        budget=budget,
        travel_style=travel_style
    )

    # ====================== GROQ AI DYNAMIC ITINERARY ======================
    ai_itinerary_data = generate_ai_itinerary(
        destination_name=destination.name,
        days=days,
        budget=budget,
        travel_style=travel_style,
        destination_type=destination.type
    )

    # Fallback if Groq fails
    if ai_itinerary_data and isinstance(ai_itinerary_data, dict) and 'daily_plan' in ai_itinerary_data:
        itinerary = ai_itinerary_data['daily_plan']
        itinerary_summary = ai_itinerary_data.get('summary', '')
    else:
        itinerary = generate_sample_itinerary(destination, days)
        itinerary_summary = None

    # ====================== BUDGET CALCULATION ======================
    multiplier = days / 3.0
    base_hotel_per_night = 1500 if destination.type.lower() in ['nature', 'adventure', 'mountain'] else 2200
    base_transport = 4500
    base_meals_per_day = 2500
    base_activities = 3200 if 'adventure' in destination.type.lower() else 1800

    hotel_cost = int(base_hotel_per_night * days)
    transport_cost = int(base_transport * (multiplier ** 0.8))
    meals_cost = int(base_meals_per_day * days)
    activities_cost = int(base_activities * multiplier)

    total_cost = hotel_cost + transport_cost + meals_cost + activities_cost
    activities = destination.activities if isinstance(destination.activities, list) else []

    context = {
        'destination': destination,
        'weather': weather,
        'events': events[:6] if events else [],
        'ai_advice': ai_advice,
        'activities': activities,
        'days': days,
        'budget': budget,                    # Passed to template
        'distance_info': distance_info,
        'user_location': {'lat': user_lat, 'lng': user_lng},
        'budget_breakdown': {
            'Accommodation (Hotels/Guesthouses)': f"PKR {hotel_cost:,}",
            'Transportation (Fuel/Tickets)': f"PKR {transport_cost:,}",
            'Meals & Dining': f"PKR {meals_cost:,}",
            'Activities & Entry Fees': f"PKR {activities_cost:,}",
        },
        'total_cost': total_cost,
        'formatted_total': f"PKR {total_cost:,}",
        'budget_warning': total_cost > 60000,
        'itinerary': itinerary,
        'itinerary_summary': itinerary_summary,
    }

    return render(request, 'plan_trip.html', context)

# Keep this as fallback
def generate_sample_itinerary(destination, days):
    """Rule-based fallback itinerary"""
    base_activities = [
        "Arrival + Hotel Check-in + Evening Market Walk",
        "Visit Main Attractions + Photography",
        "Nature/Adventure Activity + Local Cuisine",
        "Cultural Experience + Shopping",
        "Relaxation + Scenic Views",
        "Departure Preparation + Souvenir Shopping"
    ]

    type_specific = {
        'adventure': ["Hiking Trail", "Jeep Safari", "Lake Boating", "Trekking"],
        'nature': ["Valley Exploration", "Waterfall Visit", "Scenic Drive"],
        'family': ["Family Park Visit", "Cultural Show"],
    }

    dest_type = destination.type.lower()
    activity_list = type_specific.get(dest_type, ["Sightseeing", "Local Exploration"])

    itinerary = []
    for day in range(1, days + 1):
        if day == 1:
            title = f"Day {day}: Arrival & Welcome"
            description = base_activities[0]
        elif day == days:
            title = f"Day {day}: Final Exploration & Departure"
            description = base_activities[5] if days > 3 else base_activities[3]
        else:
            title = f"Day {day}: {random.choice(activity_list)}"
            description = random.choice(base_activities[1:5])

        highlight = random.choice(activity_list)

        itinerary.append({
            'day': day,
            'title': title,
            'description': description,
            'highlight': highlight,
            'meals': "Breakfast at hotel, Local lunch, Traditional dinner" if day % 2 == 0 else "Hotel breakfast & dinner"
        })

    return itinerary


from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import SavedItinerary, Destination
import json


@login_required
def my_trips(request):
    """View all saved itineraries of the logged-in user"""
    trips = SavedItinerary.objects.filter(user=request.user).order_by('-created_at')
    
    context = {
        'trips': trips,
    }
    return render(request, 'my_trips.html', context)


@login_required
def save_itinerary(request):
    """Handle saving itinerary from plan_trip page"""
    if request.method == 'POST':
        destination_id = request.POST.get('destination_id')
        days = int(request.POST.get('days', 3))
        total_cost = int(request.POST.get('total_cost', 0))
        title = request.POST.get('title', f'Trip to Destination')

        try:
            destination = Destination.objects.get(id=destination_id)
            
            # Prepare itinerary data from session/context (simplified)
            itinerary_data = {
                "days": days,
                "destination": destination.name,
                "total_cost": total_cost,
                "daily_plan": []  # You can enhance this later with full itinerary
            }

            SavedItinerary.objects.create(
                user=request.user,
                destination=destination,
                title=title,
                days=days,
                itinerary_data=itinerary_data,
                total_estimated_cost=total_cost,
                travel_style=request.user.profile.travel_style if hasattr(request.user, 'profile') else None,
            )

            messages.success(request, f'"{title}" has been saved successfully!')
            return redirect('my_trips')
            
        except Destination.DoesNotExist:
            messages.error(request, "Destination not found.")
            return redirect('home')
        except Exception as e:
            messages.error(request, "Failed to save itinerary. Please try again.")
            return redirect('plan_trip', destination_id=destination_id)

    return redirect('home')


@login_required
def delete_itinerary(request, itinerary_id):
    """Delete a saved itinerary"""
    itinerary = get_object_or_404(SavedItinerary, id=itinerary_id, user=request.user)
    title = itinerary.title
    itinerary.delete()
    messages.success(request, f'"{title}" has been deleted.')
    return redirect('my_trips')


from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import SavedItinerary, Destination
import json

@login_required
def update_itinerary(request, itinerary_id):
    """Manual update of a saved itinerary"""
    itinerary = get_object_or_404(SavedItinerary, id=itinerary_id, user=request.user)

    if request.method == 'POST':
        title = request.POST.get('title', itinerary.title)
        days = int(request.POST.get('days', itinerary.days))
        total_cost = int(request.POST.get('total_cost', itinerary.total_estimated_cost))

        # Update daily plan if provided
        daily_plan_json = request.POST.get('daily_plan', None)
        if daily_plan_json:
            try:
                daily_plan = json.loads(daily_plan_json)
                itinerary.itinerary_data['daily_plan'] = daily_plan
            except json.JSONDecodeError:
                messages.error(request, "Invalid itinerary data. Changes not saved.")

        itinerary.title = title
        itinerary.days = days
        itinerary.total_estimated_cost = total_cost
        itinerary.save()

        messages.success(request, f'Itinerary "{title}" updated successfully!')
        return redirect('my_trips')

    context = {
        'itinerary': itinerary,
        'destination': itinerary.destination,
        'daily_plan': json.dumps(itinerary.itinerary_data.get('daily_plan', [])),  # Pass as JSON string
    }
    return render(request, 'update_itinerary.html', context)