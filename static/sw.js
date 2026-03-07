// Service Worker for Push Notifications

self.addEventListener('install', (event) => {
    console.log('Service Worker installing...');
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    console.log('Service Worker activating...');
    event.waitUntil(clients.claim());
});

// Handle push notifications
self.addEventListener('push', (event) => {
    console.log('Push notification received:', event);
    
    let data = {};
    
    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data = { title: 'New Activity', body: event.data.text() };
        }
    }
    
    const title = data.title || 'Voice Log';
    const options = {
        body: data.body || 'New activity logged',
        tag: 'activity-alert',
        requireInteraction: false,
    };
    
    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

// Handle notification clicks
self.addEventListener('notificationclick', (event) => {
    console.log('Notification clicked:', event);
    
    event.notification.close();
    
    if (event.action === 'view' || !event.action) {
        // Open the app
        event.waitUntil(
            clients.openWindow('/')
        );
    }
});
