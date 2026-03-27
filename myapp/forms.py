from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import Profile

class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')

    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control mb-3'}))
    first_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control mb-3'}))
    last_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control mb-3'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control mb-3'}))
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control mb-3'}))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control mb-3'}))


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email')

    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control mb-3'}))
    first_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control mb-3'}))
    last_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control mb-3'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control mb-3'}))


class CustomAuthenticationForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control mb-3'}))

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if '@' in username:
            try:
                user = User.objects.get(email=username)
                return user.username
            except User.DoesNotExist:
                raise forms.ValidationError("No user with this email found.")
        return username


from django import forms
from .models import Profile, Destination

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = (
            'budget_range',
            'travel_style',
            'duration',
            'preferred_destinations',
            'interests',
            'weather',
        )
        widgets = {
            'budget_range': forms.Select(attrs={'class': 'form-control mb-3'}),
            'travel_style': forms.Select(attrs={'class': 'form-control mb-3'}),
            'duration': forms.NumberInput(attrs={'class': 'form-control mb-3', 'min': 1}),
            'preferred_destinations': forms.SelectMultiple(attrs={'class': 'form-control mb-3'}),
            'interests': forms.Textarea(attrs={'class': 'form-control mb-3', 'rows': 3, 'placeholder': 'Enter interests as comma separated values'}),
            'weather': forms.Select(attrs={'class': 'form-control mb-3'}),
        }

    def clean_interests(self):
        # Convert comma-separated input into a list
        interests_input = self.cleaned_data.get('interests', '')
        if isinstance(interests_input, str):
            return [item.strip() for item in interests_input.split(',') if item.strip()]
        return interests_input