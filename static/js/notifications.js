// Shared notification bell + dropdown + modal behavior
// Used on pages that include the notification header markup.

document.addEventListener('DOMContentLoaded', function () {
    const bell = document.getElementById('notificationBell');
    const dropdown = document.getElementById('notificationDropdown');
    const list = document.getElementById('notificationList');
    const badge = document.getElementById('notificationBadge');
    const modal = document.getElementById('notificationModal');
    if (!bell || !dropdown || !list || !badge || !modal) {
        return; // Page does not have notification UI
    }

    bell.addEventListener('click', function (e) {
        e.stopPropagation();
        dropdown.classList.toggle('active');
    });

    document.addEventListener('click', function (e) {
        const container = document.querySelector('.notification-container');
        if (container && !container.contains(e.target)) {
            dropdown.classList.remove('active');
        }
    });

    async function fetchNotifications() {
        try {
            const response = await fetch('/api/notifications');
            const data = await response.json();
            updateNotificationUI(data.notifications || [], data.unread_count || 0);
        } catch (err) {
            console.error('Error fetching notifications:', err);
        }
    }

    function getTimeAgo(date) {
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);
        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return diffMins + 'm ago';
        if (diffHours < 24) return diffHours + 'h ago';
        if (diffDays < 7) return diffDays + 'd ago';
        return date.toLocaleDateString();
    }

    function updateNotificationUI(notifications, unreadCount) {
        // Badge
        if (unreadCount > 0) {
            badge.textContent = unreadCount;
            badge.style.display = 'flex';
        } else {
            badge.style.display = 'none';
        }

        // List
        if (!notifications.length) {
            list.innerHTML = '<div class="notification-empty">No notifications yet</div>';
            return;
        }

        list.innerHTML = notifications.map(function (notif) {
            const date = new Date(notif.created_at);
            const timeAgo = getTimeAgo(date);
            const fullDateTime = date.toLocaleString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
            const notifData = JSON.stringify({
                id: notif.id,
                title: notif.title,
                message: notif.message,
                created_at: fullDateTime,
                is_read: notif.is_read
            }).replace(/"/g, '&quot;');
            return (
                '<div class="notification-item ' + (notif.is_read ? 'read' : 'unread') +
                '" data-notif="' + notifData + '">' +
                '<div class="notification-item-icon"></div>' +
                '<div class="notification-item-content">' +
                '<h4 class="notification-item-title">' + notif.title + '</h4>' +
                '<p class="notification-item-message">' + notif.message + '</p>' +
                '<p class="notification-item-time" title="' + fullDateTime + '">' + timeAgo + '</p>' +
                '</div>' +
                '<button class="notification-item-close" data-id="' + notif.id + '">×</button>' +
                '</div>'
            );
        }).join('');

        // Wire up click handlers for each item and close button
        Array.prototype.forEach.call(
            document.querySelectorAll('.notification-item'),
            function (item) {
                item.addEventListener('click', function () {
                    try {
                        const raw = item.getAttribute('data-notif');
                        if (!raw) return;
                        const data = JSON.parse(raw);
                        openNotificationModal(data.id, data.title, data.message, data.created_at);
                    } catch (e) {
                        console.error('Error opening notification modal', e);
                    }
                });
            }
        );

        Array.prototype.forEach.call(
            document.querySelectorAll('.notification-item-close'),
            function (btn) {
                btn.addEventListener('click', function (event) {
                    event.stopPropagation();
                    const id = btn.getAttribute('data-id');
                    if (id) deleteNotification(id);
                });
            }
        );
    }

    async function markNotificationAsRead(notificationId) {
        try {
            await fetch('/api/notifications/' + notificationId + '/read', { method: 'POST' });
            fetchNotifications();
        } catch (err) {
            console.error('Error marking notification as read:', err);
        }
    }

    async function markAllNotificationsAsRead() {
        try {
            await fetch('/api/notifications/read-all', { method: 'POST' });
            fetchNotifications();
        } catch (err) {
            console.error('Error marking all notifications as read:', err);
        }
    }

    function openNotificationModal(notificationId, title, message, timestamp) {
        const modalTitle = document.getElementById('modalTitle');
        const modalMessage = document.getElementById('modalMessage');
        const modalTimestamp = document.getElementById('modalTimestamp');
        if (!modalTitle || !modalMessage || !modalTimestamp) return;

        modalTitle.textContent = title;
        modalMessage.textContent = message;
        modalTimestamp.textContent = 'Sent: ' + timestamp;

        modal.classList.add('active');
        markNotificationAsRead(notificationId);
        document.body.style.overflow = 'hidden';
    }

    function closeNotificationModal() {
        modal.classList.remove('active');
        document.body.style.overflow = 'auto';
    }

    async function deleteNotification(notificationId) {
        try {
            await fetch('/api/notifications/' + notificationId + '/delete', { method: 'DELETE' });
            fetchNotifications();
        } catch (err) {
            console.error('Error deleting notification:', err);
        }
    }

    // Close modal when clicking outside the inner content
    document.addEventListener('click', function (e) {
        if (e.target === modal) closeNotificationModal();
    });

    // Close modal with Escape key
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeNotificationModal();
    });

    // If the "Mark all read" button exists, wire it to the helper
    const markAllBtn = document.getElementById('markAllReadBtn');
    if (markAllBtn) {
        markAllBtn.addEventListener('click', function () {
            markAllNotificationsAsRead();
        });
    }

    // Initial fetch + polling
    fetchNotifications();
    setInterval(fetchNotifications, 10000);
});

