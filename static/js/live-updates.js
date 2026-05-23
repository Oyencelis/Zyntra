(function (window, document) {
  const LiveUpdates = {
    started: false,
    timerId: null,
    inFlight: false,
    intervalMs: 15000,
    initialized: false,
    previousTokens: {},
    reloadTimerId: null,

    start() {
      if (this.started || typeof axios === 'undefined') {
        return;
      }

      const isAuthenticated = document.querySelector('meta[name="user-authenticated"]')?.getAttribute('content') === 'true'
        || !!document.querySelector('#layout-menu')
        || !!document.querySelector('[data-cart-count]')
        || !!document.querySelector('[data-notification-root]');

      if (!isAuthenticated) {
        return;
      }

      this.started = true;
      this.fetchState();
      this.timerId = window.setInterval(() => this.fetchState(), this.intervalMs);
    },

    forceRefresh() {
      this.fetchState();
    },

    async fetchState() {
      if (this.inFlight) {
        return;
      }

      this.inFlight = true;
      try {
        const response = await axios.get('/api/live/state');
        const payload = response?.data?.data || {};

        if (payload.poll_interval_ms) {
          const nextInterval = parseInt(payload.poll_interval_ms, 10) || 15000;
          if (nextInterval > 0 && nextInterval !== this.intervalMs) {
            this.intervalMs = nextInterval;
            if (this.timerId) {
              window.clearInterval(this.timerId);
              this.timerId = window.setInterval(() => this.fetchState(), this.intervalMs);
            }
          }
        }

        this.applyCounts(payload.counts || {});
        this.processTokens(payload);
      } catch (error) {
        if (error?.response?.status === 401 && this.timerId) {
          window.clearInterval(this.timerId);
          this.timerId = null;
        }
      } finally {
        this.inFlight = false;
      }
    },

    processTokens(payload) {
      const nextTokens = payload?.tokens || {};
      const changedTokens = {};

      Object.keys(nextTokens).forEach((key) => {
        const current = nextTokens[key] || '';
        const previous = this.previousTokens[key] || '';
        if (this.initialized && current && current !== previous) {
          changedTokens[key] = { previous, current };
        }
      });

      this.previousTokens = nextTokens;

      if (!this.initialized) {
        this.initialized = true;
        return;
      }

      if (!Object.keys(changedTokens).length) {
        return;
      }

      const detail = { payload, changedTokens };
      document.dispatchEvent(new CustomEvent('zyntra:live-update', { detail }));
      this.handlePageChanges(detail);
    },

    applyCounts(counts) {
      this.updateBadge('[data-cart-count]', counts.cart_count, 99);
      this.updateBadge('[data-wishlist-count]', counts.wishlist_count, 99);
      this.updateBadge('[data-notification-count]', counts.notifications_unread_count, 9, true);
      this.updateBadge('[data-messages-count]', counts.messages_unread_count, 99, true);
    },

    updateBadge(selector, rawCount, maxCount, hideWhenZero) {
      const count = parseInt(rawCount, 10) || 0;
      document.querySelectorAll(selector).forEach((badge) => {
        badge.textContent = count > 0 ? (count > maxCount ? `${maxCount}+` : `${count}`) : '';
        if (hideWhenZero) {
          badge.classList.toggle('d-none', count === 0);
        }
      });
    },

    getInterestedTokens() {
      const path = (window.location.pathname || '').toLowerCase();
      if (path === '/cart') {
        return ['cart'];
      }
      if (path === '/wishlist') {
        return ['wishlist'];
      }
      if (path === '/messages') {
        return ['messages'];
      }
      if (path === '/order-list' || path === '/order-management') {
        return ['seller_orders', 'messages', 'notifications'];
      }
      if (path === '/rider') {
        return ['rider_pickups', 'messages', 'notifications'];
      }
      if (path.startsWith('/order-tracking')) {
        return ['buyer_orders', 'messages', 'notifications'];
      }
      return [];
    },

    handlePageChanges(detail) {
      const changedTokens = detail?.changedTokens || {};
      const interestedTokens = this.getInterestedTokens();
      const hasRelevantChange = interestedTokens.some((key) => changedTokens[key]);

      if (!hasRelevantChange) {
        return;
      }

      const path = (window.location.pathname || '').toLowerCase();

      if (path === '/messages') {
        return;
      }

      if (path === '/rider' && window.RiderPickups && typeof window.RiderPickups.refreshLists === 'function') {
        window.RiderPickups.refreshLists();
        return;
      }

      if (document.activeElement && ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
        return;
      }

      if (this.reloadTimerId) {
        window.clearTimeout(this.reloadTimerId);
      }

      this.reloadTimerId = window.setTimeout(() => {
        window.location.reload();
      }, 800);
    }
  };

  window.ZyntraLiveUpdates = LiveUpdates;
  document.addEventListener('DOMContentLoaded', function () {
    LiveUpdates.start();
  });
})(window, document);
