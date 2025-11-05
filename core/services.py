"""
Service classes for Payment Gateway, SMS, and GPS functionality
"""
import requests
import json
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from .models import Transaction, SMSNotification, CollectorLocation, PaymentGatewayLog
import logging

logger = logging.getLogger(__name__)


class PaymentGatewayService:
    """
Services for Kawadiwala - SMS, GPS, Payment Gateway and other external integrations
"""
    @staticmethod
    def initiate_esewa_payment(transaction):
        """Initiate eSewa payment"""
        try:
            # eSewa API configuration
            esewa_config = {
                'merchant_code': getattr(settings, 'ESEWA_MERCHANT_CODE', 'test_merchant'),
                'success_url': f"{getattr(settings, 'BASE_URL', 'http://localhost:8000')}/payment/esewa/success/",
                'failure_url': f"{getattr(settings, 'BASE_URL', 'http://localhost:8000')}/payment/esewa/failure/",
            }
            
            payment_data = {
                'amt': str(transaction.amount),
                'pdc': '0',  # Delivery charge
                'psc': '0',  # Service charge
                'txAmt': str(transaction.amount - transaction.collector_commission),
                'tAmt': str(transaction.amount),
                'pid': f"KAWADI-{transaction.id}",
                'scd': esewa_config['merchant_code'],
                'su': esewa_config['success_url'],
                'fu': esewa_config['failure_url']
            }
            
            # Log the payment initiation
            PaymentGatewayLog.objects.create(
                transaction=transaction,
                gateway_name='esewa',
                request_data=payment_data
            )
            
            transaction.payment_status = 'processing'
            transaction.payment_initiated_at = timezone.now()
            transaction.save()
            
            return {
                'success': True,
                'payment_url': 'https://uat.esewa.com.np/epay/main',
                'payment_data': payment_data
            }
            
        except Exception as e:
            logger.error(f"eSewa payment initiation failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def initiate_khalti_payment(request, order_id, amount, return_url=None, order_type='transaction'):
        """
        Initiate Khalti payment using the eBilling API
        
        Args:
            request: HttpRequest object
            order_id: Order ID (transaction_id or credit_purchase_id)
            amount: Amount in NPR (will be converted to paisa)
            return_url: Callback URL after payment
            order_type: 'transaction' for waste payments, 'credit_purchase' for credit buying
            
        Returns:
            dict: Response from Khalti API or error message
        """
        if not return_url:
            return_url = request.build_absolute_uri(reverse('khalti_payment_verify'))
        
        # Sandbox endpoint for test keys
        url = "https://a.khalti.com/api/v2/epayment/initiate/"
        
        # Get the secret key from settings
        secret_key = getattr(settings, 'KHALTI_SECRET_KEY', '')
        if not secret_key:
            logger.error("Khalti secret key not configured")
            return {'error': 'Khalti configuration error'}
        
        # Use the key as provided (works with both test and live keys)
        # Don't modify the key format - Khalti accepts keys as-is
        
        # Log the first few characters of the key for verification
        logger.info(f"Using Khalti key: {secret_key[:16]}...")
        
        # Khalti v2 API headers
        headers = {
            'Authorization': f'Key {secret_key}',
            'Content-Type': 'application/json',
        }
        
        # Determine order name based on type
        if order_type == 'credit_purchase':
            order_name = f'Kawadiwala Credit Purchase #{order_id}'
        else:
            order_name = f'Waste Pickup Payment #{order_id}'
        
        # Prepare the payload
        payload = {
            'return_url': return_url,
            'website_url': request.build_absolute_uri('/'),
            'amount': int(amount * 100),  # Convert to paisa
            'purchase_order_id': f'kawadi_{order_type}_{order_id}',
            'purchase_order_name': order_name,
            'customer_info': {
                'name': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
                'email': request.user.email if request.user.is_authenticated else '',
                'phone': getattr(request.user, 'phone', '')
            }
        }
        
        try:
            logger.info(f"Initiating Khalti payment for {order_type} {order_id}")
            logger.debug(f"Request URL: {url}")
            logger.debug(f"Headers: {headers}")
            logger.debug(f"Payload: {payload}")
            
            # Make the API request with a timeout
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            # Log the raw response for debugging
            logger.info(f"Response status code: {response.status_code}")
            logger.info(f"Response headers: {dict(response.headers)}")
            logger.info(f"Response content: {response.text}")
            
            # Check for HTTP errors
            response.raise_for_status()
            
            # Parse the JSON response
            result = response.json()
            logger.info(f"Khalti payment initiated successfully for {order_type} {order_id}")
            return result
            
        except requests.exceptions.RequestException as e:
            # Log the full error details
            logger.error(f"Khalti API request failed: {str(e)}")
            
            # Get detailed error information if available
            error_detail = str(e)
            status_code = None
            response_text = None
            
            if hasattr(e, 'response') and e.response is not None:
                status_code = getattr(e.response, 'status_code', None)
                logger.error(f"Status code: {status_code}")
                
                try:
                    response_text = e.response.text
                    logger.error(f"Response text: {response_text}")
                    error_detail = e.response.json()
                except ValueError:
                    error_detail = response_text or str(e)
            
            logger.error(f"Khalti payment initiation failed: {error_detail}")
            return {
                'error': 'Payment initiation failed',
                'detail': error_detail,
                'status_code': status_code
            }
    
    @staticmethod
    def verify_payment(transaction, gateway_response):
        """Verify payment completion"""
        try:
            if transaction.payment_method == 'khalti':
                return PaymentGatewayService._verify_khalti_payment(transaction, gateway_response)
            elif transaction.payment_method == 'esewa':
                return PaymentGatewayService._verify_esewa_payment(transaction, gateway_response)
            else:
                return {'success': False, 'error': 'Unsupported payment method'}
                
        except Exception as e:
            logger.error(f"Payment verification failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def verify_khalti_payment(payment_token, amount=None):
        """
        Verify Khalti payment using the eBilling API
        
        Args:
            payment_token: Payment token from Khalti (pidx for eBilling API)
            amount: Amount in NPR (optional, for validation)
            
        Returns:
            dict: Verification response or error message
        """
        # Sandbox endpoint for test keys
        url = "https://a.khalti.com/api/v2/epayment/lookup/"
        
        # Get the secret key from settings
        secret_key = getattr(settings, 'KHALTI_SECRET_KEY', '')
        if not secret_key:
            logger.error("Khalti secret key not configured")
            return {'error': 'Khalti configuration error'}
        
        # Use the key as provided (works with both test and live keys)
        # Don't modify the key format - Khalti accepts keys as-is
        
        headers = {
            'Authorization': f'Key {secret_key}',
            'Content-Type': 'application/json',
        }
        
        payload = {
            'pidx': payment_token
        }
        
        try:
            logger.info(f"Verifying Khalti payment with token: {payment_token}")
            logger.debug(f"Request URL: {url}")
            logger.debug(f"Headers: {headers}")
            logger.debug(f"Payload: {payload}")
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Khalti payment verification response: {result}")
            
            # Optionally validate the amount
            if amount is not None and int(amount * 100) != result.get('total_amount'):
                logger.warning(f"Amount mismatch: expected {amount*100}, got {result.get('total_amount')}")
                
            return result
            
        except requests.exceptions.RequestException as e:
            error_detail = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                except ValueError:
                    error_detail = e.response.text or str(e)
            
            logger.error(f"Khalti payment verification failed: {error_detail}")
            return {
                'error': 'Payment verification failed',
                'detail': error_detail,
                'status_code': getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
            }
    
    @staticmethod
    def _verify_khalti_payment(transaction, gateway_response):
        """Legacy verify function for backward compatibility"""
        return PaymentGatewayService.verify_khalti_payment(
            gateway_response.get('pidx'),
            float(transaction.amount)
        )
    
    @staticmethod
    def _verify_esewa_payment(transaction, gateway_response):
        """Verify eSewa payment"""
        # eSewa verification logic would go here
        # For now, we'll simulate successful verification
        transaction.payment_status = 'completed'
        transaction.payment_completed_at = timezone.now()
        transaction.is_paid = True
        transaction.gateway_response = gateway_response
        transaction.save()
        
        return {'success': True, 'verified': True}


class SMSService:
    """Service class for sending SMS notifications"""
    
    @staticmethod
    def send_sms(user, message, notification_type, pickup_request=None):
        """Send SMS notification to user"""
        try:
            phone_number = user.phone
            if not phone_number:
                logger.warning(f"No phone number for user {user.username}")
                return {'success': False, 'error': 'No phone number'}
            
            # Create SMS notification record
            sms_notification = SMSNotification.objects.create(
                user=user,
                pickup_request=pickup_request,
                phone_number=phone_number,
                message=message,
                notification_type=notification_type
            )
            
            # Send SMS using your preferred SMS gateway
            # For Nepal, you might use services like Sparrow SMS, etc.
            sms_result = SMSService._send_via_gateway(phone_number, message)
            
            if sms_result['success']:
                sms_notification.status = 'sent'
                sms_notification.sent_at = timezone.now()
                sms_notification.gateway_message_id = sms_result.get('message_id')
                sms_notification.gateway_response = sms_result.get('response')
            else:
                sms_notification.status = 'failed'
                sms_notification.gateway_response = {'error': sms_result.get('error')}
            
            sms_notification.save()
            return sms_result
            
        except Exception as e:
            logger.error(f"SMS sending failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def _send_via_gateway(phone_number, message):
        """Send SMS via SMS gateway (implement with your preferred provider)"""
        try:
            # Example implementation for Sparrow SMS (Nepal)
            # You'll need to replace this with your actual SMS gateway
            
            sms_config = {
                'token': getattr(settings, 'SMS_GATEWAY_TOKEN', 'your_sms_token'),
                'from': getattr(settings, 'SMS_FROM_NUMBER', 'KAWADI'),
            }
            
            # Simulate SMS sending for development
            if getattr(settings, 'DEBUG', True):
                logger.info(f"SMS (DEBUG): To {phone_number}: {message}")
                return {
                    'success': True,
                    'message_id': f"DEBUG_{timezone.now().timestamp()}",
                    'response': {'status': 'sent', 'debug': True}
                }
            
            # Actual SMS sending code would go here
            # Example for Sparrow SMS:
            # response = requests.post(
            #     'http://api.sparrowsms.com/v2/sms/',
            #     data={
            #         'token': sms_config['token'],
            #         'from': sms_config['from'],
            #         'to': phone_number,
            #         'text': message
            #     }
            # )
            
            return {'success': True, 'message_id': 'test_message_id'}
            
        except Exception as e:
            logger.error(f"SMS gateway error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def send_pickup_assigned_sms(pickup_request):
        """Send SMS when pickup is assigned to collector"""
        message = f"Hello {pickup_request.customer.username}, your waste pickup request has been assigned to {pickup_request.collector.username}. Pickup date: {pickup_request.pickup_date}. Track your pickup in the app."
        return SMSService.send_sms(
            pickup_request.customer,
            message,
            'pickup_assigned',
            pickup_request
        )
    
    @staticmethod
    def send_pickup_completed_sms(pickup_request):
        """Send SMS when pickup is completed"""
        message = f"Your waste pickup has been completed! Weight: {pickup_request.actual_weight_kg}kg, Amount: Rs.{pickup_request.actual_price}. Thank you for choosing Kawadiwala!"
        return SMSService.send_sms(
            pickup_request.customer,
            message,
            'pickup_completed',
            pickup_request
        )
    
    @staticmethod
    def send_payment_received_sms(transaction):
        """Send SMS when payment is received"""
        message = f"Payment of Rs.{transaction.amount} received successfully via {transaction.get_payment_method_display()}. Transaction ID: {transaction.gateway_transaction_id}. Thank you!"
        return SMSService.send_sms(
            transaction.customer,
            message,
            'payment_received'
        )


class GPSTrackingService:
    """Service class for GPS tracking functionality"""
    
    @staticmethod
    def update_collector_location(collector, latitude, longitude, accuracy, pickup_request=None):
        """Update collector's GPS location"""
        try:
            # Calculate distance to pickup location if pickup_request is provided
            distance_to_pickup = None
            is_at_pickup = False
            
            if pickup_request and hasattr(pickup_request, 'latitude') and hasattr(pickup_request, 'longitude'):
                distance_to_pickup = GPSTrackingService._calculate_distance(
                    latitude, longitude,
                    pickup_request.latitude, pickup_request.longitude
                )
                # Consider collector at pickup location if within 100 meters
                is_at_pickup = distance_to_pickup < 0.1
            
            # Create location record
            location = CollectorLocation.objects.create(
                collector=collector,
                pickup_request=pickup_request,
                latitude=Decimal(str(latitude)),
                longitude=Decimal(str(longitude)),
                accuracy=accuracy,
                is_at_pickup_location=is_at_pickup,
                distance_to_pickup=distance_to_pickup
            )
            
            return {
                'success': True,
                'location_id': location.id,
                'is_at_pickup': is_at_pickup,
                'distance_to_pickup': distance_to_pickup
            }
            
        except Exception as e:
            logger.error(f"GPS location update failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def get_collector_current_location(collector):
        """Get collector's most recent location"""
        try:
            location = CollectorLocation.objects.filter(
                collector=collector,
                is_active=True
            ).first()
            
            if location:
                return {
                    'success': True,
                    'latitude': float(location.latitude),
                    'longitude': float(location.longitude),
                    'accuracy': location.accuracy,
                    'timestamp': location.timestamp,
                    'google_maps_url': location.google_maps_url
                }
            else:
                return {'success': False, 'error': 'No location data found'}
                
        except Exception as e:
            logger.error(f"Get collector location failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def get_collectors_near_location(latitude, longitude, radius_km=5):
        """Find collectors near a specific location"""
        try:
            # This is a simplified implementation
            # In production, you'd use PostGIS or similar for proper geographic queries
            recent_locations = CollectorLocation.objects.filter(
                is_active=True,
                timestamp__gte=timezone.now() - timezone.timedelta(minutes=30)
            ).select_related('collector')
            
            nearby_collectors = []
            for location in recent_locations:
                distance = GPSTrackingService._calculate_distance(
                    latitude, longitude,
                    float(location.latitude), float(location.longitude)
                )
                
                if distance <= radius_km:
                    nearby_collectors.append({
                        'collector': location.collector,
                        'distance': distance,
                        'location': location
                    })
            
            # Sort by distance
            nearby_collectors.sort(key=lambda x: x['distance'])
            
            return {
                'success': True,
                'collectors': nearby_collectors
            }
            
        except Exception as e:
            logger.error(f"Find nearby collectors failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def _calculate_distance(lat1, lon1, lat2, lon2):
        """Calculate distance between two GPS coordinates (Haversine formula)"""
        import math
        
        # Convert latitude and longitude from degrees to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # Radius of earth in kilometers
        r = 6371
        
        return c * r
    
    @staticmethod
    def track_pickup_journey(pickup_request):
        """Get the complete journey tracking for a pickup"""
        try:
            locations = CollectorLocation.objects.filter(
                pickup_request=pickup_request
            ).order_by('timestamp')
            
            journey_data = []
            for location in locations:
                journey_data.append({
                    'latitude': float(location.latitude),
                    'longitude': float(location.longitude),
                    'timestamp': location.timestamp,
                    'is_at_pickup': location.is_at_pickup_location,
                    'distance_to_pickup': location.distance_to_pickup
                })
            
            return {
                'success': True,
                'journey': journey_data,
                'total_points': len(journey_data)
            }
            
        except Exception as e:
            logger.error(f"Track pickup journey failed: {str(e)}")
            return {'success': False, 'error': str(e)}
