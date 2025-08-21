from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import datetime, date
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator

from .models import User, PickupRequest, WasteCategory, Transaction, EnvironmentalImpact
from .forms import CustomUserCreationForm, PickupRequestForm, CollectorUpdateForm

def home(request):
    """Home page view"""
    context = {
        'total_users': User.objects.count(),
        'total_pickups': PickupRequest.objects.count(),
        'waste_categories': WasteCategory.objects.filter(is_active=True)[:6],
    }
    return render(request, 'core/home.html', context)

def register(request):
    """User registration view"""
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created for {username}! You can now log in.')
            
            # Create environmental impact record for customers
            if user.role == 'customer':
                EnvironmentalImpact.objects.create(user=user)
            
            return redirect('login')
    else:
        form = CustomUserCreationForm()
    return render(request, 'core/register.html', {'form': form})

def user_login(request):
    """User login view"""
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f'Welcome back, {user.username}!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    return render(request, 'core/login.html')

def user_logout(request):
    """User logout view"""
    logout(request)
    messages.success(request, 'Good-bye! You have been logged out.')
    return redirect('home')

@login_required
def dashboard(request):
    """Dashboard redirect based on user role"""
    if request.user.role == 'admin' or request.user.is_staff:
        return redirect('admin_dashboard')
    elif request.user.role == 'collector':
        return redirect('collector_dashboard')
    else:
        return redirect('customer_dashboard')

@login_required
def customer_dashboard(request):
    """Customer dashboard view"""
    pickup_stats = {
        'pending': PickupRequest.objects.filter(customer=request.user, status='pending').count(),
        'completed': PickupRequest.objects.filter(customer=request.user, status='completed').count(),
        'total': PickupRequest.objects.filter(customer=request.user).count(),
    }
    
    recent_pickups = PickupRequest.objects.filter(customer=request.user).order_by('-created_at')[:5]
    
    # Get or create environmental impact
    impact, created = EnvironmentalImpact.objects.get_or_create(user=request.user)
    if created or impact.last_updated < timezone.now() - timezone.timedelta(hours=1):
        impact.calculate_impact()
    
    total_earnings = PickupRequest.objects.filter(
        customer=request.user, 
        status='completed',
        actual_price__isnull=False
    ).aggregate(total=Sum('actual_price'))['total'] or 0

    context = {
        'pickup_stats': pickup_stats,
        'recent_pickups': recent_pickups,
        'impact': impact,
        'total_earnings': total_earnings,
    }
    return render(request, 'core/dashboard_customer.html', context)

@login_required
def collector_dashboard(request):
    """Collector dashboard view"""
    available_pickups = PickupRequest.objects.filter(status='pending').order_by('-created_at')
    assigned_pickups = PickupRequest.objects.filter(collector=request.user).exclude(status='completed').order_by('-created_at')
    today_pickups = PickupRequest.objects.filter(collector=request.user, pickup_date=date.today())
    
    # Calculate earnings (10% commission)
    total_earnings = Transaction.objects.filter(collector=request.user).aggregate(
        total=Sum('collector_commission')
    )['total'] or 0
    
    completion_rate = PickupRequest.objects.filter(collector=request.user, status='completed').count()

    context = {
        'available_pickups': available_pickups,
        'assigned_pickups': assigned_pickups,
        'today_pickups': today_pickups,
        'total_earnings': total_earnings,
        'completion_rate': completion_rate,
    }
    return render(request, 'core/dashboard_collector.html', context)

@staff_member_required
def admin_dashboard(request):
    """Admin dashboard view"""
    user_stats = {
        'total': User.objects.count(),
        'customers': User.objects.filter(role='customer').count(),
        'collectors': User.objects.filter(role='collector').count(),
    }
    
    pickup_stats = {
        'total': PickupRequest.objects.count(),
        'completed': PickupRequest.objects.filter(status='completed').count(),
        'pending': PickupRequest.objects.filter(status='pending').count(),
        'this_month': PickupRequest.objects.filter(created_at__month=timezone.now().month).count(),
    }
    
    recent_pickups = PickupRequest.objects.select_related('customer', 'waste_category').order_by('-created_at')[:10]
    recent_users = User.objects.order_by('-date_joined')[:5]
    waste_categories = WasteCategory.objects.all()
    
    total_transactions = PickupRequest.objects.filter(
        status='completed'
    ).aggregate(total=Sum('actual_weight_kg'))['total'] or 0

    context = {
        'user_stats': user_stats,
        'pickup_stats': pickup_stats,
        'recent_pickups': recent_pickups,
        'recent_users': recent_users,
        'waste_categories': waste_categories,
        'total_transactions': total_transactions,
    }
    return render(request, 'core/dashboard_admin.html', context)

@login_required
def request_pickup(request):
    """Request pickup view"""
    if request.method == 'POST':
        form = PickupRequestForm(request.POST)
        if form.is_valid():
            pickup = form.save(commit=False)
            pickup.customer = request.user
            pickup.save()
            messages.success(request, 'Pickup request submitted successfully!')
            return redirect('customer_dashboard')
    else:
        form = PickupRequestForm()
    
    waste_categories = WasteCategory.objects.filter(is_active=True)
    context = {
        'form': form,
        'waste_categories': waste_categories,
    }
    return render(request, 'core/request_pickup.html', context)

@login_required
def pickup_history(request):
    """Pickup history view"""
    if request.user.role == 'customer':
        pickups = PickupRequest.objects.filter(customer=request.user).order_by('-created_at')
    elif request.user.role == 'collector':
        pickups = PickupRequest.objects.filter(collector=request.user).order_by('-created_at')
    else:
        pickups = PickupRequest.objects.all().order_by('-created_at')
    
    # Pagination
    paginator = Paginator(pickups, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
    }
    return render(request, 'core/pickup_history.html', context)

@login_required
def assign_pickup(request, pickup_id):
    """Assign pickup to collector"""
    if request.user.role != 'collector':
        messages.error(request, 'Only collectors can assign pickups.')
        return redirect('dashboard')
    
    pickup = get_object_or_404(PickupRequest, id=pickup_id, status='pending')
    pickup.collector = request.user
    pickup.status = 'assigned'
    pickup.save()
    
    messages.success(request, f'Pickup #{pickup.id} has been assigned to you!')
    return redirect('collector_dashboard')

@login_required
def update_pickup(request, pickup_id):
    """Update pickup status and actual weight"""
    pickup = get_object_or_404(PickupRequest, id=pickup_id)
    
    if request.user.role == 'collector' and pickup.collector != request.user:
        messages.error(request, 'You can only update your assigned pickups.')
        return redirect('collector_dashboard')
    
    if request.method == 'POST':
        form = CollectorUpdateForm(request.POST, instance=pickup)
        if form.is_valid():
            pickup = form.save()
            
            # Create transaction if completed
            if pickup.status == 'completed' and pickup.actual_weight_kg:
                Transaction.objects.get_or_create(
                    pickup_request=pickup,
                    defaults={
                        'customer': pickup.customer,
                        'collector': pickup.collector,
                        'amount': pickup.actual_price,
                    }
                )
                
                # Update customer's environmental impact
                impact, created = EnvironmentalImpact.objects.get_or_create(user=pickup.customer)
                impact.calculate_impact()
            
            messages.success(request, 'Pickup updated successfully!')
            return redirect('collector_dashboard')
    else:
        form = CollectorUpdateForm(instance=pickup)
    
    context = {
        'form': form,
        'pickup': pickup,
    }
    return render(request, 'core/update_pickup.html', context)

@login_required
def cancel_pickup(request, pickup_id):
    """Cancel pickup request"""
    pickup = get_object_or_404(PickupRequest, id=pickup_id)
    
    # Only customer can cancel their own pending/assigned pickups
    if pickup.customer != request.user or pickup.status in ['completed', 'cancelled']:
        messages.error(request, 'You cannot cancel this pickup.')
        return redirect('customer_dashboard')
    
    pickup.status = 'cancelled'
    pickup.save()
    
    messages.success(request, f'Pickup #{pickup.id} has been cancelled.')
    return redirect('customer_dashboard')

@login_required
def delete_account(request):
    """Delete user account"""
    if request.method == 'POST':
        user = request.user
        username = user.username
        user.delete()
        messages.success(request, f"Account for {username} has been deleted successfully.")
        return redirect('home')
    
    return render(request, 'core/delete_account.html')

def about(request):
    """About page"""
    return render(request, 'core/about.html')

def contact(request):
    """Contact page"""
    return render(request, 'core/contact.html')
