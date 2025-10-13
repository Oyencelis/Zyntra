from flask import render_template, request, session, g, url_for, redirect
from helpers.QueryHelpers import executeGet, executePost, changeStatus
from helpers.HelperFunction import responseData, allowed_image_file, generate_random_filename, generate_random_string
from controller.UserController import getSellers
import locale

locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')


def home():
    query = request.args.get('query', '')
    page = request.args.get('page', 1, type=int)
    categories = getCategoriesInHome("WHERE status = 1")
    
    if query:  # Check if there is a search query
        products = getProductsBySearch(query)  # Call the search function
    else:
        products = getProductsInHome("WHERE p.status = 1", page=page)  # Default products

    cart_items = session.get('cart', {})
    return render_template('views/home.html', cat_data=categories, prod_data=products, page=page, per_page=10, cart_items=cart_items)

def getProductsBySearch(query):
    query = f"%{query}%"
    sql_query = "SELECT p.product_id, p.category_id, p.product_name, c.category_name, pa.attachment, p.description, p.price, p.qty, p.created_at, p.status FROM products p LEFT JOIN categories c ON p.category_id = c.category_id LEFT JOIN product_attachments pa ON p.product_id = pa.product_id WHERE p.product_name LIKE %s AND p.status = 1"
    results = executeGet(sql_query, (query,))
    return results

def getCategoriesInHome(condition=""):
    query = f"SELECT * FROM `categories` {condition}"
    results = executeGet(query)
    return results

def getProductsInHome(condition="", page=1, per_page=10):
    offset = (page - 1) * per_page
    query = f"SELECT p.product_id, p.category_id, p.product_name, c.category_name, pa.attachment, p.description, p.price, p.qty, p.created_at, p.status FROM products p LEFT JOIN categories c ON p.category_id = c.category_id left JOIN product_attachments pa ON p.product_id = pa.product_id {condition} AND c.status != 2 GROUP BY p.product_id, p.category_id, p.product_name, c.category_name, p.price, p.qty, p.created_at, p.status LIMIT {offset}, {per_page}"
    results = executeGet(query)
    
    if not results:  # Check if results is empty
        return []  # Return an empty list or handle as needed

    for product in results:
        product['formatted_price'] = locale.format_string("%0.2f", product['price'], grouping=True)
        if product['attachment'] is not None:
            product['attachment'] = url_for('static', filename='images/uploads/' + product['attachment'])
        else:
            product['attachment'] = None
    return results

def loadMoreProducts():
    page = request.args.get('page', 1, type=int)
    products = getProductsInHome("WHERE p.status = 1", page=page)
    
    if products is None or products == "":
        return responseData("error", "No more products found.", [], 200)

    return responseData("success", "Products loaded successfully.", products, 200)

def categoryPage(category_id):
    products = getProductsInCategoryGrouped(category_id)
    categories = getCategoriesInHome("WHERE status = 1")

    # Check if products list is empty
    if not products:
        return render_template('/views/categories.html', data=[], cat_data=categories)  # Pass an empty list

    return render_template('/views/categories.html', data=products, cat_data=categories)

def getProductsInCategoryGrouped(category_id, page=1, per_page=10):
    offset = (page - 1) * per_page
    query = f"SELECT p.product_id, p.user_id, p.product_name, p.price, p.status AS product_status, pa.product_attachment_id, pa.product_id AS attachment_product_id, pa.attachment, pa.status AS attachment_status, c.category_id, c.category_name, c.status AS category_status FROM products p LEFT JOIN product_attachments pa ON p.product_id = pa.product_id LEFT JOIN categories c ON p.category_id = c.category_id WHERE c.category_id = {category_id} AND c.status = 1 GROUP BY p.product_id LIMIT {offset}, {per_page};"
    results = executeGet(query)
    
    if not results:  # Check if results is empty
        return []  # Return an empty list or handle as needed

    for product in results:
        product['formatted_price'] = locale.format_string("%0.2f", product['price'], grouping=True)
        if 'attachment' in product and product['attachment'] is not None:
            product['attachment'] = url_for('static', filename='images/uploads/' + product['attachment'])
            print(f"Image URL for {product['product_name']}: {product['attachment']}")
        else:
            product['attachment'] = None
            print(f"No image for {product['product_name']}")
    return results

def cart():
    categories = getCategoriesInHome("WHERE status = 1")
    user_id = g.authenticated.get('user_id')  # Get the logged-in user's ID
    if not user_id:
        return redirect(url_for('login_page'))  # Redirect to login if not authenticated

    # Single-line SQL query to retrieve cart items along with product details
    query = "SELECT oi.order_items_id, oi.product_id, oi.user_id, oi.quantity, oi.reference, oi.status, p.product_name, p.price, pa.attachment FROM order_items oi LEFT JOIN products p ON oi.product_id = p.product_id LEFT JOIN product_attachments pa ON p.product_id = pa.product_id WHERE oi.user_id = %s AND oi.status = 1 GROUP by oi.product_id;"

    cart_items = executeGet(query, (user_id,))
    products = []
    total_sum = 0  # Initialize total sum

    for item in cart_items:
        total_price = item['quantity'] * item['price']
        total_sum += total_price
        products.append({
            'order_items_id': item['order_items_id'],
            'product_name': item['product_name'],
            'quantity': item['quantity'],
            'total_price': locale.format_string("%0.2f", total_price, grouping=True),
            'formatted_price': locale.format_string("%0.2f", item['price'], grouping=True),
            'attachment': item['attachment'],
            'product_id': item['product_id'],
        })

    formatted_total_sum = locale.format_string("%0.2f", total_sum, grouping=True)

    return render_template('views/cart.html', cat_data=categories, cart_items=products, total_sum=formatted_total_sum)

def checkout():
    user_id = g.authenticated.get('user_id')
    
    if not user_id:
        return responseData("error", "User not authenticated.", [], 401)

    # Update the status of order items to 2 for the logged-in user
    query = "UPDATE order_items SET status = 2 WHERE user_id = %s AND status = 1"
    results = executeGet(query, (user_id,))

    if results:
        return responseData("success", "Checkout successful", results, 200)
    else:
        return responseData("error", "No items to checkout or update failed.", [], 400)


def submitCheckout(): 
    reference =  generate_random_string(15)
    user_id = g.authenticated.get('user_id')
    total_price = request.form.get('total_price')
    cash_type = request.form.get('payment-method')

    query = "UPDATE order_items SET status = 2, reference = %s WHERE user_id = %s AND status = 1"
    results = executePost(query, (reference, user_id))
    if results:
        insert_query = "INSERT INTO orders (user_id, reference, total_amount, cash_type) VALUES (%s, %s, %s, %s)"
        executePost(insert_query, (user_id, reference, total_price, cash_type))
        return responseData("success", "Checkout successful", reference, 200)
    else:
        return responseData("error", "Checkout failed", [], 400)