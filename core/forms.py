from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from datetime import date, datetime, time
from .models import User, PickupRequest, WasteCategory
import re


class CustomUserCreationForm(UserCreationForm):
    # Define role choices excluding admin - only customer and collector allowed for public registration
    PUBLIC_ROLE_CHOICES = [
        ('customer', 'Customer'),
        ('collector', 'Collector'),
    ]
    
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    phone = forms.CharField(max_length=15, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    address = forms.CharField(widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}), required=False)
    role = forms.ChoiceField(choices=PUBLIC_ROLE_CHOICES, widget=forms.Select(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ('username', 'email', 'phone', 'address', 'role', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs['class'] = 'form-control'
        self.fields['password2'].widget.attrs['class'] = 'form-control'
        self.fields['username'].help_text = 'Required. Letters and special characters only (no digits allowed).'

    def clean_username(self):
        username = self.cleaned_data['username']
        
        # Remove all digits from the username
        username_no_digits = ''.join([c for c in username if not c.isdigit()])
        
        # Check if username still has characters after removing digits
        if not username_no_digits:
            raise ValidationError("Username must contain at least one non-digit character.")
            
        # Check for minimum length after digit removal
        if len(username_no_digits) < 2:
            raise ValidationError("Username must have at least 2 characters (excluding digits).")
            
        return username_no_digits

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.phone = self.cleaned_data['phone']
        user.address = self.cleaned_data['address']
        user.role = self.cleaned_data['role']
        if commit:
            user.save()
        return user


class PickupRequestForm(forms.ModelForm):
    """Form for customers to request waste pickup"""
    
    class Meta:
        model = PickupRequest
        fields = [
            'waste_category',
            'estimated_weight_kg',
            'pickup_date',
            'pickup_time',
            'address',
            'special_instructions'
        ]
        
        widgets = {
            'waste_category': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'estimated_weight_kg': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.1',
                'min': '0.1',
                'max': '1000',
                'placeholder': 'Enter weight in kg',
                'required': True
            }),
            'pickup_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'required': True
            }),
            'pickup_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time',
                'required': True
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter your complete pickup address with landmarks',
                'required': True
            }),
            'special_instructions': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Any special instructions for the collector (optional)'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Ensure only active waste categories are shown
        self.fields['waste_category'].queryset = WasteCategory.objects.filter(is_active=True).order_by('name')
        
        # Set minimum date to today
        today = date.today()
        self.fields['pickup_date'].widget.attrs['min'] = today.isoformat()
        
        # Add helpful labels
        self.fields['waste_category'].label = "Waste Category"
        self.fields['estimated_weight_kg'].label = "Estimated Weight (kg)"
        self.fields['pickup_date'].label = "Pickup Date"
        self.fields['pickup_time'].label = "Pickup Time"
        self.fields['address'].label = "Pickup Address"
        self.fields['special_instructions'].label = "Special Instructions (Optional)"
        
        # Make special_instructions not required
        self.fields['special_instructions'].required = False
        
        # Add empty label for waste_category
        self.fields['waste_category'].empty_label = "Choose waste category..."
        
        # Create or ensure default waste categories exist
        self._ensure_default_categories()

    def _ensure_default_categories(self):
        """Create default waste categories if they don't exist"""
        default_categories = [
            {'name': 'Paper', 'rate_per_kg': 5.0, 'description': 'Waste paper and cardboard'},
            {'name': 'Plastic', 'rate_per_kg': 10.0, 'description': 'Various plastic wastes'},
            {'name': 'Glass', 'rate_per_kg': 8.0, 'description': 'Glass bottles and jars'},
            {'name': 'Metal', 'rate_per_kg': 15.0, 'description': 'Scrap metal and cans'},
            {'name': 'Electronics', 'rate_per_kg': 20.0, 'description': 'E-waste such as old phones, batteries'},
            {'name': 'Textiles', 'rate_per_kg': 6.0, 'description': 'Old clothes and fabrics'},
            {'name': 'Organic Waste', 'rate_per_kg': 3.0, 'description': 'Biodegradable waste'},
            {'name': 'Wood', 'rate_per_kg': 7.0, 'description': 'Wood and timber waste'},
            {'name': 'Rubber', 'rate_per_kg': 12.0, 'description': 'Scrap rubber and tires'},
            {'name': 'Others', 'rate_per_kg': 2.0, 'description': 'Miscellaneous recyclable materials'},
        ]
        
        for category_data in default_categories:
            WasteCategory.objects.get_or_create(
                name=category_data['name'],
                defaults={
                    'rate_per_kg': category_data['rate_per_kg'],
                    'description': category_data['description'],
                    'is_active': True,
                }
            )

    def clean_pickup_date(self):
        pickup_date = self.cleaned_data.get('pickup_date')
        if pickup_date:
            if pickup_date < date.today():
                raise ValidationError("Pickup date cannot be in the past.")
        return pickup_date

    def clean_pickup_time(self):
        pickup_time = self.cleaned_data.get('pickup_time')
        pickup_date = self.cleaned_data.get('pickup_date')
        
        if pickup_time:
            # Check business hours (9 AM to 6 PM)
            hour = pickup_time.hour
            if hour < 9 or hour > 18:
                raise ValidationError("Pickup time must be between 9:00 AM and 6:00 PM.")
            
            # If pickup is today, check if time is not in the past
            if pickup_date and pickup_date == date.today():
                current_time = datetime.now().time()
                if pickup_time < current_time:
                    raise ValidationError("Pickup time cannot be in the past for today.")
        
        return pickup_time

    def clean_estimated_weight_kg(self):
        weight = self.cleaned_data.get('estimated_weight_kg')
        if weight is not None:
            if weight < 0.1:
                raise ValidationError("Weight must be at least 0.1 kg.")
            if weight > 1000:
                raise ValidationError("Weight cannot exceed 1000 kg.")
        return weight

    def clean_address(self):
        address = self.cleaned_data.get('address')
        if address:
            if len(address.strip()) < 10:
                raise ValidationError("Please provide a more detailed address.")
        return address


class CollectorUpdateForm(forms.ModelForm):
    """Form for collectors to update pickup status and actual weight"""
    
    class Meta:
        model = PickupRequest
        fields = ['actual_weight_kg', 'status']
        
        widgets = {
            'actual_weight_kg': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.1',
                'min': '0.1',
                'max': '1000',
                'placeholder': 'Enter actual weight in kg'
            }),
            'status': forms.Select(attrs={
                'class': 'form-select'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields['actual_weight_kg'].label = "Actual Weight (kg)"
        self.fields['status'].label = "Status"
        
        # Limit status choices for collectors
        STATUS_CHOICES = [
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
        ]
        self.fields['status'].choices = STATUS_CHOICES

    def clean_actual_weight_kg(self):
        weight = self.cleaned_data.get('actual_weight_kg')
        if weight is not None:
            if weight < 0.1:
                raise ValidationError("Actual weight must be at least 0.1 kg.")
            if weight > 1000:
                raise ValidationError("Actual weight cannot exceed 1000 kg.")
        return weight
