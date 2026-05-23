/**
 *  Web Service
 */
// const axios = require('axios');
// const jQuery = $;

$ = (typeof $ !== 'undefined') ? $ : {};
$.SystemScript = (typeof $.SystemScript !== 'undefined') ? $.SystemScript : {};

$.SystemScript = (function() {
	let __executeGet = function (path) {

        let dfd = $.Deferred();

        axios.get(path)
          .then(function (response) {
            dfd.resolve(response);
          })
          .catch(function (error) {
            dfd.resolve({
                status : 'ERROR',
                message : error
            });

          })
        return dfd.promise();
    };

    let __executePost = function(path, jsonObj) {
        path = path;
        let d = $.Deferred();

        axios.post(path, jsonObj)
        .then(function (response) {
            d.resolve(response)
        })
        .catch(function (error) {
            d.resolve({
                status : 'ERROR',
                message : error
            });
            // console.log('ee')

        });

        return d.promise();
    };


    let __formValidation = function() {

        // Example starter JavaScript for disabling form submissions if there are invalid fields
        (function () {
        'use strict'

        window.addEventListener('load', function () {
            // Fetch all the forms we want to apply custom Bootstrap validation styles to
            var forms = document.getElementsByClassName('needs-validation')

            // Loop over them and prevent submission
            Array.prototype.filter.call(forms, function (form) {
                form.addEventListener('submit', function (event) {
                    if (form.checkValidity() === false) {
                        event.preventDefault()
                        event.stopPropagation()
                    }
                    form.classList.add('was-validated')
                }, false)
            })
        }, false)
        }())
    }

        //action (String)
    let __getSwalInstance = function() {
        if (typeof Swal !== 'undefined') {
            return Swal;
        }
        if (typeof swal !== 'undefined') {
            return swal;
        }
        console.warn('SweetAlert library is not loaded.');
        return null;
    };

    let __swalAlertMessage = function (head, mes, action) {
        let d = $.Deferred();
        let swalInstance = __getSwalInstance();

        if (!swalInstance) {
            alert(`${head}\n${mes}`);
            d.resolve(true);
            return d.promise();
        }

        if (typeof swalInstance.fire === 'function') {
            swalInstance.fire({
                title: head,
                text: mes,
                icon: action || 'info',
                confirmButtonText: 'OK'
            }).then(() => d.resolve(true));
        } else {
            swalInstance(head, mes, action);
            d.resolve(true);
        }

        return d.promise();
    }

    let __swalConfirmMessage = function(head, mes, action) {
        let d = $.Deferred();
        let swalInstance = __getSwalInstance();

        if (!swalInstance) {
            let response = confirm(mes);
            d.resolve(response);
            return d.promise();
        }

        if (typeof swalInstance.fire === 'function') {
            swalInstance.fire({
                title: head,
                text: mes,
                icon: action || 'question',
                showCancelButton: true,
                confirmButtonText: 'Yes',
                cancelButtonText: 'No'
            }).then((result) => {
                d.resolve(!!result.isConfirmed);
            });
        } else {
            swalInstance({
                title: head,
                text: mes,
                type: action,
                confirmButtonText: 'Yes',
                showCancelButton: true
            }).then((result) => {
                d.resolve(!!result.value);
            });
        }

        return d.promise();
    }

    let __dateTimeFormat = function(date_to_format) {
         // Debugging: Log the input date string
         console.log('Original date string:', date_to_format);
            
         // Ensure the input is in the format YYYY-MM-DD HH:MM:SS
         const [datePart, timePart] = date_to_format.split(" ");
         const isoDateString = `${datePart}T${timePart}`; // Convert to ISO format

         // Create a new Date object
         let dateTime = new Date(isoDateString); 

         // Debugging: Log the created date object
         console.log('Created date object:', dateTime);

         // Check if dateTime is valid
         if (isNaN(dateTime.getTime())) {
             return 'Invalid Date';
         }

         // Define month names
         const months = [
             "January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"
         ];

         // Get components of the date
         const month = months[dateTime.getMonth()]; // Month name
         const day = dateTime.getDate(); // Day of the month
         const year = dateTime.getFullYear(); // Full year
         let hours = dateTime.getHours(); // Hours
         const minutes = dateTime.getMinutes(); // Minutes

         // Determine AM/PM suffix
         const ampm = hours >= 12 ? 'PM' : 'AM';
         hours = hours % 12; // Convert to 12-hour format
         hours = hours ? hours : 12; // The hour '0' should be '12'

         // Format the final string
         const formattedDate = `${month} ${day}, ${year} at ${hours}:${minutes < 10 ? '0' : ''}${minutes}${ampm}`;
         return formattedDate;
    }

    let __getDefaultOrder = function(element_id_class, column_name, order) {
        // Assuming 'Date Created' is the desired default ordering column
        let orderColumn = column_name; // Change this to whatever field you want to sort by
        let columnIndex = -1;

        // Find the index of the column with the data-order attribute matching 'orderColumn'
        $(`${element_id_class} thead th`).each(function(index) {
            if ($(this).data('order') === orderColumn) {
                columnIndex = index;
            }
        });

        // Return the order array
        return columnIndex !== -1 ? [[columnIndex, order]] : []; // Default to empty if not found
    }

    let __showToastMessage = function(type, message) {
        if (window.ZynToast) {
            window.ZynToast(type, message);
            return;
        }

        let swalInstance = __getSwalInstance();
        if (swalInstance && typeof swalInstance.fire === 'function') {
            swalInstance.fire({
                toast: true,
                position: 'top-end',
                icon: type === 'error' ? 'error' : 'success',
                title: message,
                timer: 2200,
                showConfirmButton: false
            });
            return;
        }

        alert(message);
    }

    let __updateNavbarCounts = function(data) {
        if (!data) return;

        let cartBadge = document.querySelector('.zyn-cart-btn[title="Cart"] .zyn-cart-badge');
        if (cartBadge) {
            let cartCount = parseInt(data.cart_count, 10) || 0;
            cartBadge.textContent = cartCount > 0 ? cartCount : '';
            cartBadge.classList.toggle('d-none', cartCount === 0);
        }

        let wishlistBadge = document.querySelector('[data-wishlist-count]');
        if (wishlistBadge) {
            let wishlistCount = parseInt(data.wishlist_count, 10) || 0;
            wishlistBadge.textContent = wishlistCount > 0 ? wishlistCount : '';
            wishlistBadge.classList.toggle('d-none', wishlistCount === 0);
        }

        let dashboardMessageBadges = document.querySelectorAll('#layout-menu a[href="/messages"] .badge');
        dashboardMessageBadges.forEach(function(badge) {
            let unreadCount = parseInt(data.messages_unread_count, 10) || 0;
            if (unreadCount > 0) {
                badge.textContent = unreadCount > 99 ? '99+' : unreadCount;
                badge.classList.remove('d-none');
            } else {
                badge.classList.add('d-none');
                badge.textContent = '';
            }
        });
    }

    let __dispatchLiveUpdate = function(detail) {
        document.dispatchEvent(new CustomEvent('zyntra:live-update', {
            detail: detail || {}
        }));
    }

    let __createLiveUpdatesManager = function() {
        let state = {
            started: false,
            timerId: null,
            inFlight: false,
            intervalMs: 15000,
            previousTokens: {},
            authenticated: false,
        };

        let notifyChanges = function(payload) {
            let nextTokens = (payload && payload.tokens) ? payload.tokens : {};
            let changedTokens = {};

            Object.keys(nextTokens).forEach(function(key) {
                let nextValue = nextTokens[key] || '';
                let prevValue = state.previousTokens[key] || '';
                if (nextValue && nextValue !== prevValue) {
                    changedTokens[key] = {
                        previous: prevValue,
                        current: nextValue,
                    };
                }
            });

            state.previousTokens = nextTokens;

            if (Object.keys(changedTokens).length) {
                __dispatchLiveUpdate({
                    payload: payload,
                    changedTokens: changedTokens,
                });
            }
        }

        let fetchState = function() {
            if (state.inFlight) {
                return;
            }

            state.inFlight = true;
            axios.get('/api/live/state')
                .then(function(response) {
                    let payload = (response && response.data && response.data.data) ? response.data.data : {};
                    state.authenticated = !!payload.authenticated;

                    if (payload && payload.poll_interval_ms) {
                        let nextInterval = parseInt(payload.poll_interval_ms, 10) || 15000;
                        if (nextInterval > 0 && nextInterval !== state.intervalMs) {
                            state.intervalMs = nextInterval;
                            if (state.timerId) {
                                clearInterval(state.timerId);
                                state.timerId = setInterval(fetchState, state.intervalMs);
                            }
                        }
                    }

                    if (payload && payload.counts) {
                        __updateNavbarCounts(payload.counts);
                    }

                    notifyChanges(payload);
                })
                .catch(function(error) {
                    if (error && error.response && error.response.status === 401) {
                        state.authenticated = false;
                        if (state.timerId) {
                            clearInterval(state.timerId);
                            state.timerId = null;
                        }
                    }
                })
                .finally(function() {
                    state.inFlight = false;
                });
        }

        let start = function() {
            if (state.started || typeof axios === 'undefined') {
                return;
            }

            let userAuthenticated = document.querySelector('meta[name="user-authenticated"]')?.getAttribute('content') === 'true'
                || !!document.querySelector('[data-notification-root]')
                || !!document.querySelector('[data-cart-count]')
                || !!document.querySelector('#layout-menu');

            if (!userAuthenticated) {
                return;
            }

            state.started = true;
            fetchState();
            state.timerId = setInterval(fetchState, state.intervalMs);
        }

        let forceRefresh = function() {
            fetchState();
        }

        return {
            start: start,
            forceRefresh: forceRefresh,
        }
    }

    let __liveUpdates = __createLiveUpdatesManager();

    let __bindGlobalAjaxForms = function() {
        document.addEventListener('submit', function(event) {
            let form = event.target;
            if (!(form instanceof HTMLFormElement)) {
                return;
            }

            if (form.id === 'loginForm') {
                event.preventDefault();
                event.stopImmediatePropagation();

                let data = new FormData(form);
                axios.post('/login', data)
                    .then(function(response) {
                        let payload = response.data || {};
                        let details = payload.data || {};
                        let passwordField = form.querySelector('#password') || document.getElementById('password');

                        switch (payload.status) {
                            case 'success':
                                let role = details.role_id;
                                if (role == 1 || role == 3 || role == 4) {
                                    window.location.href = '/dashboard';
                                } else {
                                    window.location.href = '/';
                                }
                                break;
                            case 'pending':
                                __swalAlertMessage('Application Under Review', payload.message || 'Your application is currently under review.', 'info');
                                if (passwordField) passwordField.value = '';
                                break;
                            case 'rejected':
                                __swalAlertMessage('Application Rejected', payload.message || 'Your application was not approved.', 'warning');
                                if (passwordField) passwordField.value = '';
                                break;
                            default:
                                __swalAlertMessage('Login Failed', payload.message || 'An error occurred during login', 'error');
                                if (passwordField) passwordField.value = '';
                                break;
                        }
                    })
                    .catch(function() {
                        __swalAlertMessage('Error', 'An error occurred while processing your request. Please try again.', 'error');
                    });

                return;
            }

            let action = form.getAttribute('action') || '';
            if (action === '/add-to-cart') {
                event.preventDefault();
                event.stopImmediatePropagation();

                if (typeof window.setCartQuantity === 'function') {
                    window.setCartQuantity();
                }

                let data = new FormData(form);
                axios.post('/add-to-cart', data)
                    .then(function(response) {
                        let payload = response.data || {};
                        if (payload.status === 'success') {
                            __updateNavbarCounts(payload.data);
                            __showToastMessage('success', payload.message || 'Added to cart.');
                        } else {
                            __showToastMessage('error', payload.message || 'Unable to add to cart.');
                        }
                    })
                    .catch(function(error) {
                        let message = 'Something went wrong.';
                        if (error && error.response && error.response.data && error.response.data.message) {
                            message = error.response.data.message;
                        }
                        __showToastMessage('error', message);
                    });
            }
        }, true);
    }

    __bindGlobalAjaxForms();

    return {
        executePost : __executePost,
        executeGet : __executeGet,
        formValidation: __formValidation,
        swalAlertMessage: __swalAlertMessage,
        swalConfirmMessage: __swalConfirmMessage,
        dateTimeFormat: __dateTimeFormat,
        getDefaultOrder: __getDefaultOrder,
    };
}());