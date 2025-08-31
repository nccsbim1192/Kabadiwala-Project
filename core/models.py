from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
import os


def user_profile_image_path(instance, filename):
    """Generate file path for user profile images based on role"""
    # Get file extension
    ext = filename.split('.')[-1]
    # Create filename: username.extension
    filename = f"{instance.username}.{ext}"
    # Return path: images/role/filename
    return os.path.join('images', instance.role, filename)


class User(AbstractUser):
    ROLE_CHOICES = (
        ('customer', 'Customer'),
        ('collector', 'Collector'),
        ('admin', 'Admin'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='customer')
    phone = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    profile_image = models.ImageField(upload_to=user_profile_image_path, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class WasteCategory(models.Model):
    name = models.CharField(max_length=50, unique=True)
    rate_per_kg = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Waste Categories"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - Rs.{self.rate_per_kg}/kg"


class PickupRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('assigned', 'Assigned to Collector'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
        ('rescheduled', 'Rescheduled'),
    )
    
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pickup_requests')
    collector = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, 
                                related_name='assigned_pickups')
    waste_category = models.ForeignKey(WasteCategory, on_delete=models.CASCADE)
    estimated_weight_kg = models.DecimalField(max_digits=8, decimal_places=2, 
                                            validators=[MinValueValidator(0.1), MaxValueValidator(1000)])
    actual_weight_kg = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True,
                                         validators=[MinValueValidator(0.1), MaxValueValidator(1000)])
    pickup_date = models.DateField()
    pickup_time = models.TimeField()
    address = models.TextField()
    special_instructions = models.TextField(blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Add calculated price fields
    estimated_price = models.DecimalField(max_digits=10, decimal_places=2, editable=False, default=0)
    actual_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, editable=False)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        from decimal import Decimal
        
        # Calculate estimated price
        self.estimated_price = self.estimated_weight_kg * self.waste_category.rate_per_kg
        
        # Calculate actual price if actual weight is provided
        if self.actual_weight_kg:
            # Ensure actual_weight_kg is a Decimal for calculation
            if isinstance(self.actual_weight_kg, str):
                self.actual_weight_kg = Decimal(self.actual_weight_kg)
            self.actual_price = self.actual_weight_kg * self.waste_category.rate_per_kg
            
        # Set completed_at when status changes to completed
        if self.status == 'completed' and not self.completed_at:
            self.completed_at = timezone.now()
        
        super().save(*args, **kwargs)

    def get_estimated_price(self):
        """Method to get estimated price (for compatibility)"""
        return self.estimated_weight_kg * self.waste_category.rate_per_kg

    def get_actual_price(self):
        """Method to get actual price (for compatibility)"""
        if self.actual_weight_kg:
            return self.actual_weight_kg * self.waste_category.rate_per_kg
        return Decimal('0.00')

    def __str__(self):
        return f"{self.customer.username} - {self.waste_category.name} - {self.status}"


class Transaction(models.Model):
    pickup_request = models.OneToOneField(PickupRequest, on_delete=models.CASCADE)
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='customer_transactions')
    collector = models.ForeignKey(User, on_delete=models.CASCADE, related_name='collector_transactions')
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    collector_commission = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    
    payment_method = models.CharField(max_length=20, default='cash')
    payment_gateway = models.CharField(max_length=20, blank=True)
    gateway_transaction_id = models.CharField(max_length=100, blank=True)
    gateway_response = models.JSONField(blank=True, null=True)
    payment_status = models.CharField(max_length=20, default='pending')
    
    transaction_date = models.DateTimeField(auto_now_add=True)
    is_paid = models.BooleanField(default=False)

    class Meta:
        ordering = ['-transaction_date']

    def save(self, *args, **kwargs):
        from decimal import Decimal
        # Ensure amount is a Decimal
        if not isinstance(self.amount, Decimal):
            self.amount = Decimal(str(self.amount))
        # Calculate 10% commission for collector
        self.collector_commission = (self.amount * Decimal('0.10')).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Transaction for {self.pickup_request} - Rs.{self.amount}"


# Alias for compatibility with views.py
class EnvironmentalImpact(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    total_weight_recycled = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    trees_saved = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    co2_reduced = models.DecimalField(max_digits=8, decimal_places=2, default=0)  # in kg
    water_saved = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # in liters
    last_updated = models.DateTimeField(auto_now=True)

    def calculate_impact(self):
        """Calculate environmental impact based on completed pickups"""
        completed_pickups = PickupRequest.objects.filter(
            customer=self.user, 
            status='completed',
            actual_weight_kg__isnull=False
        )
        
        total_weight = sum(pickup.actual_weight_kg for pickup in completed_pickups)
        self.total_weight_recycled = total_weight
        
        # Environmental impact calculations (approximate formulas)
        self.trees_saved = total_weight * Decimal('0.017')  # 1kg paper = 0.017 trees saved
        self.co2_reduced = total_weight * Decimal('0.82')   # 1kg recycled = 0.82kg CO2 saved
        self.water_saved = total_weight * Decimal('13.2')   # 1kg recycled = 13.2L water saved
        
        self.save()

    def update_impact(self):
        """Alias for calculate_impact for backward compatibility"""
        self.calculate_impact()

    def __str__(self):
        return f"Environmental Impact for {self.user.username}"


# Keep the RecyclingImpact model as an alias for compatibility
RecyclingImpact = EnvironmentalImpact
