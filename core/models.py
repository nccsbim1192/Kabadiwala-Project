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
            if isinstance(self.actual_weight_kg, (str, float, int)):
                self.actual_weight_kg = Decimal(str(self.actual_weight_kg))
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
    PAYMENT_METHOD_CHOICES = (
        ('cash', 'Cash'),
        ('esewa', 'eSewa'),
        ('khalti', 'Khalti'),
        ('ime_pay', 'IME Pay'),
        ('fonepay', 'FonePay'),
        ('bank_transfer', 'Bank Transfer'),
    )
    
    PAYMENT_STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
        ('cancelled', 'Cancelled'),
    )
    
    pickup_request = models.OneToOneField(PickupRequest, on_delete=models.CASCADE)
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='customer_transactions')
    collector = models.ForeignKey(User, on_delete=models.CASCADE, related_name='collector_transactions')
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    collector_commission = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cash')
    payment_gateway = models.CharField(max_length=20, blank=True)
    gateway_transaction_id = models.CharField(max_length=100, blank=True)
    gateway_response = models.JSONField(blank=True, null=True)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    
    # Enhanced payment fields
    payment_initiated_at = models.DateTimeField(null=True, blank=True)
    payment_completed_at = models.DateTimeField(null=True, blank=True)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    refund_reason = models.TextField(blank=True)
    
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


class SMSNotification(models.Model):
    """Model to track SMS notifications sent to users"""
    NOTIFICATION_TYPE_CHOICES = (
        ('pickup_assigned', 'Pickup Assigned'),
        ('pickup_completed', 'Pickup Completed'),
        ('payment_received', 'Payment Received'),
        ('status_update', 'Status Update'),
        ('reminder', 'Reminder'),
        ('welcome', 'Welcome Message'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('delivered', 'Delivered'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sms_notifications')
    pickup_request = models.ForeignKey(PickupRequest, on_delete=models.CASCADE, null=True, blank=True)
    phone_number = models.CharField(max_length=15)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    
    # SMS Gateway fields
    gateway_message_id = models.CharField(max_length=100, blank=True)
    gateway_response = models.JSONField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"SMS to {self.phone_number} - {self.notification_type}"


class CollectorLocation(models.Model):
    """Model to track real-time GPS location of collectors"""
    collector = models.ForeignKey(User, on_delete=models.CASCADE, related_name='locations')
    pickup_request = models.ForeignKey(PickupRequest, on_delete=models.CASCADE, null=True, blank=True)
    
    latitude = models.DecimalField(max_digits=10, decimal_places=8)
    longitude = models.DecimalField(max_digits=11, decimal_places=8)
    accuracy = models.FloatField(help_text="GPS accuracy in meters")
    
    # Location context
    is_active = models.BooleanField(default=True)
    is_at_pickup_location = models.BooleanField(default=False)
    distance_to_pickup = models.FloatField(null=True, blank=True, help_text="Distance in kilometers")
    
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['collector', '-timestamp']),
            models.Index(fields=['pickup_request', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.collector.username} location at {self.timestamp}"
    
    @property
    def google_maps_url(self):
        """Generate Google Maps URL for this location"""
        return f"https://www.google.com/maps?q={self.latitude},{self.longitude}"


class PaymentGatewayLog(models.Model):
    """Model to log all payment gateway interactions"""
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='gateway_logs')
    gateway_name = models.CharField(max_length=50)  # esewa, khalti, etc.
    request_data = models.JSONField()
    response_data = models.JSONField(null=True, blank=True)
    
    status_code = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.gateway_name} log for Transaction #{self.transaction.id}"


class CreditPackage(models.Model):
    """Pre-defined credit packages for collectors to purchase"""
    name = models.CharField(max_length=50)  # "Starter Pack", "Professional Pack"
    purchase_amount = models.DecimalField(max_digits=10, decimal_places=2)  # Amount collector pays
    credit_amount = models.DecimalField(max_digits=10, decimal_places=2)    # Credits they receive
    commission_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0.1000)  # 10%
    
    # Package features
    is_active = models.BooleanField(default=True)
    is_popular = models.BooleanField(default=False)  # Highlight popular packages
    bonus_credits = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Extra credits for promotions
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    @property
    def savings_percentage(self):
        """Calculate how much collector saves vs paying commission per transaction"""
        if self.purchase_amount > 0:
            from decimal import Decimal
            return float((self.purchase_amount - self.credit_amount) / self.purchase_amount) * 100
        return 0
    
    def __str__(self):
        return f"{self.name} - Pay Rs.{self.purchase_amount}, Get Rs.{self.credit_amount}"


class CollectorCreditAccount(models.Model):
    """Credit account for each collector"""
    collector = models.OneToOneField(User, on_delete=models.CASCADE, related_name='credit_account')
    current_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_purchased = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Lifetime purchases
    total_used = models.DecimalField(max_digits=10, decimal_places=2, default=0)      # Lifetime usage
    
    # Account status
    is_active = models.BooleanField(default=True)
    low_balance_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=100)  # Alert when below this
    
    # Security and limits
    daily_usage_limit = models.DecimalField(max_digits=10, decimal_places=2, default=5000)
    last_transaction_date = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def has_sufficient_balance(self, amount):
        """Check if collector has enough credits for a transaction"""
        return self.current_balance >= amount and self.is_active
    
    def deduct_credits(self, amount, pickup_request, description="Payment to customer"):
        """Deduct credits for a customer payment"""
        if self.has_sufficient_balance(amount):
            balance_before = self.current_balance
            self.current_balance -= amount
            self.total_used += amount
            self.last_transaction_date = timezone.now()
            self.save()
            
            # Create transaction record
            CreditTransaction.objects.create(
                credit_account=self,
                transaction_type='debit',
                amount=amount,
                pickup_request=pickup_request,
                description=description,
                balance_before=balance_before,
                balance_after=self.current_balance
            )
            return True
        return False
    
    def add_credits(self, amount, credit_purchase=None, description="Credit purchase"):
        """Add credits to account"""
        balance_before = self.current_balance
        self.current_balance += amount
        self.total_purchased += amount
        self.save()
        
        CreditTransaction.objects.create(
            credit_account=self,
            transaction_type='credit',
            amount=amount,
            credit_purchase=credit_purchase,
            description=description,
            balance_before=balance_before,
            balance_after=self.current_balance
        )
    
    def is_low_balance(self):
        """Check if balance is below threshold"""
        return self.current_balance <= self.low_balance_threshold
    
    def __str__(self):
        return f"{self.collector.username} Credits - Rs.{self.current_balance}"


class CreditPurchase(models.Model):
    """Record of credit purchases by collectors"""
    PAYMENT_STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )
    
    collector = models.ForeignKey(User, on_delete=models.CASCADE, related_name='credit_purchases')
    package = models.ForeignKey(CreditPackage, on_delete=models.CASCADE)
    
    # Purchase details
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    credits_received = models.DecimalField(max_digits=10, decimal_places=2)
    bonus_credits = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Payment details
    payment_method = models.CharField(max_length=50)  # "eSewa", "Khalti", "Cash", etc.
    payment_reference = models.CharField(max_length=100, blank=True)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    
    # Timestamps
    purchased_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def complete_purchase(self):
        """Complete the credit purchase and add credits to account"""
        if self.payment_status == 'pending':
            # Add credits to collector's account
            credit_account, created = CollectorCreditAccount.objects.get_or_create(
                collector=self.collector
            )
            
            total_credits = self.credits_received + self.bonus_credits
            credit_account.add_credits(total_credits, self, f"Credit purchase - {self.package.name}")
            
            # Update purchase status
            self.payment_status = 'completed'
            self.completed_at = timezone.now()
            self.save()
            
            return True
        return False
    
    def __str__(self):
        return f"{self.collector.username} - {self.package.name} - Rs.{self.amount_paid}"


class CreditTransaction(models.Model):
    """Track all credit transactions (purchases and usage)"""
    TRANSACTION_TYPE_CHOICES = (
        ('credit', 'Credit Added'),
        ('debit', 'Credit Used'),
    )
    
    credit_account = models.ForeignKey(CollectorCreditAccount, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField()
    
    # References
    pickup_request = models.ForeignKey(PickupRequest, on_delete=models.SET_NULL, null=True, blank=True)
    credit_purchase = models.ForeignKey(CreditPurchase, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Balance tracking
    balance_before = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.transaction_type.title()} Rs.{self.amount} - {self.credit_account.collector.username}"
