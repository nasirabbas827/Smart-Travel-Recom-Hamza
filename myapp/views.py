from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.forms import PasswordChangeForm
from .forms import (
    CustomUserChangeForm, ProfileForm, CustomUserCreationForm,
    CustomAuthenticationForm
)
from .models import Profile, Destination, Feedback, SavedItinerary
import re, json, random
from .services import (
    get_destination_weather, get_local_events,
    get_ai_itinerary_adjustment, geocode_location,
    generate_ai_itinerary
)
from math import radians, sin, cos, sqrt, atan2


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
                return redirect('dashboard')
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

    days_patterns = [
        r'(\d+)-day',
        r'(\d+)\s*(?:day|days|d|day trip|days trip)',
        r'(?:for|over|about|around)\s*(\d+)\s*(?:day|days|d)',
        r'(\d+)\s*(?:night|nights)',
    ]
    days = None
    for pat in days_patterns:
        match = re.search(pat, query_lower)
        if match:
            days = int(match.group(1))
            break

    budget_match = re.search(r'(?:under|below|within|budget|max|maximum)\s*([\d,]+)', query_lower)
    budget = int(budget_match.group(1).replace(',', '')) if budget_match else None

    region_patterns = [
        r'trip to\s+([a-z\s]+?)(?:\s*(?:under|for|budget|\.|in|valley|$))',
        r'(?:in|to|for)\s+([a-z\s]+?)(?:\s*(?:under|for|budget|\.|trip|$))',
        r'([a-z\s]+?)\s*(?:valley|mountains|region|area|trip)',
    ]
    region = None
    for pat in region_patterns:
        match = re.search(pat, query_lower)
        if match:
            candidate = match.group(1).strip().title()
            # Filter out stop words that aren't real regions
            stop_words = {'A', 'An', 'The', 'My', 'Our', 'Your'}
            if candidate not in stop_words and len(candidate) > 2:
                region = candidate
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
    user_weather_pref = None
    if user and user.is_authenticated and hasattr(user, 'profile'):
        profile = user.profile
        if profile.travel_style:
            user_style = profile.travel_style.lower()
        if profile.weather:
            user_weather_pref = profile.weather

    # Scoring
    scored = []
    for dest in destinations:
        score = 0.0

        # Prefer cheaper within budget
        if dest.cost > 0:
            score += 5000 / (dest.cost + 1)

        # Match travel style strongly
        if user_style and dest.type.lower() == user_style:
            score += 60

        # Match weather preference
        if user_weather_pref and dest.weather == user_weather_pref:
            score += 20

        # Bonus for high ratings & safety
        score += float(dest.user_rating) * 12
        score += float(dest.safety_rating) * 8

        scored.append((score, dest))

    scored.sort(reverse=True, key=lambda x: x[0])

    # Cold-start fallback for new/anonymous users with no matches
    if len(scored) < 6:
        popular = Destination.objects.order_by('-user_rating', '-safety_rating')[:12]
        existing_ids = {d.id for _, d in scored}
        for dest in popular:
            if dest.id not in existing_ids:
                scored.append((0, dest))
                existing_ids.add(dest.id)
                if len(scored) >= 6:
                    break

    return [dest for _, dest in scored][:6]


# =====================================================
# Distance Calculator (Haversine)
# =====================================================
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return round(R * c, 2)


# =====================================================
# Home View
# =====================================================
def home(request):
    query = request.GET.get('q', '').strip()
    parsed_query = parse_query(query) if query else {}

    # 1. Personalized Greeting
    if request.user.is_authenticated:
        user_name = request.user.first_name or request.user.username
        if query and parsed_query.get('region'):
            user_greeting = f"Great choice, {user_name}! Let's map out your trip to {parsed_query['region']}."
        else:
            user_greeting = f"Welcome back, {user_name}! Ready for your next adventure?"
    else:
        user_greeting = "Where to next, Explorer?"

    # 2. Recommendations
    recommendations = recommend_destinations(
        user=request.user if request.user.is_authenticated else None,
        query_params=parsed_query
    )

    # 3. Map + Distance Logic
    user_lat, user_lng = 24.8607, 67.0011  # Karachi fallback
    map_destinations = []

    for dest in recommendations:
        try:
            lat, lng = geocode_location(dest.name + ", Pakistan")
            if lat and lng:
                distance = calculate_distance(user_lat, user_lng, lat, lng)
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

    # 4. Top Destination API Data
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

    # 5. Personalized Travel Suggestions
    budget_label = parsed_query.get('budget', 20000)
    if request.user.is_authenticated and hasattr(request.user, 'profile'):
        style = request.user.profile.travel_style or 'adventure'
        suggestions = [
            f"Top {style.title()} Spots under PKR {budget_label:,}",
            "Best Weekend Getaways from Karachi",
            "Popular Family-Friendly Destinations",
            "Hidden Gems in Northern Pakistan",
        ]
    else:
        suggestions = [
            "Ideal Weekend Destinations This Month",
            f"Best Budget Trips under PKR {budget_label:,}",
            "Top-Rated Adventure Places Near You",
            "Hidden Gems in Northern Pakistan",
        ]

    # 6. Budget Calculation
    days = parsed_query.get('days') or 3
    multiplier = max(1, days / 3.0)
    base_hotel = 1000
    base_travel = 4000
    base_meals = 3000
    hotel_cost = int(base_hotel * multiplier)
    travel_cost = int(base_travel * multiplier * 0.9)
    meal_cost = int(base_meals * multiplier)
    total_cost = hotel_cost + travel_cost + meal_cost

    # 7. Budget warning — compare against user's query budget if provided
    query_budget = parsed_query.get('budget')
    budget_exceeded = query_budget and total_cost > query_budget

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
        'budget_exceeded': budget_exceeded,
        'query_budget': f"{query_budget:,}" if query_budget else None,
        'is_authenticated': request.user.is_authenticated,
        'map_destinations': map_destinations,
        'user_location': {'lat': user_lat, 'lng': user_lng},
        # Cold-start indicator for template
        'is_cold_start': not request.user.is_authenticated or (
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            not request.user.profile.travel_style
        ),
    }

    return render(request, 'home.html', context)


# =====================================================
# User Profile View
# =====================================================
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


# =====================================================
# Feedback View
# =====================================================
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


# =====================================================
# Trip Planning View
# =====================================================
@login_required
def plan_trip(request, destination_id):
    destination = get_object_or_404(Destination, id=destination_id)

    # Distance from user's location (Karachi)
    user_lat, user_lng = 24.8607, 67.0011
    dest_lat = getattr(destination, 'lat', None)
    dest_lng = getattr(destination, 'lon', None)
    distance_info = None

    if dest_lat and dest_lng:
        distance = calculate_distance(user_lat, user_lng, dest_lat, dest_lng)
        distance_info = {'distance': distance, 'time': round(distance / 60, 1)}
    else:
        dest_lat, dest_lng = geocode_location(destination.name + ", Pakistan")
        if dest_lat and dest_lng:
            distance = calculate_distance(user_lat, user_lng, dest_lat, dest_lng)
            distance_info = {'distance': distance, 'time': round(distance / 60, 1)}

    # Days and Budget from URL parameters
    try:
        days = int(request.GET.get('days', 3))
        days = max(2, min(days, 10))
    except ValueError:
        days = 3

    try:
        budget = int(request.GET.get('budget')) if request.GET.get('budget') else None
    except (ValueError, TypeError):
        budget = None

    # Fetch real-time data
    weather = get_destination_weather(destination.name)
    events = get_local_events(destination.name)

    # User profile travel style
    travel_style = None
    if hasattr(request.user, 'profile') and request.user.profile.travel_style:
        travel_style = request.user.profile.travel_style

    # AI adjustment note
    ai_advice = get_ai_itinerary_adjustment(
        destination_name=destination.name,
        weather_data=weather,
        days=days,
        budget=budget,
        travel_style=travel_style
    )

    # Groq AI Dynamic Itinerary
    ai_itinerary_data = generate_ai_itinerary(
        destination_name=destination.name,
        days=days,
        budget=budget,
        travel_style=travel_style,
        destination_type=destination.type
    )

    if ai_itinerary_data and isinstance(ai_itinerary_data, dict) and 'daily_plan' in ai_itinerary_data:
        itinerary = ai_itinerary_data['daily_plan']
        itinerary_summary = ai_itinerary_data.get('summary', '')
        ai_generated = True
    else:
        itinerary = generate_sample_itinerary(destination, days)
        itinerary_summary = None
        ai_generated = False

    # Budget Calculation
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

    # Budget warning: compare against user's budget if provided
    budget_warning = budget and total_cost > budget

    activities = destination.activities if isinstance(destination.activities, list) else []

    context = {
        'destination': destination,
        'weather': weather,
        'events': events[:6] if events else [],
        'ai_advice': ai_advice,
        'activities': activities,
        'days': days,
        'budget': budget,
        'distance_info': distance_info,
        'dest_lat': dest_lat or 34.5,
        'dest_lng': dest_lng or 73.2,
        'user_location': {'lat': user_lat, 'lng': user_lng},
        'budget_breakdown': {
            'Accommodation (Hotels/Guesthouses)': f"PKR {hotel_cost:,}",
            'Transportation (Fuel/Tickets)': f"PKR {transport_cost:,}",
            'Meals & Dining': f"PKR {meals_cost:,}",
            'Activities & Entry Fees': f"PKR {activities_cost:,}",
        },
        'total_cost': total_cost,
        'formatted_total': f"PKR {total_cost:,}",
        'budget_warning': budget_warning,
        'itinerary': itinerary,
        'itinerary_summary': itinerary_summary,
        'ai_generated': ai_generated,
    }

    return render(request, 'plan_trip.html', context)


# =====================================================
# Fallback Itinerary Generator
# =====================================================
def generate_sample_itinerary(destination, days):
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
        'historical': ["Museum Tour", "Heritage Walk", "Ruins Exploration"],
        'romantic': ["Scenic Viewpoint Visit", "Candlelight Dinner", "Sunset Cruise"],
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
            'activities': activity_list[:3],
            'meals': "Breakfast at hotel, Local lunch, Traditional dinner" if day % 2 == 0 else "Hotel breakfast & dinner",
            'tips': f"Carry cash and wear comfortable shoes for Day {day}."
        })

    return itinerary


# =====================================================
# My Trips View
# =====================================================
@login_required
def my_trips(request):
    trips = SavedItinerary.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'my_trips.html', {'trips': trips})


@login_required
def save_itinerary(request):
    if request.method == 'POST':
        destination_id = request.POST.get('destination_id')
        days = int(request.POST.get('days', 3))
        total_cost = int(request.POST.get('total_cost', 0))
        title = request.POST.get('title', 'Trip to Destination')

        try:
            destination = Destination.objects.get(id=destination_id)
            itinerary_data = {
                "days": days,
                "destination": destination.name,
                "total_cost": total_cost,
                "daily_plan": []
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
    itinerary = get_object_or_404(SavedItinerary, id=itinerary_id, user=request.user)
    title = itinerary.title
    itinerary.delete()
    messages.success(request, f'"{title}" has been deleted.')
    return redirect('my_trips')


@login_required
def update_itinerary(request, itinerary_id):
    itinerary = get_object_or_404(SavedItinerary, id=itinerary_id, user=request.user)

    if request.method == 'POST':
        title = request.POST.get('title', itinerary.title)
        days = int(request.POST.get('days', itinerary.days))
        total_cost = int(request.POST.get('total_cost', itinerary.total_estimated_cost))

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
        'daily_plan': json.dumps(itinerary.itinerary_data.get('daily_plan', [])),
    }
    return render(request, 'update_itinerary.html', context)