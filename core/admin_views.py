"""
Custom Admin Dashboard Views - Complete replacement for Django Admin
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum, Avg
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from datetime import datetime, timedelta
import json
import csv
import calendar
from io import StringIO

from .models import (
    User, PickupRequest, Transaction, WasteCategory, 
    EnvironmentalImpact, SMSNotification, CollectorLocation, PaymentGatewayLog
)
from .forms import CustomUserCreationForm, PickupRequestForm, AdminPickupEditForm
from .services import SMSService, GPSTrackingService


def admin_required(user):
    """Check if user is admin"""
    return user.is_authenticated and user.role == 'admin'


@user_passes_test(admin_required)
def custom_admin_dashboard(request):
    """Enhanced custom admin dashboard"""
    # Get date range for filtering
    now = timezone.now()
    today = now.date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # User Statistics
    user_stats = {
        'total': User.objects.count(),
        'customers': User.objects.filter(role='customer').count(),
        'collectors': User.objects.filter(role='collector').count(),
        'admins': User.objects.filter(role='admin').count(),
        'active_users': User.objects.filter(is_active=True).count(),
        'new_this_week': User.objects.filter(date_joined__gte=week_ago).count(),
        'new_this_month': User.objects.filter(date_joined__gte=month_ago).count(),
    }
    
    # Pickup Statistics
    pickup_stats = {
        'total': PickupRequest.objects.count(),
        'pending': PickupRequest.objects.filter(status='pending').count(),
        'assigned': PickupRequest.objects.filter(status='assigned').count(),
        'in_progress': PickupRequest.objects.filter(status='in_progress').count(),
        'completed': PickupRequest.objects.filter(status='completed').count(),
        'cancelled': PickupRequest.objects.filter(status='cancelled').count(),
        'this_week': PickupRequest.objects.filter(created_at__gte=week_ago).count(),
        'this_month': PickupRequest.objects.filter(created_at__gte=month_ago).count(),
    }
    
    # Financial Statistics
    financial_stats = {
        'total_transactions': Transaction.objects.count(),
        'completed_transactions': Transaction.objects.filter(is_paid=True).count(),
        'pending_transactions': Transaction.objects.filter(is_paid=False).count(),
        'total_revenue': Transaction.objects.filter(is_paid=True).aggregate(
            total=Sum('amount'))['total'] or 0,
        'total_commissions': Transaction.objects.filter(is_paid=True).aggregate(
            total=Sum('collector_commission'))['total'] or 0,
        'avg_transaction': Transaction.objects.filter(is_paid=True).aggregate(
            avg=Avg('amount'))['avg'] or 0,
    }
    
    # Environmental Impact
    env_stats = {
        'total_weight': PickupRequest.objects.filter(
            status='completed', actual_weight_kg__isnull=False
        ).aggregate(total=Sum('actual_weight_kg'))['total'] or 0,
        'trees_saved': 0,
        'co2_reduced': 0,
        'water_saved': 0,
    }
    
    # Calculate environmental impact
    if env_stats['total_weight']:
        # Ensure proper type conversion to avoid Decimal * float errors
        total_weight_float = float(env_stats['total_weight']) if env_stats['total_weight'] else 0.0
        env_stats['trees_saved'] = total_weight_float * 0.017
        env_stats['co2_reduced'] = total_weight_float * 0.82
        env_stats['water_saved'] = total_weight_float * 13.2
    else:
        env_stats['trees_saved'] = 0
        env_stats['co2_reduced'] = 0
        env_stats['water_saved'] = 0
    
    # Recent Activity
    recent_pickups = PickupRequest.objects.select_related(
        'customer', 'collector', 'waste_category'
    ).order_by('-created_at')[:15]
    
    recent_users = User.objects.order_by('-date_joined')[:10]
    
    pending_transactions = Transaction.objects.filter(
        is_paid=False
    ).select_related('customer', 'collector', 'pickup_request')[:10]
    
    # System Health
    system_health = {
        'active_collectors': User.objects.filter(
            role='collector', is_active=True
        ).count(),
        'recent_gps_updates': CollectorLocation.objects.filter(
            timestamp__gte=timezone.now() - timedelta(hours=1)
        ).count(),
        'sms_sent_today': SMSNotification.objects.filter(
            created_at__date=today, status='sent'
        ).count(),
        'payment_success_rate': 0,
    }
    
    # Calculate payment success rate
    total_payments = PaymentGatewayLog.objects.count()
    if total_payments > 0:
        successful_payments = Transaction.objects.filter(is_paid=True).count()
        system_health['payment_success_rate'] = (successful_payments / total_payments) * 100
    
    # Waste Categories
    waste_categories = WasteCategory.objects.all().order_by('name')
    
    # Status choices for modals
    status_choices = PickupRequest.STATUS_CHOICES
    
    context = {
        'user_stats': user_stats,
        'pickup_stats': pickup_stats,
        'financial_stats': financial_stats,
        'env_stats': env_stats,
        'recent_pickups': recent_pickups,
        'recent_users': recent_users,
        'pending_transactions': pending_transactions,
        'system_health': system_health,
        'waste_categories': waste_categories,
        'status_choices': status_choices,
        'today': today,
        'now': now,
    }
    
    return render(request, 'core/admin/dashboard.html', context)


@user_passes_test(admin_required)
def admin_user_management(request):
    """Comprehensive user management interface"""
    # Get filter parameters
    role_filter = request.GET.get('role', 'all')
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('search', '')
    
    # Base queryset
    users = User.objects.all()
    
    # Apply filters
    if role_filter != 'all':
        users = users.filter(role=role_filter)
    
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )
    
    # Order by date joined (newest first)
    users = users.order_by('-date_joined')
    
    # Pagination
    paginator = Paginator(users, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # User statistics for each role
    role_stats = {
        'customers': User.objects.filter(role='customer').count(),
        'collectors': User.objects.filter(role='collector').count(),
        'admins': User.objects.filter(role='admin').count(),
        'active': User.objects.filter(is_active=True).count(),
        'inactive': User.objects.filter(is_active=False).count(),
    }
    
    context = {
        'page_obj': page_obj,
        'role_stats': role_stats,
        'current_filters': {
            'role': role_filter,
            'status': status_filter,
            'search': search_query,
        },
        'role_choices': User.ROLE_CHOICES,
    }
    
    return render(request, 'core/admin/user_management.html', context)


@user_passes_test(admin_required)
@require_http_methods(["POST"])
def admin_create_user(request):
    """Create new user via admin interface"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        required_fields = ['username', 'email', 'password', 'role']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({
                    'success': False, 
                    'error': f'{field.title()} is required'
                })
        
        # Check if username already exists
        if User.objects.filter(username=data['username']).exists():
            return JsonResponse({
                'success': False, 
                'error': 'Username already exists'
            })
        
        # Check if email already exists
        if User.objects.filter(email=data['email']).exists():
            return JsonResponse({
                'success': False, 
                'error': 'Email already exists'
            })
        
        # Create user
        user = User.objects.create_user(
            username=data['username'],
            email=data['email'],
            password=data['password'],
            role=data['role'],
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
            phone=data.get('phone', ''),
        )
        
        # Send welcome SMS if phone number provided
        if user.phone:
            try:
                SMSService.send_sms(
                    user, 
                    f"Welcome to Kawadiwala! Your account has been created. Username: {user.username}",
                    'welcome'
                )
            except Exception as e:
                pass  # Don't fail user creation if SMS fails
        
        return JsonResponse({
            'success': True,
            'message': f'User {user.username} created successfully',
            'user_id': user.id
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@user_passes_test(admin_required)
@require_http_methods(["POST"])
def admin_update_user(request, user_id):
    """Update user information"""
    try:
        user = get_object_or_404(User, id=user_id)
        data = json.loads(request.body)
        
        # Update fields
        user.first_name = data.get('first_name', user.first_name)
        user.last_name = data.get('last_name', user.last_name)
        user.email = data.get('email', user.email)
        user.phone = data.get('phone', user.phone)
        user.role = data.get('role', user.role)
        user.is_active = data.get('is_active', user.is_active)
        
        user.save()
        
        return JsonResponse({
            'success': True,
            'message': f'User {user.username} updated successfully'
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@user_passes_test(admin_required)
def admin_pickup_management(request):
    """Comprehensive pickup management interface"""
    # Get filter parameters
    status_filter = request.GET.get('status', 'all')
    collector_filter = request.GET.get('collector', 'all')
    date_filter = request.GET.get('date_range', 'all')
    search_query = request.GET.get('search', '')
    
    # Base queryset
    pickups = PickupRequest.objects.select_related(
        'customer', 'collector', 'waste_category'
    )
    
    # Apply filters
    if status_filter != 'all':
        pickups = pickups.filter(status=status_filter)
    
    if collector_filter != 'all':
        if collector_filter == 'unassigned':
            pickups = pickups.filter(collector__isnull=True)
        else:
            pickups = pickups.filter(collector_id=collector_filter)
    
    if date_filter != 'all':
        today = timezone.now().date()
        if date_filter == 'today':
            pickups = pickups.filter(created_at__date=today)
        elif date_filter == 'week':
            week_ago = today - timedelta(days=7)
            pickups = pickups.filter(created_at__date__gte=week_ago)
        elif date_filter == 'month':
            month_ago = today - timedelta(days=30)
            pickups = pickups.filter(created_at__date__gte=month_ago)
    
    if search_query:
        pickups = pickups.filter(
            Q(customer__username__icontains=search_query) |
            Q(collector__username__icontains=search_query) |
            Q(waste_category__name__icontains=search_query) |
            Q(address__icontains=search_query)
        )
    
    # Order by creation date (newest first)
    pickups = pickups.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(pickups, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get collectors for filter dropdown
    collectors = User.objects.filter(role='collector', is_active=True)
    
    # Pickup statistics
    pickup_stats = {
        'total': PickupRequest.objects.count(),
        'pending': PickupRequest.objects.filter(status='pending').count(),
        'assigned': PickupRequest.objects.filter(status='assigned').count(),
        'in_progress': PickupRequest.objects.filter(status='in_progress').count(),
        'completed': PickupRequest.objects.filter(status='completed').count(),
        'cancelled': PickupRequest.objects.filter(status='cancelled').count(),
    }
    
    context = {
        'page_obj': page_obj,
        'collectors': collectors,
        'pickup_stats': pickup_stats,
        'current_filters': {
            'status': status_filter,
            'collector': collector_filter,
            'date_range': date_filter,
            'search': search_query,
        },
        'status_choices': PickupRequest.STATUS_CHOICES,
    }
    
    return render(request, 'core/admin/pickup_management.html', context)


@user_passes_test(admin_required)
def admin_pickup_details(request, pickup_id):
    """Detailed view of a specific pickup request"""
    pickup = get_object_or_404(PickupRequest, id=pickup_id)
    
    # Get related transaction if exists
    transaction = None
    try:
        transaction = Transaction.objects.get(pickup_request=pickup)
    except Transaction.DoesNotExist:
        pass
    
    # Get environmental impact data for the customer
    environmental_impact = None
    try:
        environmental_impact = EnvironmentalImpact.objects.get(user=pickup.customer)
    except EnvironmentalImpact.DoesNotExist:
        pass
    
    # Get pickup history for this customer (last 5 pickups)
    customer_pickup_history = PickupRequest.objects.filter(
        customer=pickup.customer
    ).exclude(id=pickup.id).order_by('-created_at')[:5]
    
    # Get collector's performance stats if assigned
    collector_stats = None
    if pickup.collector:
        collector_stats = {
            'total_pickups': PickupRequest.objects.filter(collector=pickup.collector).count(),
            'completed_pickups': PickupRequest.objects.filter(
                collector=pickup.collector, status='completed'
            ).count(),
            'avg_rating': 4.5,  # Placeholder - implement rating system later
            'total_waste_collected': PickupRequest.objects.filter(
                collector=pickup.collector, status='completed'
            ).aggregate(total=Sum('actual_weight_kg'))['total'] or 0,
        }
        if collector_stats['total_pickups'] > 0:
            collector_stats['completion_rate'] = (
                collector_stats['completed_pickups'] / collector_stats['total_pickups']
            ) * 100
        else:
            collector_stats['completion_rate'] = 0
    
    context = {
        'pickup': pickup,
        'transaction': transaction,
        'environmental_impact': environmental_impact,
        'customer_pickup_history': customer_pickup_history,
        'collector_stats': collector_stats,
    }
    
    return render(request, 'core/admin/pickup_details.html', context)


@user_passes_test(admin_required)
def admin_pickup_edit(request, pickup_id):
    """Admin view for editing pickup requests"""
    pickup = get_object_or_404(PickupRequest, id=pickup_id)
    
    if request.method == 'POST':
        form = AdminPickupEditForm(request.POST, instance=pickup)
        if form.is_valid():
            # Save the form
            updated_pickup = form.save(commit=False)
            
            # If status is being changed to completed and actual weight is provided
            if updated_pickup.status == 'completed' and updated_pickup.actual_weight_kg:
                # Calculate actual price
                updated_pickup.actual_price = updated_pickup.actual_weight_kg * updated_pickup.waste_category.rate_per_kg
                
                # Create transaction if it doesn't exist
                if not hasattr(updated_pickup, 'transaction'):
                    from decimal import Decimal
                    Transaction.objects.create(
                        pickup_request=updated_pickup,
                        customer=updated_pickup.customer,
                        collector=updated_pickup.collector,
                        amount=updated_pickup.actual_price,
                        payment_method='cash',
                        payment_status='completed',
                        is_paid=True
                    )
            
            updated_pickup.save()
            messages.success(request, f'Pickup #{pickup.id} updated successfully!')
            return redirect('admin_pickup_details', pickup_id=pickup.id)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = AdminPickupEditForm(instance=pickup)
    
    context = {
        'form': form,
        'pickup': pickup,
    }
    return render(request, 'core/admin/pickup_edit.html', context)


@user_passes_test(admin_required)
def admin_transaction_details(request, transaction_id):
    """Admin view for detailed transaction information"""
    transaction = get_object_or_404(Transaction, id=transaction_id)
    
    context = {
        'transaction': transaction,
        'pickup_request': transaction.pickup_request,
        'gateway_logs': transaction.gateway_logs.all() if hasattr(transaction, 'gateway_logs') else []
    }
    return render(request, 'core/payment/transaction_details.html', context)


@user_passes_test(admin_required)
def admin_analytics_dashboard(request):
    """Advanced analytics and reporting dashboard"""
    # Date range for analysis
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    year_ago = today - timedelta(days=365)
    
    # Revenue Analytics
    revenue_data = {
        'total_revenue': Transaction.objects.filter(is_paid=True).aggregate(
            total=Sum('amount'))['total'] or 0,
        'monthly_revenue': Transaction.objects.filter(
            is_paid=True, transaction_date__gte=month_ago
        ).aggregate(total=Sum('amount'))['total'] or 0,
        'weekly_revenue': Transaction.objects.filter(
            is_paid=True, transaction_date__gte=week_ago
        ).aggregate(total=Sum('amount'))['total'] or 0,
        'avg_transaction': Transaction.objects.filter(is_paid=True).aggregate(
            avg=Avg('amount'))['avg'] or 0,
    }
    
    # User Growth Analytics - Get actual monthly data
    # Get monthly user registrations for the last 12 months
    monthly_registrations = User.objects.filter(
        date_joined__gte=year_ago
    ).annotate(
        month=TruncMonth('date_joined')
    ).values('month').annotate(
        count=Count('id')
    ).order_by('month')
    
    # Create a dictionary for easy lookup
    monthly_data = {reg['month'].month: reg['count'] for reg in monthly_registrations}
    
    # Generate data for all 12 months (showing last 12 months)
    current_month = today.month
    current_year = today.year
    monthly_labels = []
    monthly_values = []
    
    for i in range(12):
        # Calculate the month and year for each of the last 12 months
        months_back = 11 - i
        target_date = today.replace(day=1) - timedelta(days=months_back * 30)
        month_name = calendar.month_abbr[target_date.month]
        monthly_labels.append(month_name)
        
        # Get the actual count for this month, or 0 if no registrations
        month_count = 0
        for reg in monthly_registrations:
            if reg['month'].month == target_date.month and reg['month'].year == target_date.year:
                month_count = reg['count']
                break
        monthly_values.append(month_count)
    
    user_growth = {
        'total_users': User.objects.count(),
        'monthly_growth': User.objects.filter(date_joined__gte=month_ago).count(),
        'weekly_growth': User.objects.filter(date_joined__gte=week_ago).count(),
        'customer_retention': 0,  # Calculate based on repeat pickups
        'monthly_labels': monthly_labels,
        'monthly_values': monthly_values,
    }
    
    # Pickup Analytics
    pickup_analytics = {
        'completion_rate': 0,
        'avg_pickup_time': 0,
        'popular_categories': [],
        'peak_hours': [],
    }
    
    # Calculate completion rate
    total_pickups = PickupRequest.objects.count()
    if total_pickups > 0:
        completed_pickups = PickupRequest.objects.filter(status='completed').count()
        pickup_analytics['completion_rate'] = (completed_pickups / total_pickups) * 100
    
    # Popular waste categories
    popular_categories = WasteCategory.objects.annotate(
        pickup_count=Count('pickuprequest')
    ).order_by('-pickup_count')[:5]
    
    pickup_analytics['popular_categories'] = [
        {'name': cat.name, 'count': cat.pickup_count} 
        for cat in popular_categories
    ]
    
    # Environmental Impact Analytics
    env_impact = {
        'total_weight_recycled': PickupRequest.objects.filter(
            status='completed', actual_weight_kg__isnull=False
        ).aggregate(total=Sum('actual_weight_kg'))['total'] or 0,
        'monthly_weight': PickupRequest.objects.filter(
            status='completed', 
            actual_weight_kg__isnull=False,
            pickup_date__gte=month_ago
        ).aggregate(total=Sum('actual_weight_kg'))['total'] or 0,
    }
    
    # Calculate environmental benefits
    if env_impact['total_weight_recycled']:
        # Ensure proper type conversion to avoid Decimal * float errors
        total_weight_float = float(env_impact['total_weight_recycled']) if env_impact['total_weight_recycled'] else 0.0
        env_impact['trees_saved'] = total_weight_float * 0.017
        env_impact['co2_reduced'] = total_weight_float * 0.82
        env_impact['water_saved'] = total_weight_float * 13.2
    else:
        env_impact['trees_saved'] = 0
        env_impact['co2_reduced'] = 0
        env_impact['water_saved'] = 0
    
    # Payment Method Analytics
    payment_methods = Transaction.objects.filter(is_paid=True).values(
        'payment_method'
    ).annotate(count=Count('id')).order_by('-count')
    
    # System Performance
    system_performance = {
        'active_collectors': User.objects.filter(
            role='collector', is_active=True
        ).count(),
        'avg_response_time': 0,  # Would need to track this
        'sms_delivery_rate': 0,
        'payment_success_rate': 0,
    }
    
    # Calculate SMS delivery rate
    total_sms = SMSNotification.objects.count()
    if total_sms > 0:
        delivered_sms = SMSNotification.objects.filter(status='sent').count()
        system_performance['sms_delivery_rate'] = (delivered_sms / total_sms) * 100
    
    # Calculate payment success rate
    total_payment_attempts = PaymentGatewayLog.objects.count()
    if total_payment_attempts > 0:
        successful_payments = Transaction.objects.filter(is_paid=True).count()
        system_performance['payment_success_rate'] = (successful_payments / total_payment_attempts) * 100
    
    context = {
        'revenue_data': revenue_data,
        'user_growth': user_growth,
        'pickup_analytics': pickup_analytics,
        'env_impact': env_impact,
        'payment_methods': payment_methods,
        'system_performance': system_performance,
    }
    
    return render(request, 'core/admin/analytics.html', context)


@user_passes_test(admin_required)
def admin_system_settings(request):
    """System configuration and settings"""
    if request.method == 'POST':
        # Handle settings update
        try:
            # This would typically update a Settings model
            # For now, we'll just show a success message
            messages.success(request, 'Settings updated successfully!')
            return redirect('admin_system_settings')
        except Exception as e:
            messages.error(request, f'Error updating settings: {str(e)}')
    
    # Get current system statistics
    system_stats = {
        'total_users': User.objects.count(),
        'total_pickups': PickupRequest.objects.count(),
        'total_transactions': Transaction.objects.count(),
        'active_collectors': User.objects.filter(role='collector', is_active=True).count(),
        'waste_categories': WasteCategory.objects.count(),
        'sms_sent': SMSNotification.objects.filter(status='sent').count(),
        'gps_updates': CollectorLocation.objects.count(),
    }
    
    # Recent system logs (you might want to implement a proper logging system)
    recent_activities = []
    
    context = {
        'system_stats': system_stats,
        'recent_activities': recent_activities,
    }
    
    return render(request, 'core/admin/system_settings.html', context)


@user_passes_test(admin_required)
def admin_export_data(request):
    """Export system data in various formats"""
    export_type = request.GET.get('type', 'pickups')
    format_type = request.GET.get('format', 'csv')
    
    if export_type == 'pickups':
        queryset = PickupRequest.objects.select_related(
            'customer', 'collector', 'waste_category'
        ).all()
        
        if format_type == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="pickups_export.csv"'
            
            writer = csv.writer(response)
            writer.writerow([
                'ID', 'Date', 'Customer', 'Collector', 'Category', 
                'Status', 'Weight (kg)', 'Price (Rs)', 'Address'
            ])
            
            for pickup in queryset:
                writer.writerow([
                    pickup.id,
                    pickup.created_at.strftime('%Y-%m-%d'),
                    pickup.customer.username,
                    pickup.collector.username if pickup.collector else 'Unassigned',
                    pickup.waste_category.name,
                    pickup.get_status_display(),
                    pickup.actual_weight_kg or pickup.estimated_weight_kg,
                    pickup.actual_price or pickup.estimated_price,
                    pickup.address
                ])
            
            return response
    
    elif export_type == 'users':
        queryset = User.objects.all()
        
        if format_type == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="users_export.csv"'
            
            writer = csv.writer(response)
            writer.writerow([
                'ID', 'Username', 'Email', 'Role', 'Status', 'Date Joined'
            ])
            
            for user in queryset:
                writer.writerow([
                    user.id,
                    user.username,
                    user.email,
                    user.get_role_display(),
                    'Active' if user.is_active else 'Inactive',
                    user.date_joined.strftime('%Y-%m-%d')
                ])
            
            return response
    
    # Default response
    return JsonResponse({'error': 'Invalid export parameters'})


@user_passes_test(admin_required)
@csrf_exempt
def admin_bulk_actions(request):
    """Handle bulk actions on various models"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        action = data.get('action')
        model_type = data.get('model_type')
        item_ids = data.get('item_ids', [])
        
        if not action or not model_type or not item_ids:
            return JsonResponse({'success': False, 'error': 'Missing required parameters'})
        
        if model_type == 'users':
            users = User.objects.filter(id__in=item_ids)
            
            if action == 'activate':
                users.update(is_active=True)
                message = f'Activated {users.count()} users'
            elif action == 'deactivate':
                users.update(is_active=False)
                message = f'Deactivated {users.count()} users'
            elif action == 'delete':
                count = users.count()
                users.delete()
                message = f'Deleted {count} users'
            else:
                return JsonResponse({'success': False, 'error': 'Invalid action'})
        
        elif model_type == 'pickups':
            pickups = PickupRequest.objects.filter(id__in=item_ids)
            
            if action == 'mark_completed':
                pickups.update(status='completed')
                message = f'Marked {pickups.count()} pickups as completed'
            elif action == 'cancel':
                pickups.update(status='cancelled')
                message = f'Cancelled {pickups.count()} pickups'
            elif action == 'delete':
                count = pickups.count()
                pickups.delete()
                message = f'Deleted {count} pickups'
            else:
                return JsonResponse({'success': False, 'error': 'Invalid action'})
        
        else:
            return JsonResponse({'success': False, 'error': 'Invalid model type'})
        
        return JsonResponse({'success': True, 'message': message})
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
