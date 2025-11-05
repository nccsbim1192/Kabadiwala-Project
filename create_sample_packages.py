#!/usr/bin/env python
"""
Script to create sample credit packages for testing Khalti integration
Run this with: python create_sample_packages.py
"""

import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kawadiwala.settings')
django.setup()

from core.models import CreditPackage

def create_sample_packages():
    """Create sample credit packages"""
    
    # Clear existing packages
    CreditPackage.objects.all().delete()
    
    packages = [
        {
            'name': 'Starter Pack',
            'purchase_amount': 1000,
            'credit_amount': 900,
            'is_popular': False,
            'bonus_credits': 0,
        },
        {
            'name': 'Professional Pack',
            'purchase_amount': 5000,
            'credit_amount': 4500,
            'is_popular': True,
            'bonus_credits': 100,
        },
        {
            'name': 'Business Pack',
            'purchase_amount': 10000,
            'credit_amount': 9000,
            'is_popular': False,
            'bonus_credits': 300,
        },
        {
            'name': 'Enterprise Pack',
            'purchase_amount': 25000,
            'credit_amount': 22500,
            'is_popular': False,
            'bonus_credits': 1000,
        }
    ]
    
    created_packages = []
    for pkg_data in packages:
        package = CreditPackage.objects.create(**pkg_data)
        created_packages.append(package)
        print(f"✅ Created: {package.name} - Pay Rs.{package.purchase_amount}, Get Rs.{package.credit_amount}")
        if package.bonus_credits > 0:
            print(f"   💰 Bonus: Rs.{package.bonus_credits} extra credits!")
    
    print(f"\n🎉 Successfully created {len(created_packages)} credit packages!")
    print("\nYou can now:")
    print("1. Visit http://127.0.0.1:8000/credits/buy/ to see the packages")
    print("2. Test Khalti payment integration")
    print("3. Create a collector account to purchase credits")

if __name__ == '__main__':
    create_sample_packages()
