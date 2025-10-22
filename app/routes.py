from functools import wraps
from flask import Flask, session, redirect, url_for, g, render_template, request, flash
from flask_login import current_user
#Middleware
from middleware.auth import login_required
#Helpers
from helpers.Session import sessionRemove
from helpers.HelperFunction import responseData

# Controllers
from controller.HomeController import home, loadMoreProducts, categoryPage, getCategoriesInHome, cart, checkout, submitCheckout, shop

from controller.LoginController import login, LoginSubmit, signup, signupSubmit, sellerSignup, sellerSignupSubmit, deliveryPartnerSignup, deliveryPartnerSignupSubmit
# Authenticate controllers
from controller.DashboardController import dashboardIndex
from controller.ProductController import productCategories, addCategories, changeCategoryStatus, updateCategories, products, addProduct, changeProductStatus, updateProducts, viewProduct, addToCart, removeFromCart, updateCart, details, checkout, detailsSubmit
from controller.ManageProfileController import sellerRequestSubmit, sellerRequest, manageProfile
from controller.UserController import seller, updateSeller, buyer, updateBuyer
from controller.SellerManagementController import (
    get_all_sellers, get_pending_sellers, get_approved_sellers,
    update_seller_status, delete_seller, get_seller_details
)

# Seller Management routes
def seller_management_routes(app):
    @app.route('/admin/sellers')
    @login_required
    def all_sellers():
        sellers = get_all_sellers()
        return render_template('admin/all_seller.html', 
                            menu='seller-list',
                            all_sellers=sellers)

    @app.route('/admin/sellers/pending')
    @login_required
    def pending_sellers():
        pending = get_pending_sellers()
        return render_template('admin/pending_approval.html', 
                            menu='seller-pending',
                            pending_sellers=pending)

    @app.route('/admin/sellers/approved')
    @login_required
    def approved_sellers():
        approved = get_approved_sellers()
        return render_template('admin/approved_seller.html', 
                            menu='seller-approved',
                            approved_sellers=approved)
    
    @app.route('/admin/sellers/<int:user_id>/view')
    @login_required
    def view_seller(user_id):
        seller = get_seller_details(user_id)
        if not seller:
            flash('Seller not found', 'error')
            return redirect(url_for('all_sellers'))
        return render_template('admin/view_seller.html', 
                            seller=seller,
                            menu='seller-list')
    
    @app.route('/admin/sellers/<int:user_id>/approve', methods=['POST'])
    @login_required
    def approve_seller(user_id):
        from controller.SellerManagementController import update_seller_status
        try:
            # Status 1 = Approved/Active
            result = update_seller_status(user_id, 1, session.get('user_id'))
            flash('Seller approved successfully', 'success')
        except Exception as e:
            current_app.logger.error(f'Error approving seller: {str(e)}')
            flash('Error approving seller', 'error')
        # Redirect back to the referring page or all_sellers if no referrer
        return redirect(request.referrer or url_for('all_sellers'))
    
    @app.route('/admin/sellers/<int:user_id>/reject', methods=['POST'])
    @login_required
    def reject_seller(user_id):
        from controller.SellerManagementController import update_seller_status
        try:
            # Status 3 = Rejected
            result = update_seller_status(user_id, 3, session.get('user_id'))
            flash('Seller rejected successfully', 'success')
        except Exception as e:
            current_app.logger.error(f'Error rejecting seller: {str(e)}')
            flash('Error rejecting seller', 'error')
        # Redirect back to the referring page or all_sellers if no referrer
        return redirect(request.referrer or url_for('all_sellers'))
    
    @app.route('/admin/sellers/<int:user_id>/block', methods=['POST'])
    @login_required
    def block_seller(user_id):
        from controller.SellerManagementController import update_seller_status
        try:
            # Status 4 = Blocked
            result = update_seller_status(user_id, 4, session.get('user_id'))
            flash('Seller blocked successfully', 'success')
        except Exception as e:
            current_app.logger.error(f'Error blocking seller: {str(e)}')
            flash('Error blocking seller', 'error')
        return redirect(request.referrer or url_for('all_sellers'))
    
    @app.route('/admin/sellers/<int:user_id>/unblock', methods=['POST'])
    @login_required
    def unblock_seller(user_id):
        from controller.SellerManagementController import update_seller_status
        try:
            # Status 1 = Active
            result = update_seller_status(user_id, 1, session.get('user_id'))
            flash('Seller unblocked successfully', 'success')
        except Exception as e:
            current_app.logger.error(f'Error unblocking seller: {str(e)}')
            flash('Error unblocking seller', 'error')
        return redirect(request.referrer or url_for('all_sellers'))
    
    @app.route('/admin/sellers/<int:user_id>/delete', methods=['POST'])
    @login_required
    def delete_seller(user_id):
        try:
            delete_seller(user_id, current_user.user_id)
            flash('Seller deleted successfully', 'success')
        except Exception as e:
            app.logger.error(f'Error deleting seller: {str(e)}')
            flash('Error deleting seller', 'error')
        return redirect(url_for('all_sellers'))



def setup_routes(app: Flask):
    # Initialize seller management routes
    seller_management_routes(app)


    @app.before_request
    def load_user():
        g.authenticated = session.get('authenticated', None)

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
        if g.authenticated:
            return redirect(url_for('home_page'))  # Redirect to home if logged in
        return login() 
    
    @app.route('/login', methods=['POST'])
    def login_submit():
        return LoginSubmit() 
    
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
    
    # Public Seller Signup (no login required)
    @app.route('/sell')
    def sell_page():
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

    @app.route('/dashboard')
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
    
    @app.route('/products')
    @login_required
    def products_page():
        return redirect(url_for('seller_products'))
        
    @app.route('/seller/products')
    @login_required
    def seller_products():
        return products()
    
    @app.route('/products/add', methods=['GET', 'POST'])
    @app.route('/seller/products/add', methods=['GET', 'POST'])
    @login_required
    def add_product():
        print("Debug: Entering add_product route")  # Debug log
        print(f"Debug: Request method: {request.method}")  # Debug log
        if request.method == 'GET':
            print("Debug: Handling GET request")  # Debug log
            from controller.ProductController import getCategories
            categories = getCategories("")
            print(f"Debug: Found {len(categories)} categories")  # Debug log
            print(f"Debug: Template path: {app.template_folder}")  # Debug log
            return render_template('seller/add_product.html', categories=categories)
        print("Debug: Handling POST request")  # Debug log
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
    
    @app.route('/profile')
    @login_required
    def manage_profile():
        return manageProfile()
    
    @app.route('/update-seller', methods=['GET', 'POST'])
    def update_seller():
        return updateSeller()
    
    @app.route('/update-buyer', methods=['GET', 'POST'])
    def update_buyer():
        return updateBuyer()
    
    @app.route('/load_more_products', methods=['GET'])
    def load_more_products():
        return loadMoreProducts()
    
    @app.route('/category/<int:category_id>', methods=['GET', 'POST'])
    def category_page(category_id):
        return categoryPage(category_id)
    

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('views/404.html'), 404
    
    # Deliver with Zyntra (courier/driver signup)
    @app.route('/deliver')
    def deliver_page():
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
    
    @app.route('/checkout')
    def checkout_page():
        return checkout()
    
    @app.route('/details-submit', methods=['POST'])
    def details_submit():
        return detailsSubmit()
    
    @app.route('/submit-checkout',  methods=['POST'])
    def submit_checkout():
        return submitCheckout()

    