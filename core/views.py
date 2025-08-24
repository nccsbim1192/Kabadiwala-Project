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
    # Get available pickups (not assigned to any collector)
    available_pickups = PickupRequest.objects.filter(
        status='pending',
        collector__isnull=True
    ).order_by('-created_at')
    
    # Get pickups assigned to current collector
    assigned_pickups = PickupRequest.objects.filter(
        collector=request.user,
        status__in=['assigned', 'in_progress']
    ).order_by('-created_at')
    
    # Get today's pickups
    today_pickups = PickupRequest.objects.filter(
        collector=request.user, 
        pickup_date=date.today(),
        status__in=['assigned', 'in_progress']
    )
    
    # Calculate total completed pickups
    completed_pickups = PickupRequest.objects.filter(
        collector=request.user, 
        status='completed'
    )
    
    # Calculate total pickups (assigned + completed)
    total_pickups = PickupRequest.objects.filter(
        collector=request.user
    ).count()
    
    # Calculate completion rate (percentage)
    completion_rate = 0
    if total_pickups > 0:
        completion_rate = round((completed_pickups.count() / total_pickups) * 100)
    
    # Calculate total earnings from transactions (10% commission)
    total_earnings = Transaction.objects.filter(
        collector=request.user,
        is_paid=True
    ).aggregate(
        total=Sum('collector_commission')
    )['total'] or 0
    
    # If no transactions exist, calculate from completed pickups (10% of actual_price)
    if total_earnings == 0:
        from decimal import Decimal
        completed_earnings = completed_pickups.filter(
            actual_price__isnull=False
        ).aggregate(
            total=Sum('actual_price')
        )['total'] or 0
        total_earnings = completed_earnings * Decimal('0.10')

    # Get recent completed pickups for history widget
    recent_completed_pickups = PickupRequest.objects.filter(
        collector=request.user,
        status='completed'
    ).order_by('-created_at')[:10]

    context = {
        'available_pickups': available_pickups,
        'assigned_pickups': assigned_pickups,
        'today_pickups': today_pickups,
        'total_earnings': total_earnings,
        'completion_rate': completion_rate,
        'completed_pickups': completed_pickups.count(),
        'recent_completed_pickups': recent_completed_pickups,
    }
    return render(request, 'core/dashboard_collector.html', context)

@staff_member_required
def admin_dashboard(request):
    """Admin dashboard view - only for admin users"""
    # Additional check to ensure only admin role users can access
    if not (request.user.role == 'admin' or request.user.is_superuser):
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('dashboard')
    user_stats = {
        'total': User.objects.count(),
        'customers': User.objects.filter(role='customer').count(),
        'collectors': User.objects.filter(role='collector').count(),
    }
    
    pickup_stats = {
        'total': PickupRequest.objects.count(),
        'completed': PickupRequest.objects.filter(status='completed').count(),
        'pending': PickupRequest.objects.filter(status='pending').count(),
        'assigned': PickupRequest.objects.filter(status='assigned').count(),
        'in_progress': PickupRequest.objects.filter(status='in_progress').count(),
        'this_month': PickupRequest.objects.filter(created_at__month=timezone.now().month).count(),
    }
    
    # Get pickups that need admin attention
    recent_pickups = PickupRequest.objects.select_related('customer', 'waste_category', 'collector').order_by('-created_at')[:15]
    recent_users = User.objects.order_by('-date_joined')[:5]
    waste_categories = WasteCategory.objects.all()
    
    # Get pending transactions for approval
    pending_transactions = Transaction.objects.filter(
        payment_status='pending'
    ).select_related('pickup_request', 'customer', 'collector').order_by('-transaction_date')[:10]
    
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
        'pending_transactions': pending_transactions,
        'status_choices': PickupRequest.STATUS_CHOICES,
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

# Admin-specific views for pickup management
@staff_member_required
def admin_update_pickup_status(request, pickup_id):
    """Admin view to update pickup status"""
    pickup = get_object_or_404(PickupRequest, id=pickup_id)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        actual_weight = request.POST.get('actual_weight_kg')
        
        if new_status in dict(PickupRequest.STATUS_CHOICES):
            pickup.status = new_status
            
            if actual_weight and new_status == 'completed':
                pickup.actual_weight_kg = actual_weight
                
                # Create transaction if completed
                if not hasattr(pickup, 'transaction'):
                    Transaction.objects.create(
                        pickup_request=pickup,
                        customer=pickup.customer,
                        collector=pickup.collector,
                        amount=pickup.actual_price or pickup.estimated_price,
                    )
                    
                    # Update customer's environmental impact
                    impact, created = EnvironmentalImpact.objects.get_or_create(user=pickup.customer)
                    impact.calculate_impact()
            
            pickup.save()
            messages.success(request, f'Pickup #{pickup.id} status updated to {pickup.get_status_display()}')
        else:
            messages.error(request, 'Invalid status provided')
    
    return redirect('admin_dashboard')

@staff_member_required
def admin_approve_transaction(request, transaction_id):
    """Admin view to approve/reject transactions"""
    transaction = get_object_or_404(Transaction, id=transaction_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            transaction.is_paid = True
            transaction.payment_status = 'completed'
            transaction.save()
            messages.success(request, f'Transaction #{transaction.id} approved and marked as paid')
        elif action == 'reject':
            transaction.payment_status = 'failed'
            transaction.save()
            messages.warning(request, f'Transaction #{transaction.id} rejected')
    
    return redirect('admin_dashboard')

@staff_member_required
def admin_bulk_update_pickups(request):
    """Admin view for bulk pickup operations"""
    if request.method == 'POST':
        pickup_ids = request.POST.getlist('pickup_ids')
        action = request.POST.get('bulk_action')
        
        if pickup_ids and action:
            pickups = PickupRequest.objects.filter(id__in=pickup_ids)
            
            if action == 'mark_completed':
                pickups.update(status='completed')
                messages.success(request, f'{len(pickup_ids)} pickups marked as completed')
            elif action == 'mark_cancelled':
                pickups.update(status='cancelled')
                messages.success(request, f'{len(pickup_ids)} pickups cancelled')
            elif action == 'unassign':
                pickups.update(collector=None, status='pending')
                messages.success(request, f'{len(pickup_ids)} pickups unassigned')
    
    return redirect('admin_dashboard')

@staff_member_required
def export_data_pdf(request):
    """Export pickup data as PDF with filters"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from django.http import HttpResponse
    from datetime import datetime
    import io
    
    # Get filter parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    status = request.GET.get('status')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    user_filter = request.GET.get('user_filter')  # For filtering by specific user
    
    # Build queryset with filters
    pickups = PickupRequest.objects.select_related('customer', 'collector', 'waste_category').all()
    
    if start_date:
        pickups = pickups.filter(created_at__date__gte=start_date)
    if end_date:
        pickups = pickups.filter(created_at__date__lte=end_date)
    if status and status != 'all':
        pickups = pickups.filter(status=status)
    if min_price:
        pickups = pickups.filter(estimated_price__gte=min_price)
    if max_price:
        pickups = pickups.filter(estimated_price__lte=max_price)
    if user_filter:
        pickups = pickups.filter(customer_id=user_filter)
    
    pickups = pickups.order_by('-created_at')
    
    # Create PDF with landscape orientation for better table fit
    from reportlab.lib.pagesizes import landscape
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=36, leftMargin=36, topMargin=72, bottomMargin=36)
    
    # Container for PDF elements
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=1,  # Center alignment
        textColor=colors.darkgreen
    )
    title = Paragraph("Kawadiwala - Pickup Requests Export", title_style)
    elements.append(title)
    
    # Export info
    info_style = ParagraphStyle(
        'InfoStyle',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=20,
        alignment=1
    )
    
    export_info = f"Export Date: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}<br/>"
    export_info += f"Total Records: {pickups.count()}<br/>"
    
    if start_date or end_date:
        date_range = f"Date Range: {start_date or 'Start'} to {end_date or 'End'}<br/>"
        export_info += date_range
    if status and status != 'all':
        export_info += f"Status Filter: {status.title()}<br/>"
    if min_price or max_price:
        price_range = f"Price Range: Rs {min_price or '0'} to Rs {max_price or '∞'}<br/>"
        export_info += price_range
    
    info_para = Paragraph(export_info, info_style)
    elements.append(info_para)
    elements.append(Spacer(1, 12))
    
    # Create table data
    data = [['ID', 'Date', 'Customer', 'Collector', 'Category', 'Weight (kg)', 'Actual Weight (kg)', 'Price (Rs)', 'Status']]
    
    for pickup in pickups:
        # Get collector name with proper fallback
        collector_name = 'Not Assigned'
        if pickup.collector:
            collector_name = pickup.collector.get_full_name() or pickup.collector.username
        
        # Format price properly
        price_value = pickup.actual_price or pickup.estimated_price or 0
        
        # Handle long status text properly
        status_text = pickup.get_status_display()
        if pickup.status == 'assigned':
            status_text = 'Assigned'
        
        data.append([
            str(pickup.id),
            pickup.created_at.strftime('%Y-%m-%d'),
            pickup.customer.get_full_name() or pickup.customer.username,
            collector_name,
            pickup.waste_category.name,
            f"{pickup.estimated_weight_kg}",
            f"{pickup.actual_weight_kg}" if pickup.actual_weight_kg else 'N/A',
            f"{price_value}",
            status_text
        ])
    
    # Create table with optimized column widths to prevent text overflow
    table = Table(data, colWidths=[0.4*inch, 0.8*inch, 0.9*inch, 0.9*inch, 0.8*inch, 0.9*inch, 1.1*inch, 0.9*inch, 1.2*inch])
    
    # Enhanced table style for better readability
    table.setStyle(TableStyle([
        # Header styling with smaller font to fit text
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        
        # Data rows styling
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # ID column center
        ('ALIGN', (1, 1), (1, -1), 'CENTER'),  # Date column center
        ('ALIGN', (2, 1), (2, -1), 'LEFT'),    # Customer column left
        ('ALIGN', (3, 1), (3, -1), 'LEFT'),    # Collector column left
        ('ALIGN', (4, 1), (4, -1), 'LEFT'),    # Category column left
        ('ALIGN', (5, 1), (5, -1), 'CENTER'),  # Weight column center
        ('ALIGN', (6, 1), (6, -1), 'CENTER'),  # Actual Weight column center
        ('ALIGN', (7, 1), (7, -1), 'RIGHT'),   # Price column right
        ('ALIGN', (8, 1), (8, -1), 'CENTER'),  # Status column center
        
        # Grid and borders - stronger borders to separate columns clearly
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 2, colors.darkgreen),
        ('LINEBEFORE', (5, 0), (5, -1), 1.5, colors.darkgray),  # Separate Weight column
        ('LINEBEFORE', (6, 0), (6, -1), 1.5, colors.darkgray),  # Separate Actual Weight column
        ('LINEBEFORE', (7, 0), (7, -1), 1.5, colors.darkgray),  # Separate Price column
        
        # Row backgrounds
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
        
        # Enhanced padding to prevent text overlap
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        
        # Text wrapping and overflow control
        ('WORDWRAP', (0, 0), (-1, -1), 'LTR'),
        
        # Vertical alignment
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(table)
    
    # Build PDF
    doc.build(elements)
    
    # Return PDF response
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    filename = f"kawadiwala_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response

@staff_member_required
def edit_category(request, category_id):
    """Edit waste category"""
    category = get_object_or_404(WasteCategory, id=category_id)
    
    if request.method == 'POST':
        name = request.POST.get('categoryName')
        rate_per_kg = request.POST.get('categoryRate')
        description = request.POST.get('categoryDescription')
        is_active = request.POST.get('categoryActive') == 'on'
        
        if name and rate_per_kg:
            category.name = name
            category.rate_per_kg = rate_per_kg
            category.description = description or ''
            category.is_active = is_active
            category.save()
            messages.success(request, f'Category "{name}" updated successfully!')
        else:
            messages.error(request, 'Name and rate are required fields.')
    
    return redirect('admin_dashboard')

@staff_member_required
def delete_category(request, category_id):
    """Delete waste category"""
    category = get_object_or_404(WasteCategory, id=category_id)
    
    if request.method == 'POST':
        category_name = category.name
        category.delete()
        messages.success(request, f'Category "{category_name}" deleted successfully!')
    
    return redirect('admin_dashboard')

@staff_member_required
def manage_users(request):
    """User management view for admin"""
    if not (request.user.role == 'admin' or request.user.is_superuser):
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('dashboard')
    
    # Get all users with their statistics
    users = User.objects.all().order_by('-date_joined')
    
    # Add pickup statistics for each user
    for user in users:
        if user.role == 'customer':
            user.pickup_count = PickupRequest.objects.filter(customer=user).count()
            user.completed_pickups = PickupRequest.objects.filter(customer=user, status='completed').count()
        elif user.role == 'collector':
            user.pickup_count = PickupRequest.objects.filter(collector=user).count()
            user.completed_pickups = PickupRequest.objects.filter(collector=user, status='completed').count()
        else:
            user.pickup_count = 0
            user.completed_pickups = 0
    
    context = {
        'users': users,
        'total_users': users.count(),
        'role_choices': User.ROLE_CHOICES,
    }
    return render(request, 'core/manage_users.html', context)

@staff_member_required
def create_admin_user(request):
    """Create a new admin user"""
    if not (request.user.role == 'admin' or request.user.is_superuser):
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        phone = request.POST.get('phone', '')
        
        # Validation
        if not username or not email or not password:
            messages.error(request, 'Username, email, and password are required.')
            return redirect('manage_users')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return redirect('manage_users')
        
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists.')
            return redirect('manage_users')
        
        try:
            # Create new admin user
            admin_user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                role='admin',
                is_staff=True
            )
            
            messages.success(request, f'Admin user "{username}" created successfully!')
        except Exception as e:
            messages.error(request, f'Error creating admin user: {str(e)}')
    
    return redirect('manage_users')

@staff_member_required
def toggle_user_status(request, user_id):
    """Activate/deactivate user account"""
    if not (request.user.role == 'admin' or request.user.is_superuser):
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('dashboard')
    
    user = get_object_or_404(User, id=user_id)
    
    # Prevent deactivating superuser or self
    if user.is_superuser or user == request.user:
        messages.error(request, 'Cannot deactivate this user account.')
        return redirect('manage_users')
    
    if request.method == 'POST':
        user.is_active = not user.is_active
        user.save()
        
        status = 'activated' if user.is_active else 'deactivated'
        messages.success(request, f'User {user.username} has been {status}')
    
    return redirect('manage_users')

@staff_member_required
def delete_user(request, user_id):
    """Delete user account (admin only)"""
    if not (request.user.role == 'admin' or request.user.is_superuser):
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('dashboard')
    
    user = get_object_or_404(User, id=user_id)
    
    # Prevent deleting superuser or self
    if user.is_superuser or user == request.user:
        messages.error(request, 'Cannot delete this user account.')
        return redirect('manage_users')
    
    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f'User {username} has been deleted successfully.')
    
    return redirect('manage_users')

@login_required
def user_profile(request):
    """User profile view with image upload"""
    if request.method == 'POST':
        # Handle profile update
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        email = request.POST.get('email', '')
        phone = request.POST.get('phone', '')
        address = request.POST.get('address', '')
        
        # Update user fields
        request.user.first_name = first_name
        request.user.last_name = last_name
        request.user.email = email
        request.user.phone = phone
        request.user.address = address
        
        # Handle profile image upload
        if 'profile_image' in request.FILES:
            request.user.profile_image = request.FILES['profile_image']
        
        request.user.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('user_profile')
    
    context = {
        'user': request.user,
    }
    return render(request, 'core/user_profile.html', context)
