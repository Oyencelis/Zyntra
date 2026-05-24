from functools import wraps
# pyrefly: ignore [missing-import]
from flask import Flask, session, redirect, url_for, g, render_template, request

# Middleware
from middleware.auth import login_required

# Helpers
from helpers.Session import sessionRemove
from helpers.HelperFunction import responseData

# Controllers
from controller.HomeController import home, loadMoreProducts, categoryPage, getCategoriesInHome, cart, checkout, submitCheckout, shop, orderTracking, orderTrackingLatest, cancelOrder, orderTrackingHub, orderList, orderManagement, updateSuborderStatus, getNotifications, markNotificationRead, markAllNotificationsRead, wishlistPage, confirmOrder, cancelOrderItem, liveState

from controller.LoginController import (
    login,
    LoginSubmit,
    forgotPasswordSubmit,
    signup,
    signupSubmit,
    sellerSignup,
    sellerSignupSubmit,
    deliveryPartnerSignup,
    deliveryPartnerSignupSubmit,
    getDeliveryPartnerDocuments,
    getSellerDocuments,
    verifyEmailPage,
    verifyEmailCode,
    resendEmailCode,
)
from controller.DashboardController import dashboardIndex
from controller.ProductController import productCategories, addCategories, changeCategoryStatus, updateCategories, products, addProduct, changeProductStatus, updateProducts, viewProduct, addToCart, removeFromCart, updateCart, details, checkout, detailsSubmit, storeProducts, toggleWishlist, wishlistMoveToCart, submitProductReview

from controller.ManageProfileController import sellerRequestSubmit, sellerRequest, manageProfile, profileOverview, updateProfileInfo

from controller.UserController import seller, updateSeller, buyer, updateBuyer, rider, updateRider
from controller.RiderController import (
    riderPickupDashboard,
    getRiderPickups,
    claimPickupAssignment,
    updatePickupStatus,
    getPickupDetail,
    uploadDeliveryProof,
)
from controller.PaymentController import paymentDashboard

from controller.ChatController import (
    ensureConversation,
    getConversationMessages,
    postConversationMessage,
    getUserConversations,
    getChatCounterparts,
)

from controller.WalletController import (
    admin_withdrawals_page,
    admin_withdrawal_decide,
    api_wallet_summary,
    api_wallet_withdraw
)

# Seller Management routes
def seller_management_routes(app):
    @app.route('/admin/sellers')
    @login_required
    def all_sellers():
        return render_template('/views/dashboard/admin/all_seller.html', menu='seller-list')

    @app.route('/admin/sellers/pending')
    @login_required
    def pending_sellers():
        return render_template('/views/dashboard/admin/pending_approval.html', menu='seller-pending')

    @app.route('/admin/sellers/approved')
    @login_required
    def approved_sellers():
        return render_template('/views/dashboard/admin/approved_seller.html', menu='seller-approved')

    @app.route('/admin/riders')
    @login_required
    def admin_riders():
        return rider()

    @app.route('/admin/riders/update', methods=['POST'])
    @login_required
    def admin_update_rider():
        return updateRider()

def setup_routes(app: Flask):
    # Initialize seller management routes
    seller_management_routes(app)


    @app.before_request
    def load_user():
        g.authenticated = session.get('authenticated', None)

        if request.endpoint == 'static':
            return
        
        # Load cart items for the current user
        if g.authenticated and g.authenticated.get('user_id'):
            from helpers.QueryHelpers import executeGet
            user_id = g.authenticated['user_id']

            cart_query = """
                SELECT
                    (
                        SELECT COUNT(oi.order_items_id)
                        FROM order_items oi
                        WHERE oi.user_id = %s
                          AND oi.status = 1
                          AND (oi.reference = '' OR oi.reference IS NULL)
                    ) AS item_count,
                    (
                        SELECT COUNT(w.wishlist_id)
                        FROM wishlists w
                        WHERE w.user_id = %s
                    ) AS wishlist_count,
                    (
                        SELECT COUNT(*)
                        FROM conversation_messages cm
                        JOIN conversations c ON cm.conversation_id = c.conversation_id
                        WHERE cm.is_read = 0
                          AND (
                                (c.buyer_id = %s AND cm.sender_id != %s)
                             OR (c.seller_id = %s AND cm.sender_id != %s)
                          )
                    ) AS unread_count,
                    (
                        SELECT COUNT(*)
                        FROM notifications n
                        WHERE n.user_id = %s
                          AND n.is_read = 0
                    ) AS notifications_unread_count
            """
            header_counts = executeGet(cart_query, (user_id, user_id, user_id, user_id, user_id, user_id, user_id))
            header_count = header_counts[0] if header_counts else {}
            g.cart_item_count = header_count.get('item_count', 0) or 0
            g.wishlist_count = header_count.get('wishlist_count', 0) or 0
            g.messages_unread_count = header_count.get('unread_count', 0) or 0
            g.notifications_unread_count = header_count.get('notifications_unread_count', 0) or 0
        else:
            g.cart_item_count = 0
            g.wishlist_count = 0
            g.messages_unread_count = 0
            g.notifications_unread_count = 0


    #HomeController
    @app.route('/')
    def home_page():
        return home() 
    
    @app.route('/about')
    def about_page():
        cart_items = session.get('cart', {})
        categories = getCategoriesInHome("WHERE status = 1")
        return render_template('views/about.html', cat_data=categories, cart_items=cart_items)
        
    @app.route('/shop')
    def shop_page():
        return shop()
    
    #Login Controller
    @app.route('/login')
    def login_page():
        # Check if the user is already logged in
        if g.authenticated and request.args.get('mode') != 'recovery':
            return redirect(url_for('home_page'))  # Redirect to home if logged in
        return login() 
    
    @app.route('/login', methods=['POST'])
    def login_submit():
        return LoginSubmit() 

    @app.route('/forgot-password', methods=['POST'])
    def forgot_password_submit():
        return forgotPasswordSubmit()
    
    #Sign Up Controller
    @app.route('/signup')
    def signup_page():
        # Check if the user is already logged in
        if g.authenticated:
            return redirect(url_for('home_page'))  # Redirect to home if logged in
        return signup()
    
    @app.route('/signup', methods=['POST'])
    def signup_submit():
        return signupSubmit()
    
    @app.route('/verify-email')
    def verify_email_page():
        return verifyEmailPage()

    @app.route('/verify-email-code', methods=['POST'])
    def verify_email_code():
        return verifyEmailCode()

    @app.route('/resend-email-code', methods=['POST'])
    def resend_email_code():
        return resendEmailCode()
    
    # Public Seller Signup (no login required)
    @app.route('/sell')
    def sell_page():
        if g.authenticated:
            return redirect(url_for('home_page'))
        return sellerSignup()
    
    @app.route('/sell', methods=['POST'])
    def seller_signup_submit():
        return sellerSignupSubmit()
    
    @app.route('/seller')
    @login_required
    def seller_dashboard():
        return seller()
    
    @app.route('/buyer')
    @login_required
    def buyer_dashboard():
        return buyer()
    
    @app.route('/details')
    @login_required
    def details_page():
        return details()
    

    @app.route('/logout')
    @login_required 
    def logout():
        sessionRemove('authenticated') # Clear session data
        return redirect(url_for('home_page'))

    @app.route('/dashboard', strict_slashes=False)
    @login_required 
    def dashboard_page():
        return dashboardIndex()
        
    @app.route('/buyer/dashboard')
    @login_required 
    def buyer_dashboard_page():
        # Access firstname from the authenticated user dictionary
        firstname = g.authenticated.get('firstname', 'User')
        return render_template('views/dashboard/buyer/index.html', 
                            user_greeting=f"Hello, {firstname}", 
                            recent_orders=[])
    

    @app.route('/product/categories')
    @login_required 
    def product_categories():
        return productCategories()
    

    @app.route('/add-category', methods=['POST'])
    def add_categories():
        return addCategories()
    
    @app.route('/change-category-status', methods=['GET', 'POST'])
    def change_category_status():
        return changeCategoryStatus()

    @app.route('/update-category', methods=['POST'])
    def update_categories():
        return updateCategories()
    
    @app.route('/product')
    @login_required
    def products_page():
        return products()
    
    @app.route('/add-product', methods=['POST'])
    def add_product():
        return addProduct()
    
    @app.route('/change-product-status', methods=['GET', 'POST'])
    def change_product_status():
        return changeProductStatus()
    
    @app.route('/update-product', methods=['POST'])
    @login_required
    def update_products():
        return updateProducts()
    
    @app.route('/product/view/<int:product_id>')
    def view_product(product_id):
        return viewProduct(product_id)
    
    @app.route('/store/<int:seller_id>')
    def store_products(seller_id):
        return storeProducts(seller_id)
    
    @app.route('/wishlist')
    @login_required
    def wishlist_page():
        return wishlistPage()
    
    @app.route('/profile')
    @login_required
    def profile_page():
        return profileOverview()

    @app.route('/profiles')
    @login_required
    def manage_profile_dashboard():
        return manageProfile()
    
    @app.route('/profile/update', methods=['POST'])
    @login_required
    def profile_update():
        return updateProfileInfo()
    
    @app.route('/update-seller', methods=['GET', 'POST'])
    def update_seller():
        return updateSeller()
    
    @app.route('/update-buyer', methods=['GET', 'POST'])
    def update_buyer():
        return updateBuyer()
    
    @app.route('/update-rider', methods=['GET', 'POST'])
    def update_rider():
        return updateRider()
    
    @app.route('/messages')
    @login_required
    def messages_page():
        return render_template('views/dashboard/messages.html', menu='messages')
        
    @app.route('/payment')
    @login_required
    def payment_page():
        return paymentDashboard()

    @app.route('/rider-earnings')
    @login_required
    def rider_earnings_page():
        return paymentDashboard()

    # Rider routes
    @app.route('/rider')
    @login_required
    def rider_dashboard():
        return riderPickupDashboard()
        
    @app.route('/load_more_products', methods=['GET'])
    def load_more_products():
        return loadMoreProducts()
    
    @app.route('/category/<int:category_id>', methods=['GET', 'POST'])
    def category_page(category_id):
        return categoryPage(category_id)

    # Notification APIs
    @app.route('/notifications', methods=['GET'])
    @login_required
    def notifications_index():
        return getNotifications()

    @app.route('/api/live/state', methods=['GET'])
    @login_required
    def api_live_state():
        return liveState()

    @app.route('/notifications/read/<int:notification_id>', methods=['POST'])
    @login_required
    def notifications_read(notification_id):
        return markNotificationRead(notification_id)

    @app.route('/notifications/read/all', methods=['POST'])
    @login_required
    def notifications_read_all():
        return markAllNotificationsRead()
    

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('views/404.html'), 404
    
    # Deliver with Zyntra (courier/driver signup)
    @app.route('/deliver')
    def deliver_page():
        if g.authenticated:
            return redirect(url_for('home_page'))
        return deliveryPartnerSignup()
    
    @app.route('/deliver', methods=['POST'])
    def delivery_partner_submit():
        return deliveryPartnerSignupSubmit()

    @app.route('/cart')
    def cart_page():
        return cart()

    
    @app.route('/add-to-cart', methods=['POST'])
    def add_to_cart():
        return addToCart()
    
    @app.route('/remove-from-cart', methods=['POST'])
    def remove_from_cart():
        return removeFromCart()
    
    @app.route('/update-cart', methods=['POST'])
    def update_cart():
        return updateCart()

    @app.route('/api/wishlist/toggle', methods=['POST'])
    @login_required
    def wishlist_toggle():
        return toggleWishlist()

    @app.route('/api/wishlist/add-to-cart', methods=['POST'])
    @login_required
    def wishlist_add_to_cart():
        return wishlistMoveToCart()

    @app.route('/api/products/reviews', methods=['POST'])
    @login_required
    def api_submit_review():
        return submitProductReview()
    
    # API endpoint for fetching delivery partner documents
    @app.route('/api/delivery-partners/<int:user_id>/documents', methods=['GET'])
    def get_delivery_partner_documents(user_id):
        return getDeliveryPartnerDocuments(user_id)

    # API endpoint for fetching seller documents
    @app.route('/api/sellers/<int:user_id>/documents', methods=['GET'])
    def get_seller_documents(user_id):
        return getSellerDocuments(user_id)

    # Rider pickup APIs
    @app.route('/api/rider/pickups', methods=['GET'])
    @login_required
    def api_rider_pickups():
        return getRiderPickups()

    @app.route('/api/rider/pickups/<int:order_item_id>/details', methods=['GET'])
    @login_required
    def api_rider_pickup_detail(order_item_id):
        return getPickupDetail(order_item_id)

    @app.route('/api/rider/pickups/<int:order_item_id>/claim', methods=['POST'])
    @login_required
    def api_rider_claim_pickup(order_item_id):
        return claimPickupAssignment(order_item_id)

    @app.route('/api/rider/pickups/<int:order_item_id>/status', methods=['POST'])
    @login_required
    def api_rider_update_status(order_item_id):
        return updatePickupStatus(order_item_id)

    @app.route('/api/rider/pickups/<int:order_item_id>/delivery-proof', methods=['POST'])
    @login_required
    def api_rider_delivery_proof(order_item_id):
        return uploadDeliveryProof(order_item_id)

    # Chat APIs
    @app.route('/api/chat/conversations', methods=['GET'])
    @login_required
    def api_list_conversations():
        return getUserConversations()

    @app.route('/api/chat/counterparts', methods=['GET'])
    @login_required
    def api_chat_counterparts():
        return getChatCounterparts()

    @app.route('/api/chat/conversations', methods=['POST'])
    @login_required
    def api_ensure_conversation():
        return ensureConversation()

    @app.route('/api/chat/conversations/<int:conversation_id>/messages', methods=['GET'])
    @login_required
    def api_get_conversation_messages(conversation_id):
        return getConversationMessages(conversation_id)

    @app.route('/api/chat/conversations/<int:conversation_id>/messages', methods=['POST'])
    @login_required
    def api_post_conversation_message(conversation_id):
        return postConversationMessage(conversation_id)

    
    @app.route('/checkout')
    def checkout_page():
        return checkout()
    
    @app.route('/details-submit', methods=['POST'])
    def details_submit():
        return detailsSubmit()
    
    @app.route('/submit-checkout',  methods=['POST'])
    def submit_checkout():
        return submitCheckout()

    @app.route('/order-tracking')
    @login_required
    def order_tracking_hub():
        return orderTrackingHub()

    @app.route('/order-tracking/<reference>')
    @login_required
    def order_tracking(reference):
        return orderTracking(reference)

    @app.route('/order-tracking/latest')
    @login_required
    def order_tracking_latest():
        return orderTrackingLatest()

    @app.route('/order-tracking/<reference>/cancel', methods=['POST'])
    @login_required
    def order_tracking_cancel(reference):
        return cancelOrder(reference)

    @app.route('/order-tracking/<reference>/confirm', methods=['POST'])
    @login_required
    def order_tracking_confirm(reference):
        return confirmOrder(reference)

    @app.route('/order-items/<int:order_item_id>/cancel', methods=['POST'])
    @login_required
    def order_item_cancel(order_item_id):
        return cancelOrderItem(order_item_id)

    @app.route('/order-list')
    @login_required
    def order_list():
        return orderList()

    @app.route('/order-management')
    @login_required
    def order_management_page():
        return orderManagement()

    @app.route('/suborders/update-status', methods=['POST'])
    @login_required
    def suborders_update_status():
        return updateSuborderStatus()

    @app.route('/admin/withdrawals', strict_slashes=False)
    @login_required
    def admin_withdrawals():
        return admin_withdrawals_page()

    @app.route('/admin/withdrawals/decide', methods=['POST'])
    @login_required
    def admin_withdrawals_decide():
        return admin_withdrawal_decide()

    @app.route('/api/wallet/summary', strict_slashes=False)
    @login_required
    def api_wallet_summary_route():
        return api_wallet_summary()

    @app.route('/api/wallet/withdraw', methods=['POST'])
    @login_required
    def api_wallet_withdraw_route():
        return api_wallet_withdraw()