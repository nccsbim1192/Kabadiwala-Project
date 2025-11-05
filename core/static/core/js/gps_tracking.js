/**
 * GPS Tracking JavaScript for Kawadiwala Collectors
 */

class GPSTracker {
    constructor() {
        this.watchId = null;
        this.isTracking = false;
        this.lastPosition = null;
        this.updateInterval = 30000; // 30 seconds
        this.apiEndpoint = '/gps/update-location/';
    }

    /**
     * Start GPS tracking for collectors
     */
    startTracking(pickupRequestId = null) {
        if (!navigator.geolocation) {
            this.showError('Geolocation is not supported by this browser.');
            return false;
        }

        const options = {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 60000
        };

        this.watchId = navigator.geolocation.watchPosition(
            (position) => this.onLocationUpdate(position, pickupRequestId),
            (error) => this.onLocationError(error),
            options
        );

        this.isTracking = true;
        this.showSuccess('GPS tracking started');
        return true;
    }

    /**
     * Stop GPS tracking
     */
    stopTracking() {
        if (this.watchId !== null) {
            navigator.geolocation.clearWatch(this.watchId);
            this.watchId = null;
        }
        this.isTracking = false;
        this.showInfo('GPS tracking stopped');
    }

    /**
     * Handle location updates
     */
    onLocationUpdate(position, pickupRequestId) {
        const coords = position.coords;
        
        // Check if location has changed significantly (more than 10 meters)
        if (this.lastPosition && this.calculateDistance(
            this.lastPosition.latitude, this.lastPosition.longitude,
            coords.latitude, coords.longitude
        ) < 0.01) {
            return; // Skip if location hasn't changed much
        }

        const locationData = {
            latitude: coords.latitude,
            longitude: coords.longitude,
            accuracy: coords.accuracy,
            pickup_request_id: pickupRequestId
        };

        this.sendLocationUpdate(locationData);
        this.lastPosition = coords;
        
        // Update UI
        this.updateLocationDisplay(coords);
    }

    /**
     * Handle location errors
     */
    onLocationError(error) {
        let message = 'Location error: ';
        switch (error.code) {
            case error.PERMISSION_DENIED:
                message += 'Location access denied by user.';
                break;
            case error.POSITION_UNAVAILABLE:
                message += 'Location information is unavailable.';
                break;
            case error.TIMEOUT:
                message += 'Location request timed out.';
                break;
            default:
                message += 'An unknown error occurred.';
                break;
        }
        this.showError(message);
    }

    /**
     * Send location update to server
     */
    async sendLocationUpdate(locationData) {
        try {
            const response = await fetch(this.apiEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify(locationData)
            });

            const result = await response.json();
            
            if (result.success) {
                console.log('Location updated successfully');
                
                // Show notification if collector is at pickup location
                if (result.is_at_pickup) {
                    this.showSuccess('You have arrived at the pickup location!');
                }
            } else {
                console.error('Location update failed:', result.error);
                this.showError('Failed to update location: ' + result.error);
            }
        } catch (error) {
            console.error('Network error:', error);
            this.showError('Network error while updating location');
        }
    }

    /**
     * Calculate distance between two coordinates (in kilometers)
     */
    calculateDistance(lat1, lon1, lat2, lon2) {
        const R = 6371; // Radius of the Earth in kilometers
        const dLat = this.deg2rad(lat2 - lat1);
        const dLon = this.deg2rad(lon2 - lon1);
        const a = 
            Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.cos(this.deg2rad(lat1)) * Math.cos(this.deg2rad(lat2)) * 
            Math.sin(dLon/2) * Math.sin(dLon/2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        return R * c;
    }

    /**
     * Convert degrees to radians
     */
    deg2rad(deg) {
        return deg * (Math.PI/180);
    }

    /**
     * Get CSRF token from cookie
     */
    getCSRFToken() {
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    /**
     * Update location display in UI
     */
    updateLocationDisplay(coords) {
        const locationElement = document.getElementById('current-location');
        if (locationElement) {
            locationElement.innerHTML = `
                <strong>Current Location:</strong><br>
                Lat: ${coords.latitude.toFixed(6)}<br>
                Lng: ${coords.longitude.toFixed(6)}<br>
                Accuracy: ${coords.accuracy.toFixed(0)}m<br>
                <small>Updated: ${new Date().toLocaleTimeString()}</small>
            `;
        }

        // Update tracking status
        const statusElement = document.getElementById('tracking-status');
        if (statusElement) {
            statusElement.innerHTML = `
                <span class="badge bg-success">
                    <i class="fas fa-satellite-dish me-1"></i>Tracking Active
                </span>
            `;
        }
    }

    /**
     * Show success message
     */
    showSuccess(message) {
        this.showToast(message, 'success');
    }

    /**
     * Show error message
     */
    showError(message) {
        this.showToast(message, 'error');
    }

    /**
     * Show info message
     */
    showInfo(message) {
        this.showToast(message, 'info');
    }

    /**
     * Show toast notification
     */
    showToast(message, type = 'info') {
        // Use existing toast system if available
        if (typeof window.KawadiwalaSystem !== 'undefined' && window.KawadiwalaSystem.showToast) {
            window.KawadiwalaSystem.showToast(message, type);
        } else {
            // Fallback to console
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }

    /**
     * Get current position once
     */
    getCurrentLocation() {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) {
                reject(new Error('Geolocation is not supported'));
                return;
            }

            navigator.geolocation.getCurrentPosition(
                (position) => resolve(position.coords),
                (error) => reject(error),
                {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 60000
                }
            );
        });
    }
}

// Initialize GPS tracker
const gpsTracker = new GPSTracker();

// Auto-start tracking for collectors on pickup pages
document.addEventListener('DOMContentLoaded', function() {
    // Check if user is a collector and on a pickup-related page
    const userRole = document.body.dataset.userRole;
    const pickupId = document.body.dataset.pickupId;
    
    if (userRole === 'collector' && pickupId) {
        // Ask for permission to start tracking
        if (confirm('Start GPS tracking for this pickup?')) {
            gpsTracker.startTracking(pickupId);
        }
    }

    // Add event listeners for tracking controls
    const startTrackingBtn = document.getElementById('start-tracking');
    const stopTrackingBtn = document.getElementById('stop-tracking');
    
    if (startTrackingBtn) {
        startTrackingBtn.addEventListener('click', () => {
            const pickupId = startTrackingBtn.dataset.pickupId;
            gpsTracker.startTracking(pickupId);
        });
    }
    
    if (stopTrackingBtn) {
        stopTrackingBtn.addEventListener('click', () => {
            gpsTracker.stopTracking();
        });
    }
});

// Export for global use
window.GPSTracker = GPSTracker;
window.gpsTracker = gpsTracker;
