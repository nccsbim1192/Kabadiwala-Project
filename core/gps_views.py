"""
Views for GPS Tracking functionality
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib import messages
import json
import logging

from .models import PickupRequest, CollectorLocation
from .services import GPSTrackingService, SMSService

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class UpdateLocationView(View):
    """API endpoint for collectors to update their GPS location"""
    
    def post(self, request):
        if not request.user.is_authenticated or request.user.role != 'collector':
            return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)
        
        try:
            data = json.loads(request.body)
            latitude = data.get('latitude')
            longitude = data.get('longitude')
            accuracy = data.get('accuracy', 0)
            pickup_request_id = data.get('pickup_request_id')
            
            if not latitude or not longitude:
                return JsonResponse({'success': False, 'error': 'Missing coordinates'}, status=400)
            
            pickup_request = None
            if pickup_request_id:
                pickup_request = get_object_or_404(PickupRequest, id=pickup_request_id, collector=request.user)
            
            result = GPSTrackingService.update_collector_location(
                request.user, latitude, longitude, accuracy, pickup_request
            )
            
            return JsonResponse(result)
            
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Location update error: {str(e)}")
            return JsonResponse({'success': False, 'error': 'Server error'}, status=500)


@login_required
def collector_location_api(request, collector_id):
    """API to get collector's current location"""
    if request.user.role not in ['admin', 'customer']:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)
    
    try:
        from .models import User
        collector = get_object_or_404(User, id=collector_id, role='collector')
        
        result = GPSTrackingService.get_collector_current_location(collector)
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Get collector location error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Server error'}, status=500)


@login_required
def pickup_tracking(request, pickup_id):
    """View to track a specific pickup with GPS"""
    pickup_request = get_object_or_404(PickupRequest, id=pickup_id)
    
    # Check permissions
    if request.user.role == 'customer' and pickup_request.customer != request.user:
        messages.error(request, 'You can only track your own pickups.')
        return redirect('customer_dashboard')
    elif request.user.role == 'collector' and pickup_request.collector != request.user:
        messages.error(request, 'You can only track your assigned pickups.')
        return redirect('collector_dashboard')
    
    # Get tracking data
    tracking_result = GPSTrackingService.track_pickup_journey(pickup_request)
    
    # Get collector's current location if available
    collector_location = None
    if pickup_request.collector:
        location_result = GPSTrackingService.get_collector_current_location(pickup_request.collector)
        if location_result['success']:
            collector_location = location_result
    
    context = {
        'pickup_request': pickup_request,
        'tracking_data': tracking_result.get('journey', []),
        'collector_location': collector_location,
        'google_maps_api_key': getattr(settings, 'GOOGLE_MAPS_API_KEY', '')
    }
    
    return render(request, 'core/gps/pickup_tracking.html', context)


@login_required
def live_tracking_dashboard(request):
    """Live tracking dashboard for admin to see all active collectors"""
    if request.user.role != 'admin':
        messages.error(request, 'Admin access required.')
        return redirect('dashboard')
    
    # Get all active pickups with collectors
    active_pickups = PickupRequest.objects.filter(
        status__in=['assigned', 'in_progress'],
        collector__isnull=False
    ).select_related('collector', 'customer', 'waste_category')
    
    # Get recent locations for each collector
    collector_locations = {}
    for pickup in active_pickups:
        location_result = GPSTrackingService.get_collector_current_location(pickup.collector)
        if location_result['success']:
            collector_locations[pickup.collector.id] = location_result
    
    context = {
        'active_pickups': active_pickups,
        'collector_locations': collector_locations,
        'google_maps_api_key': getattr(settings, 'GOOGLE_MAPS_API_KEY', '')
    }
    
    return render(request, 'core/gps/live_tracking_dashboard.html', context)


@login_required
def nearby_collectors_api(request):
    """API to find collectors near a specific location"""
    if request.user.role != 'admin':
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)
    
    try:
        latitude = float(request.GET.get('latitude'))
        longitude = float(request.GET.get('longitude'))
        radius = float(request.GET.get('radius', 5))  # Default 5km radius
        
        result = GPSTrackingService.get_collectors_near_location(latitude, longitude, radius)
        
        # Format response for JSON
        if result['success']:
            collectors_data = []
            for item in result['collectors']:
                collectors_data.append({
                    'id': item['collector'].id,
                    'username': item['collector'].username,
                    'phone': item['collector'].phone,
                    'distance': round(item['distance'], 2),
                    'latitude': float(item['location'].latitude),
                    'longitude': float(item['location'].longitude),
                    'last_update': item['location'].timestamp.isoformat()
                })
            
            return JsonResponse({
                'success': True,
                'collectors': collectors_data
            })
        else:
            return JsonResponse(result)
            
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid coordinates'}, status=400)
    except Exception as e:
        logger.error(f"Nearby collectors error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Server error'}, status=500)


@login_required
def collector_gps_dashboard(request):
    """GPS dashboard for collectors to manage their location sharing"""
    if request.user.role != 'collector':
        messages.error(request, 'Collector access required.')
        return redirect('dashboard')
    
    # Get collector's recent locations
    recent_locations = CollectorLocation.objects.filter(
        collector=request.user
    ).order_by('-timestamp')[:10]
    
    # Get active pickups
    active_pickups = PickupRequest.objects.filter(
        collector=request.user,
        status__in=['assigned', 'in_progress']
    ).select_related('customer', 'waste_category')
    
    context = {
        'recent_locations': recent_locations,
        'active_pickups': active_pickups,
        'google_maps_api_key': getattr(settings, 'GOOGLE_MAPS_API_KEY', '')
    }
    
    return render(request, 'core/gps/collector_gps_dashboard.html', context)


@csrf_exempt
def gps_webhook(request):
    """Webhook endpoint for external GPS tracking services"""
    try:
        if request.method == 'POST':
            data = json.loads(request.body)
            
            # Validate webhook data (implement your validation logic)
            collector_id = data.get('collector_id')
            latitude = data.get('latitude')
            longitude = data.get('longitude')
            accuracy = data.get('accuracy', 0)
            
            if collector_id and latitude and longitude:
                from .models import User
                collector = User.objects.get(id=collector_id, role='collector')
                
                result = GPSTrackingService.update_collector_location(
                    collector, latitude, longitude, accuracy
                )
                
                return JsonResponse(result)
            else:
                return JsonResponse({'success': False, 'error': 'Missing required data'}, status=400)
        else:
            return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
            
    except Exception as e:
        logger.error(f"GPS webhook error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Server error'}, status=500)


# Import settings for Google Maps API key
from django.conf import settings
