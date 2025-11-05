# core/urls.py (app URLs)
from django.urls import path
from . import views
from . import payment_views
from . import gps_views
from . import admin_views

urlpatterns = [
    # Authentication
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    
    # Dashboards
    path('dashboard/', views.dashboard, name='dashboard'),
    path('customer/', views.customer_dashboard, name='customer_dashboard'),
    path('collector/', views.collector_dashboard, name='collector_dashboard'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    
    # Pickup Management
    path('request-pickup/', views.request_pickup, name='request_pickup'),
    path('pickup-history/', views.pickup_history, name='pickup_history'),
    path('assign-pickup/<int:pickup_id>/', views.assign_pickup, name='assign_pickup'),
    path('update-pickup/<int:pickup_id>/', views.update_pickup, name='update_pickup'),
    path('cancel-pickup/<int:pickup_id>/', views.cancel_pickup, name='cancel_pickup'),
    
    # Admin management URLs
    path('admin-manage/update-pickup/<int:pickup_id>/', views.admin_update_pickup_status, name='admin_update_pickup_status'),
    path('admin-manage/approve-transaction/<int:transaction_id>/', views.admin_approve_transaction, name='admin_approve_transaction'),
    path('admin-manage/bulk-update-pickups/', views.admin_bulk_update_pickups, name='admin_bulk_update_pickups'),
    path('admin-manage/export-data/', views.export_data_pdf, name='export_data_pdf'),
    path('admin-manage/edit-category/<int:category_id>/', views.edit_category, name='edit_category'),
    path('admin-manage/delete-category/<int:category_id>/', views.delete_category, name='delete_category'),
    
    # User Management
    path('delete-account/', views.delete_account, name='delete_account'),
    path('profile/', views.user_profile, name='user_profile'),
    path('download-report/', views.customer_report_pdf, name='customer_report_pdf'),
    path('download-receipt/<int:pickup_id>/', views.download_pickup_receipt, name='download_pickup_receipt'),
    path('admin-manage/users/', views.manage_users, name='manage_users'),
    path('admin-manage/create-admin/', views.create_admin_user, name='create_admin_user'),
    path('admin-manage/toggle-user-status/<int:user_id>/', views.toggle_user_status, name='toggle_user_status'),
    path('admin-manage/delete-user/<int:user_id>/', views.delete_user, name='delete_user'),
    
    # Static Pages
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    
    # Payment Gateway URLs
    path('payment/initiate/<int:transaction_id>/', payment_views.initiate_payment, name='initiate_payment'),
    path('payment/esewa/success/', payment_views.esewa_success, name='esewa_success'),
    path('payment/esewa/failure/', payment_views.esewa_failure, name='esewa_failure'),
    path('payment/khalti/callback/', payment_views.khalti_callback, name='khalti_callback'),
    path('payment/success/<int:transaction_id>/', payment_views.payment_success, name='payment_success'),
    path('payment/failure/<int:transaction_id>/', payment_views.payment_failure, name='payment_failure'),
    path('payment/instructions/<int:transaction_id>/', payment_views.payment_instructions, name='payment_instructions'),
    path('payment/history/', payment_views.payment_history, name='payment_history'),
    path('payment/transaction/<int:transaction_id>/', payment_views.transaction_details, name='transaction_details'),
    
    # Credit Purchase URLs
    path('credits/buy/', payment_views.buy_credits, name='buy_credits'),
    path('credits/purchase/<int:package_id>/', payment_views.initiate_credit_purchase, name='initiate_credit_purchase'),
    path('payment/khalti/credit/callback/', payment_views.khalti_credit_callback, name='khalti_credit_callback'),
    path('payment/khalti/verify/', payment_views.khalti_payment_verify, name='khalti_payment_verify'),
    
    # API URLs
    path('api/credit-balance/', views.api_credit_balance, name='api_credit_balance'),
    
    # GPS Tracking URLs
    path('gps/update-location/', gps_views.UpdateLocationView.as_view(), name='update_location'),
    path('gps/collector-location/<int:collector_id>/', gps_views.collector_location_api, name='collector_location_api'),
    path('gps/pickup-tracking/<int:pickup_id>/', gps_views.pickup_tracking, name='pickup_tracking'),
    path('gps/live-dashboard/', gps_views.live_tracking_dashboard, name='live_tracking_dashboard'),
    path('gps/nearby-collectors/', gps_views.nearby_collectors_api, name='nearby_collectors_api'),
    path('gps/collector-dashboard/', gps_views.collector_gps_dashboard, name='collector_gps_dashboard'),
    path('gps/webhook/', gps_views.gps_webhook, name='gps_webhook'),
    
    # Custom Admin URLs
    path('custom-admin/', admin_views.custom_admin_dashboard, name='custom_admin_dashboard'),
    path('custom-admin/users/', admin_views.admin_user_management, name='admin_user_management'),
    path('custom-admin/users/create/', admin_views.admin_create_user, name='admin_create_user'),
    path('custom-admin/users/<int:user_id>/update/', admin_views.admin_update_user, name='admin_update_user'),
    path('custom-admin/pickups/', admin_views.admin_pickup_management, name='admin_pickup_management'),
    path('custom-admin/pickups/<int:pickup_id>/', admin_views.admin_pickup_details, name='admin_pickup_details'),
    path('custom-admin/pickups/<int:pickup_id>/edit/', admin_views.admin_pickup_edit, name='admin_pickup_edit'),
    path('custom-admin/transactions/<int:transaction_id>/', admin_views.admin_transaction_details, name='admin_transaction_details'),
    path('custom-admin/analytics/', admin_views.admin_analytics_dashboard, name='admin_analytics_dashboard'),
    path('custom-admin/settings/', admin_views.admin_system_settings, name='admin_system_settings'),
    path('custom-admin/export/', admin_views.admin_export_data, name='admin_export_data'),
    path('custom-admin/bulk-actions/', admin_views.admin_bulk_actions, name='admin_bulk_actions'),
]
