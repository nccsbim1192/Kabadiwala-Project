"""
Views for Payment Gateway Integration
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.utils import timezone
import json
import logging

from .models import Transaction, PickupRequest, CreditPackage, CreditPurchase, CollectorCreditAccount
from .services import PaymentGatewayService, SMSService

logger = logging.getLogger(__name__)


@login_required
def initiate_payment(request, transaction_id):
    """Initiate payment for a transaction"""
    transaction = get_object_or_404(Transaction, id=transaction_id, customer=request.user)
    
    if request.method == 'POST':
        payment_method = request.POST.get('payment_method')
        
        if payment_method not in ['esewa', 'khalti', 'ime_pay', 'fonepay']:
            return JsonResponse({'success': False, 'error': 'Invalid request method'})
        
        transaction.payment_method = payment_method
        transaction.save()
        
        # Initiate payment based on selected method
        if payment_method == 'esewa':
            result = PaymentGatewayService.initiate_esewa_payment(transaction)
        elif payment_method == 'khalti':
            result = PaymentGatewayService.initiate_khalti_payment(transaction)
        else:
            # For other payment methods, redirect to a generic payment page
            messages.info(request, f'Please complete payment via {payment_method.upper()}')
            return redirect('payment_instructions', transaction_id=transaction.id)
        
        if result['success']:
            if payment_method == 'esewa':
                # Redirect to eSewa with form data
                return render(request, 'core/payment/esewa_redirect.html', {
                    'payment_url': result['payment_url'],
                    'payment_data': result['payment_data']
                })
            elif payment_method == 'khalti':
                # Redirect to Khalti payment URL
                return redirect(result['payment_url'])
        else:
            messages.error(request, f'Payment initiation failed: {result.get("error")}')
            return redirect('customer_dashboard')
    
    context = {
        'transaction': transaction,
        'pickup_request': transaction.pickup_request
    }
    return render(request, 'core/payment/initiate_payment.html', context)


@csrf_exempt
def esewa_success(request):
    """Handle eSewa payment success callback"""
    try:
        # Get payment details from eSewa response
        oid = request.GET.get('oid')  # Our transaction ID
        amt = request.GET.get('amt')
        refId = request.GET.get('refId')  # eSewa reference ID
        
        if oid and amt and refId:
            # Extract transaction ID from oid
            transaction_id = oid.replace('KAWADI-', '')
            transaction = get_object_or_404(Transaction, id=transaction_id)
            
            # Verify payment with eSewa
            gateway_response = {
                'oid': oid,
                'amt': amt,
                'refId': refId
            }
            
            verification_result = PaymentGatewayService.verify_payment(transaction, gateway_response)
            
            if verification_result['success'] and verification_result.get('verified'):
                # Payment successful
                messages.success(request, 'Payment completed successfully!')
                
                # Send SMS notification
                SMSService.send_payment_received_sms(transaction)
                
                return redirect('payment_success', transaction_id=transaction.id)
            else:
                messages.error(request, 'Payment verification failed.')
                return redirect('payment_failure', transaction_id=transaction.id)
        else:
            messages.error(request, 'Invalid payment response.')
            return redirect('customer_dashboard')
            
    except Exception as e:
        logger.error(f"eSewa success callback error: {str(e)}")
        messages.error(request, 'Payment processing error.')
        return redirect('customer_dashboard')


@csrf_exempt
def esewa_failure(request):
    """Handle eSewa payment failure callback"""
    messages.error(request, 'Payment was cancelled or failed.')
    return redirect('customer_dashboard')


@csrf_exempt
def khalti_callback(request):
    """Handle Khalti payment callback"""
    try:
        if request.method == 'GET':
            pidx = request.GET.get('pidx')
            status = request.GET.get('status')
            
            if pidx and status:
                # Find transaction by pidx
                transaction = get_object_or_404(Transaction, gateway_transaction_id=pidx)
                
                if status == 'Completed':
                    # Verify payment with Khalti
                    gateway_response = {'pidx': pidx, 'status': status}
                    verification_result = PaymentGatewayService.verify_payment(transaction, gateway_response)
                    
                    if verification_result['success'] and verification_result.get('verified'):
                        messages.success(request, 'Payment completed successfully!')
                        
                        # Send SMS notification
                        SMSService.send_payment_received_sms(transaction)
                        
                        return redirect('payment_success', transaction_id=transaction.id)
                    else:
                        messages.error(request, 'Payment verification failed.')
                        return redirect('payment_failure', transaction_id=transaction.id)
                else:
                    messages.error(request, f'Payment {status.lower()}.')
                    return redirect('payment_failure', transaction_id=transaction.id)
            else:
                messages.error(request, 'Invalid payment response.')
                return redirect('customer_dashboard')
                
    except Exception as e:
        logger.error(f"Khalti callback error: {str(e)}")
        messages.error(request, 'Payment processing error.')
        return redirect('customer_dashboard')


@login_required
def payment_success(request, transaction_id):
    """Payment success page"""
    transaction = get_object_or_404(Transaction, id=transaction_id, customer=request.user)
    
    context = {
        'transaction': transaction,
        'pickup_request': transaction.pickup_request
    }
    return render(request, 'core/payment/payment_success.html', context)


@login_required
def payment_failure(request, transaction_id):
    """Payment failure page"""
    transaction = get_object_or_404(Transaction, id=transaction_id, customer=request.user)
    
    context = {
        'transaction': transaction,
        'pickup_request': transaction.pickup_request
    }
    return render(request, 'core/payment/payment_failure.html', context)


@login_required
def payment_instructions(request, transaction_id):
    """Payment instructions for manual payment methods"""
    transaction = get_object_or_404(Transaction, id=transaction_id, customer=request.user)
    
    context = {
        'transaction': transaction,
        'pickup_request': transaction.pickup_request
    }
    return render(request, 'core/payment/payment_instructions.html', context)


@login_required
def payment_history(request):
    """View payment history for customer"""
    transactions = Transaction.objects.filter(
        customer=request.user
    ).select_related('pickup_request', 'collector').order_by('-transaction_date')
    
    context = {
        'transactions': transactions
    }
    return render(request, 'core/payment/payment_history.html', context)


@login_required
def transaction_details(request, transaction_id):
    """View detailed transaction information"""
    transaction = get_object_or_404(Transaction, id=transaction_id, customer=request.user)
    
    context = {
        'transaction': transaction,
        'pickup_request': transaction.pickup_request,
        'gateway_logs': transaction.gateway_logs.all()
    }
    return render(request, 'core/payment/transaction_details.html', context)


@login_required
def buy_credits(request):
    """Display credit packages for purchase"""
    if request.user.role != 'collector':
        messages.error(request, 'Only collectors can purchase credits.')
        return redirect('home')
    
    packages = CreditPackage.objects.filter(is_active=True).order_by('purchase_amount')
    
    # Get collector's current credit balance
    credit_account, created = CollectorCreditAccount.objects.get_or_create(
        collector=request.user
    )
    
    context = {
        'packages': packages,
        'credit_account': credit_account,
    }
    return render(request, 'core/payment/buy_credits.html', context)


@login_required
def initiate_credit_purchase(request, package_id):
    """Initiate credit purchase with Khalti"""
    if request.user.role != 'collector':
        messages.error(request, 'Only collectors can purchase credits.')
        return redirect('home')
    
    package = get_object_or_404(CreditPackage, id=package_id, is_active=True)
    
    if request.method == 'POST':
        payment_method = request.POST.get('payment_method')
        
        if payment_method not in ['khalti', 'esewa', 'bank_transfer']:
            messages.error(request, 'Invalid payment method selected.')
            return redirect('buy_credits')
        
        # Create credit purchase record
        credit_purchase = CreditPurchase.objects.create(
            collector=request.user,
            package=package,
            amount_paid=package.purchase_amount,
            credits_received=package.credit_amount,
            bonus_credits=package.bonus_credits,
            payment_method=payment_method,
            payment_status='pending'
        )
        
        # Initiate payment based on selected method
        if payment_method == 'khalti':
            from django.urls import reverse
            result = PaymentGatewayService.initiate_khalti_payment(
                request=request,
                order_id=credit_purchase.id,
                amount=package.purchase_amount,
                return_url=request.build_absolute_uri(reverse('khalti_credit_callback')),
                order_type='credit_purchase'
            )
            
            if 'error' not in result:
                # Store payment details
                credit_purchase.payment_reference = result.get('pidx')
                credit_purchase.save()
                
                # Redirect to Khalti payment page
                return render(request, 'core/payment/khalti_credit_redirect.html', {
                    'payment_url': result.get('payment_url'),
                    'credit_purchase': credit_purchase,
                    'package': package
                })
            else:
                messages.error(request, f'Payment initiation failed: {result.get("error")}')
                credit_purchase.payment_status = 'failed'
                credit_purchase.save()
                return redirect('buy_credits')
    
    # If GET request, redirect back to buy credits page
    return redirect('buy_credits')


@csrf_exempt
def khalti_credit_callback(request):
    """Handle Khalti payment callback for credit purchases"""
    try:
        # Get payment details from callback
        pidx = request.GET.get('pidx')
        status = request.GET.get('status')
        
        if not pidx:
            messages.error(request, 'Invalid payment callback.')
            return redirect('buy_credits')
        
        # Find the credit purchase
        try:
            credit_purchase = CreditPurchase.objects.get(
                payment_reference=pidx,
                payment_method='khalti'
            )
        except CreditPurchase.DoesNotExist:
            messages.error(request, 'Credit purchase not found.')
            return redirect('buy_credits')
        
        # Verify payment with Khalti
        verification_result = PaymentGatewayService.verify_khalti_payment(
            pidx, 
            float(credit_purchase.amount_paid)
        )
        
        if 'error' not in verification_result and verification_result.get('status') == 'Completed':
            # Payment successful - complete the credit purchase
            logger.info(f"Payment verified successfully for credit purchase {credit_purchase.id}")
            success = credit_purchase.complete_purchase()
            
            if success:
                logger.info(f"Credit purchase {credit_purchase.id} completed successfully")
                messages.success(request, f'Credit purchase successful! Rs.{credit_purchase.credits_received + credit_purchase.bonus_credits} credits added to your account.')
                
                # Send SMS notification
                SMSService.send_sms(
                    credit_purchase.collector,
                    f'Credit purchase successful! Rs.{credit_purchase.credits_received + credit_purchase.bonus_credits} credits added to your Kawadiwala account.',
                    'credit_purchase'
                )
            else:
                logger.error(f"Credit purchase {credit_purchase.id} completion failed")
                messages.error(request, 'Credit purchase processing failed.')
        else:
            # Payment failed
            logger.warning(f"Payment verification failed for credit purchase {credit_purchase.id}: {verification_result}")
            credit_purchase.payment_status = 'failed'
            credit_purchase.save()
            messages.error(request, 'Payment verification failed.')
        
        return redirect('collector_dashboard')
        
    except Exception as e:
        logger.error(f"Khalti credit callback error: {str(e)}")
        messages.error(request, 'Payment processing error.')
        return redirect('buy_credits')


@login_required
def khalti_payment_verify(request):
    """General Khalti payment verification endpoint"""
    try:
        pidx = request.GET.get('pidx')
        status = request.GET.get('status')
        
        if not pidx:
            messages.error(request, 'Invalid payment verification.')
            return redirect('home')
        
        # Determine if this is a credit purchase or transaction payment
        # Check credit purchases first
        credit_purchase = CreditPurchase.objects.filter(
            payment_reference=pidx,
            payment_method='khalti'
        ).first()
        
        if credit_purchase:
            # This is a credit purchase - redirect to credit callback
            return redirect(f'/payment/khalti/credit/callback/?pidx={pidx}&status={status}')
        
        # Check for regular transactions
        transaction = Transaction.objects.filter(
            gateway_transaction_id=pidx,
            payment_method='khalti'
        ).first()
        
        if transaction:
            # This is a regular transaction payment
            verification_result = PaymentGatewayService.verify_khalti_payment(pidx, float(transaction.amount))
            
            if 'error' not in verification_result and verification_result.get('status') == 'Completed':
                transaction.payment_status = 'completed'
                transaction.is_paid = True
                transaction.payment_completed_at = timezone.now()
                transaction.save()
                
                # Update pickup status
                transaction.pickup_request.status = 'completed'
                transaction.pickup_request.save()
                
                messages.success(request, 'Payment successful!')
                return redirect('customer_dashboard')
            else:
                messages.error(request, 'Payment verification failed.')
                return redirect('customer_dashboard')
        
        messages.error(request, 'Payment record not found.')
        return redirect('home')
        
    except Exception as e:
        logger.error(f"Payment verification error: {str(e)}")
        messages.error(request, 'Payment verification error.')
        return redirect('home')
