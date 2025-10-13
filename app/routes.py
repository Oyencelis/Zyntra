from functools import wraps
from flask import Flask, session, redirect, url_for, g, render_template
#Middleware
from middleware.auth import login_required
#Helpers
from helpers.Session import sessionRemove
from helpers.HelperFunction import responseData

# Controllers
from controller.HomeController import home, loadMoreProducts, categoryPage, getCategoriesInHome, cart, checkout, submitCheckout

from controller.LoginController import login, LoginSubmit, signup, signupSubmit, sellerSignup, sellerSignupSubmit, deliveryPartnerSignup, deliveryPartnerSignupSubmit
# Authenticate controllers
from controller.DashboardController import dashboardIndex
from controller.ProductController import productCategories, addCategories, changeCategoryStatus, updateCategories, products, addProduct, changeProductStatus, updateProducts, viewProduct, addToCart, removeFromCart, updateCart, details, checkout, detailsSubmit
from controller.ManageProfileController import sellerRequestSubmit, sellerRequest, manageProfile
from controller.UserController import seller, updateSeller, buyer, updateBuyer





def setup_routes(app: Flask):

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
    def product_page():
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

    