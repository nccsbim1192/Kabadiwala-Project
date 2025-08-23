# kawadiwala/urls.py (main project URLs)
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
]

# core/urls.py (app URLs)
from django.urls import path
from . import views

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
    
    # Static Pages
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
]
