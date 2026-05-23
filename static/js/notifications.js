(function () {
    const NotificationCenter = {
        root: null,
        countBadge: null,
        listContainer: null,
        emptyState: null,
        markAllBtn: null,
        toggle: null,
        modal: null,
        modalInstance: null,
        modalTitleEl: null,
        modalMessageEl: null,
        modalTimeEl: null,
        modalReferenceEl: null,
        isLoading: false,
        hasLoaded: false,

        init() {
            this.root = document.querySelector('[data-notification-root]');
            if (!this.root || typeof axios === 'undefined') {
                return;
            }

            this.countBadge = this.root.querySelector('[data-notification-count]');
            this.listContainer = this.root.querySelector('[data-notification-list]');
            this.emptyState = this.root.querySelector('[data-notification-empty]');
            this.markAllBtn = this.root.querySelector('[data-notification-markall]');
            this.toggle = this.root.querySelector('[data-notification-toggle]');
            this.modal = document.getElementById('notificationModal');
            if (this.modal && typeof bootstrap !== 'undefined' && bootstrap.Modal) {
                this.modalInstance = bootstrap.Modal.getOrCreateInstance(this.modal);
                this.modalTitleEl = this.modal.querySelector('[data-notification-modal-title]');
                this.modalMessageEl = this.modal.querySelector('[data-notification-modal-message]');
                this.modalTimeEl = this.modal.querySelector('[data-notification-modal-time]');
                this.modalReferenceEl = this.modal.querySelector('[data-notification-modal-reference]');
            }

            if (this.markAllBtn) {
                this.markAllBtn.addEventListener('click', (event) => {
                    event.preventDefault();
                    this.markAllRead();
                });
            }

            if (this.toggle) {
                this.toggle.addEventListener('click', () => {
                    if (!this.hasLoaded) {
                        this.loadNotifications();
                    }
                });

                this.toggle.addEventListener('shown.bs.dropdown', () => {
                    if (!this.hasLoaded || this.shouldRefresh) {
                        this.loadNotifications();
                    }
                });
            }

            this.listContainer?.addEventListener('click', (event) => {
                const button = event.target.closest('[data-notification-read]');
                if (button) {
                    const id = button.getAttribute('data-notification-read');
                    if (id) {
                        event.preventDefault();
                        this.markSingleRead(id);
                    }
                    return;
                }

                const openTarget = event.target.closest('[data-notification-open]');
                if (openTarget) {
                    event.preventDefault();
                    this.openModal(openTarget);
                }
            });

            this.listContainer?.addEventListener('keydown', (event) => {
                if (event.key !== 'Enter' && event.key !== ' ') {
                    return;
                }
                const openTarget = event.target.closest('[data-notification-open]');
                if (openTarget) {
                    event.preventDefault();
                    this.openModal(openTarget);
                }
            });

            // Initial fetch for badges even if dropdown isn't opened yet
            this.loadNotifications();
        },

        async loadNotifications() {
            if (this.isLoading) {
                return;
            }
            this.isLoading = true;
            this.setEmptyState('Loading notifications…');

            try {
                const response = await axios.get('/notifications');
                const payload = response?.data?.data || { items: [], unread_count: 0 };
                this.renderNotifications(payload.items || []);
                this.updateBadge(payload.unread_count || 0);
                this.hasLoaded = true;
                this.shouldRefresh = false;
            } catch (error) {
                console.error('Unable to load notifications', error);
                this.setEmptyState('Unable to load notifications right now.');
            } finally {
                this.isLoading = false;
            }
        },

        renderNotifications(items) {
            if (!this.listContainer) {
                return;
            }

            this.listContainer.innerHTML = '';

            if (!items.length) {
                this.setEmptyState('No new notifications');
                return;
            }

            this.setEmptyState('');

            const fragment = document.createDocumentFragment();
            items.forEach((item) => {
                const li = document.createElement('li');
                li.className = 'dropdown-item px-3 py-2 notification-item';
                li.dataset.notificationOpen = 'true';
                li.dataset.notificationTitle = item.title || 'Notification';
                li.dataset.notificationMessage = item.message || '';
                li.dataset.notificationTime = item.created_at_display || '';
                li.dataset.notificationId = item.notification_id || '';
                if (item.reference) {
                    li.dataset.notificationReference = item.reference;
                } else {
                    delete li.dataset.notificationReference;
                }
                li.dataset.notificationUnread = (!item.is_read).toString();
                li.setAttribute('role', 'button');
                li.setAttribute('tabindex', '0');

                const isUnread = !item.is_read;
                const reference = item.reference ? `<span class="badge bg-light text-primary ms-2">${escapeHtml(item.reference)}</span>` : '';
                const title = escapeHtml(item.title || 'Notification');
                const timestamp = escapeHtml(item.created_at_display || '');
                const message = escapeHtml(item.message || '');
                const unreadClass = isUnread ? 'notification-unread' : '';

                li.innerHTML = `
                    <div class="notification-item-body d-flex flex-column gap-1 ${unreadClass}">
                        <div class="d-flex justify-content-between align-items-start gap-2">
                            <div class="flex-grow-1">
                                <div>${title}${reference}</div>
                                <small class="text-muted">${timestamp}</small>
                            </div>
                            ${isUnread ? `<button class="btn btn-link btn-sm p-0" data-notification-read="${item.notification_id}">Mark read</button>` : ''}
                        </div>
                        <div class="small text-body text-truncate-3">${message}</div>
                    </div>
                `;

                fragment.appendChild(li);
            });

            this.listContainer.appendChild(fragment);
        },

        async markSingleRead(notificationId) {
            try {
                await axios.post(`/notifications/read/${notificationId}`);
                this.shouldRefresh = true;
                this.loadNotifications();
            } catch (error) {
                console.error('Unable to mark notification as read', error);
            }
        },

        async markAllRead() {
            if (!this.markAllBtn) {
                return;
            }
            this.markAllBtn.disabled = true;
            try {
                await axios.post('/notifications/read/all');
                this.shouldRefresh = true;
                this.loadNotifications();
            } catch (error) {
                console.error('Unable to mark notifications as read', error);
            } finally {
                this.markAllBtn.disabled = false;
            }
        },

        updateBadge(unreadCount) {
            if (!this.countBadge) {
                return;
            }
            if (unreadCount > 0) {
                this.countBadge.textContent = unreadCount > 9 ? '9+' : unreadCount;
                this.countBadge.classList.remove('d-none');
            } else {
                this.countBadge.classList.add('d-none');
            }
        },

        setEmptyState(text) {
            if (!this.emptyState) {
                return;
            }
            if (!text) {
                this.emptyState.classList.add('d-none');
                this.emptyState.textContent = '';
                return;
            }
            this.emptyState.classList.remove('d-none');
            this.emptyState.textContent = text;
        },

        openModal(targetEl) {
            const dataset = targetEl?.dataset || {};
            if (!this.modalInstance) {
                return;
            }

            const title = dataset.notificationTitle || 'Notification';
            const message = dataset.notificationMessage || '';
            const time = dataset.notificationTime || '';
            const reference = dataset.notificationReference || '';
            const notificationId = dataset.notificationId;
            const wasUnread = dataset.notificationUnread === 'true';

            if (this.modalTitleEl) {
                this.modalTitleEl.textContent = title;
            }
            if (this.modalMessageEl) {
                this.modalMessageEl.textContent = message;
            }
            if (this.modalTimeEl) {
                this.modalTimeEl.textContent = time;
            }
            if (this.modalReferenceEl) {
                if (reference) {
                    this.modalReferenceEl.textContent = `Reference: ${reference}`;
                    this.modalReferenceEl.classList.remove('d-none');
                } else {
                    this.modalReferenceEl.classList.add('d-none');
                    this.modalReferenceEl.textContent = '';
                }
            }

            if (notificationId && wasUnread) {
                dataset.notificationUnread = 'false';
                targetEl.querySelector('.notification-item-body')?.classList.remove('notification-unread');
                const readBtn = targetEl.querySelector('[data-notification-read]');
                if (readBtn) {
                    readBtn.remove();
                }
                this.markSingleRead(notificationId);
            }

            this.modalInstance.show();
        }
    };

    function escapeHtml(str) {
        if (!str) return '';
        return str
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    document.addEventListener('DOMContentLoaded', () => NotificationCenter.init());
    document.addEventListener('zyntra:live-update', (event) => {
        const changedTokens = event?.detail?.changedTokens || {};
        if (!changedTokens.notifications) {
            return;
        }

        if (NotificationCenter.root) {
            NotificationCenter.shouldRefresh = true;
            NotificationCenter.loadNotifications();
        }
    });
})();
