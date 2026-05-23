(function (window, document) {
  class ChatWidget {
    constructor(options) {
      this.root = options.root;
      this.roleId = options.roleId;
      this.userId = options.userId;
      this.counterpartLabel = options.counterpartLabel || 'User';
      this.options = Object.assign(
        {
          counterpartListEnabled: true,
          fixedCounterpartId: null,
          fixedCounterpartName: null,
          conversationFilter: null,
          autoRefreshIntervalMs: 5000,
          autoOpenFirstConversation: false,
        },
        options || {}
      );
      this.initialized = false;
      this.autoRefreshTimerId = null;
      this.visibilityHandler = null;
      this.liveUpdateHandler = null;
      this.state = {
        conversations: [],
        counterparts: [],
        activeConversationId: null,
        messages: [],
        loadingMessages: false,
        sending: false,
        refreshingLive: false,
      };

      this.elements = {
        conversationList: this.root.querySelector('[data-chat="conversation-list"]'),
        counterpartList: this.root.querySelector('[data-chat="counterpart-list"]'),
        messagesContainer: this.root.querySelector('[data-chat="messages"]'),
        messageForm: this.root.querySelector('[data-chat="message-form"]'),
        messageInput: this.root.querySelector('[data-chat="message-input"]'),
        status: this.root.querySelector('[data-chat="status"]'),
        counterpartEmpty: this.root.querySelector('[data-chat="counterpart-empty"]'),
      };
    }

    init() {
      if (this.initialized) {
        return;
      }

      this.initialized = true;
      this.bindEvents();
      this.refreshData();
      this.liveUpdateHandler = (event) => {
        const changedTokens = event?.detail?.changedTokens || {};
        if (!changedTokens.messages) {
          return;
        }

        this.liveRefresh();
      };
      document.addEventListener('zyntra:live-update', this.liveUpdateHandler);
      this.startAutoRefresh();
    }

    bindEvents() {
      if (this.elements.messageForm) {
        this.elements.messageForm.addEventListener('submit', (e) => {
          e.preventDefault();
          this.submitMessage();
        });
      }
    }

    async refreshData() {
      await this.fetchConversations();
      this.autoOpenConversationIfNeeded();
      await this.fetchCounterparts();
    }

    async fetchConversations() {
      try {
        const res = await fetch('/api/chat/conversations');
        const data = await res.json();
        if (data.status === 'success') {
          let list = data.data || [];
          if (typeof this.options.conversationFilter === 'function') {
            list = list.filter(this.options.conversationFilter);
          }
          this.state.conversations = list;
          if (this.state.activeConversationId && !list.some((item) => item.conversation_id === this.state.activeConversationId)) {
            this.state.activeConversationId = null;
            this.state.messages = [];
          }
          this.renderConversations();
        } else {
          this.setStatus(data.message || 'Unable to load conversations');
        }
      } catch (error) {
        console.error(error);
        this.setStatus('Network error while loading conversations');
      }
    }

    autoOpenConversationIfNeeded() {
      const preferredConversationId = this.getPreferredConversationId();
      if (preferredConversationId && preferredConversationId !== this.state.activeConversationId) {
        this.openConversation(preferredConversationId);
      }
    }

    getPreferredConversationId() {
      const list = this.state.conversations || [];
      if (!list.length) {
        return null;
      }

      if (this.state.activeConversationId && list.some((item) => item.conversation_id === this.state.activeConversationId)) {
        return this.state.activeConversationId;
      }

      if (this.options.fixedCounterpartId) {
        return list[0].conversation_id;
      }

      if (this.options.autoOpenFirstConversation) {
        return list[0].conversation_id;
      }

      return null;
    }

    async fetchCounterparts() {
      if (!this.elements.counterpartList || this.options.fixedCounterpartId || this.options.counterpartListEnabled === false) {
        if (this.options.fixedCounterpartId) {
          this.state.counterparts = [
            {
              user_id: this.options.fixedCounterpartId,
              firstname: this.options.fixedCounterpartName || this.counterpartLabel,
            },
          ];
        }
        this.renderCounterparts();
        return;
      }

      try {
        const res = await fetch('/api/chat/counterparts');
        const data = await res.json();
        if (data.status === 'success') {
          this.state.counterparts = data.data || [];
          this.renderCounterparts();
        } else {
          this.setStatus(data.message || 'Unable to load users');
        }
      } catch (error) {
        console.error(error);
        this.setStatus('Network error while loading users');
      }
    }

    renderConversations() {
      if (!this.elements.conversationList) return;
      const list = this.state.conversations;
      if (!list.length) {
        this.elements.conversationList.innerHTML = '<p class="text-muted small mb-0">No conversations yet.</p>';
        return;
      }

      this.elements.conversationList.innerHTML = list
        .map((item) => {
          const counterpart = item.counterpart || {};
          const isActive = item.conversation_id === this.state.activeConversationId;
          return `
            <button type="button" class="list-group-item list-group-item-action ${isActive ? 'active' : ''}" data-conversation-id="${item.conversation_id}">
              <div class="d-flex justify-content-between align-items-center">
                <div>
                  <div class="fw-semibold">${this.escapeHtml(this.buildCounterpartName(counterpart))}</div>
                  <small class="text-muted">${this.escapeHtml(item.last_message || 'No messages yet')}</small>
                </div>
                <small class="text-muted">${item.last_message_at ? this.formatTimestamp(item.last_message_at) : ''}</small>
              </div>
            </button>
          `;
        })
        .join('');

      this.elements.conversationList.querySelectorAll('[data-conversation-id]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const conversationId = parseInt(btn.dataset.conversationId, 10);
          this.openConversation(conversationId);
        });
      });
    }

    renderCounterparts() {
      if (!this.elements.counterpartList || this.options.counterpartListEnabled === false) return;
      const list = this.state.counterparts;
      if (!list.length) {
        this.elements.counterpartList.innerHTML = '';
        if (this.elements.counterpartEmpty) {
          this.elements.counterpartEmpty.classList.remove('d-none');
        }
        return;
      }

      if (this.elements.counterpartEmpty) {
        this.elements.counterpartEmpty.classList.add('d-none');
      }

      this.elements.counterpartList.innerHTML = list
        .map((user) => {
          return `
            <button type="button" class="list-group-item list-group-item-action" data-counterpart-id="${user.user_id}">
              <div class="d-flex flex-column">
                <span class="fw-semibold">${this.escapeHtml(this.buildCounterpartName(user))}</span>
                ${user.store_name ? `<small class="text-muted">${this.escapeHtml(user.store_name)}</small>` : ''}
              </div>
            </button>
          `;
        })
        .join('');

      this.elements.counterpartList.querySelectorAll('[data-counterpart-id]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const counterpartId = parseInt(btn.dataset.counterpartId, 10);
          this.startConversationWith(counterpartId);
        });
      });
    }

    buildCounterpartName(user) {
      const parts = [user.firstname, user.lastname].filter(Boolean);
      if (parts.length) {
        return parts.join(' ');
      }
      return user.email || this.counterpartLabel;
    }

    async startConversationWith(counterpartId) {
      if (this.options.fixedCounterpartId && counterpartId !== this.options.fixedCounterpartId) {
        counterpartId = this.options.fixedCounterpartId;
      }

      const payload = new URLSearchParams();
      if (this.roleId === 2) {
        payload.append('buyer_id', this.userId);
        payload.append('seller_id', counterpartId);
      } else if (this.roleId === 3) {
        payload.append('seller_id', this.userId);
        payload.append('buyer_id', counterpartId);
      } else {
        return;
      }

      try {
        const res = await fetch('/api/chat/conversations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: payload,
        });
        const data = await res.json();
        if (data.status === 'success') {
          const conversationId = data.data.conversation_id;
          await this.fetchConversations();
          await this.openConversation(conversationId);
          return conversationId;
        } else {
          this.setStatus(data.message || 'Unable to start conversation');
        }
      } catch (error) {
        console.error(error);
        this.setStatus('Network error while starting conversation');
      }

      return null;
    }

    async openConversation(conversationId) {
      this.state.activeConversationId = conversationId;
      this.renderConversations();
      await this.fetchMessages(conversationId);
    }

    async fetchMessages(conversationId, options = {}) {
      if (!conversationId) return;
      const background = options.background === true;
      const stickToBottom = options.stickToBottom === true || (background && this.isNearBottom());
      if (!background) {
        this.state.loadingMessages = true;
        this.renderMessages({ stickToBottom });
      }
      try {
        const res = await fetch(`/api/chat/conversations/${conversationId}/messages`);
        const data = await res.json();
        if (data.status === 'success') {
          this.state.messages = data.data || [];
        } else {
          this.setStatus(data.message || 'Unable to load messages');
        }
      } catch (error) {
        console.error(error);
        this.setStatus('Network error while loading messages');
      } finally {
        if (!background) {
          this.state.loadingMessages = false;
        }
        this.renderMessages({ stickToBottom });
      }
    }

    renderMessages(options = {}) {
      if (!this.elements.messagesContainer) return;
      const stickToBottom = options.stickToBottom === true;
      if (this.state.loadingMessages) {
        this.elements.messagesContainer.innerHTML = '';
        return;
      }

      const list = this.state.messages;
      if (!list.length) {
        this.elements.messagesContainer.innerHTML = '<p class="text-muted small">No messages yet. Start the conversation!</p>';
        return;
      }

      this.elements.messagesContainer.innerHTML = list
        .map((msg) => {
          const isMine = msg.sender_id === this.userId;
          return `
            <div class="mb-3 d-flex ${isMine ? 'justify-content-end' : 'justify-content-start'}">
              <div class="chat-bubble ${isMine ? 'chat-bubble-own' : ''}">
                <div class="small text-muted mb-1">${isMine ? 'You' : this.escapeHtml(msg.firstname || '')}</div>
                <div>${this.escapeHtml(msg.message_text)}</div>
                <small class="text-muted d-block mt-1">${this.formatTimestamp(msg.created_at)}</small>
              </div>
            </div>
          `;
        })
        .join('');

      if (stickToBottom) {
        this.elements.messagesContainer.scrollTop = this.elements.messagesContainer.scrollHeight;
      }
    }

    isNearBottom() {
      if (!this.elements.messagesContainer) {
        return true;
      }

      const container = this.elements.messagesContainer;
      const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      return distanceFromBottom <= 72;
    }

    async submitMessage() {
      if (!this.state.activeConversationId || this.state.sending) return;
      const text = (this.elements.messageInput?.value || '').trim();
      if (!text) return;

      this.state.sending = true;
      try {
        const res = await fetch(`/api/chat/conversations/${this.state.activeConversationId}/messages`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message_text: text }),
        });
        const data = await res.json();
        if (data.status === 'success') {
          this.elements.messageInput.value = '';
          const newMessage = data.data || null;
          if (newMessage && newMessage.message_id) {
            const exists = this.state.messages.some((msg) => msg.message_id === newMessage.message_id);
            if (!exists) {
              this.state.messages = [...this.state.messages, newMessage];
            }
            this.renderMessages({ stickToBottom: true });
          } else {
            await this.fetchMessages(this.state.activeConversationId, { background: true, stickToBottom: true });
          }
          await this.fetchConversations();
          await this.fetchMessages(this.state.activeConversationId, { background: true, stickToBottom: true });
        } else {
          this.setStatus(data.message || 'Unable to send message');
        }
      } catch (error) {
        console.error(error);
        this.setStatus('Network error while sending message');
      } finally {
        this.state.sending = false;
      }
    }

    async liveRefresh() {
      if (this.state.refreshingLive) {
        return;
      }

      this.state.refreshingLive = true;
      try {
        await this.fetchConversations();
        this.autoOpenConversationIfNeeded();
        if (this.state.activeConversationId) {
          await this.fetchMessages(this.state.activeConversationId, { background: true });
        }
      } finally {
        this.state.refreshingLive = false;
      }
    }

    startAutoRefresh() {
      if (this.autoRefreshTimerId || !this.options.autoRefreshIntervalMs) {
        return;
      }

      this.autoRefreshTimerId = window.setInterval(() => {
        if (!this.shouldAutoRefresh()) {
          return;
        }

        this.liveRefresh();
      }, this.options.autoRefreshIntervalMs);

      this.visibilityHandler = () => {
        if (document.visibilityState === 'visible' && this.shouldAutoRefresh()) {
          this.liveRefresh();
        }
      };
      document.addEventListener('visibilitychange', this.visibilityHandler);
    }

    shouldAutoRefresh() {
      if (document.visibilityState === 'hidden') {
        return false;
      }

      if (this.state.sending || this.state.loadingMessages) {
        return false;
      }

      if (
        this.elements.messageInput
        && document.activeElement === this.elements.messageInput
        && (this.elements.messageInput.value || '').trim()
      ) {
        return false;
      }

      const modal = this.root.closest('.modal');
      if (modal) {
        return modal.classList.contains('show');
      }

      return !!(this.root.offsetParent || this.root.getClientRects().length);
    }

    setStatus(message) {
      if (this.elements.status && message) {
        this.elements.status.textContent = message;
        this.elements.status.classList.remove('d-none');
        setTimeout(() => {
          this.elements.status.classList.add('d-none');
        }, 4000);
      }
    }

    escapeHtml(value) {
      if (typeof value !== 'string') return value || '';
      return value
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    formatTimestamp(value) {
      if (!value) return '';
      const date = new Date(value);
      return date.toLocaleString();
    }
  }

  window.ChatWidget = ChatWidget;
})(window, document);
