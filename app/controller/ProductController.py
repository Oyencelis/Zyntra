from flask import render_template, session, g, request, redirect, url_for
from helpers.QueryHelpers import executeGet, executePost, changeStatus
from helpers.HelperFunction import responseData, allowed_image_file, generate_random_filename
import os
from werkzeug.utils import secure_filename
import uuid
from controller.HomeController import getCategoriesInHome
from controller.UserController import getSellers
import locale

locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static', 'images', 'uploads')

def products():
    active_menu = ['product', 'products']
    categories = getCategories("")
    if g.authenticated.get('role_id') == 1:
        products = getProducts("")
        
    else:
        products = getProducts("AND p.user_id = %s")
    return render_template('views/products/index.html', menu=active_menu, cat_data=categories, prod_data=products)


def getProducts(condition):
    # query = f"SELECT p.product_id, p.category_id, p.product_name, c.category_name, p.description, p.price, p.qty, p.created_at, p.status FROM products p LEFT JOIN categories c ON p.category_id = c.category_id  {prod}"
    query = f"SELECT p.product_id, p.category_id, p.product_name, c.category_name, p.description, p.price, p.qty, p.created_at, p.status, u.user_id, u.firstname, u.lastname FROM products p LEFT JOIN categories c ON p.category_id = c.category_id LEFT JOIN users u ON p.user_id = u.user_id WHERE p.status = 1 AND c.status != 2 {condition}"
    if condition:
        results = executeGet(query, (g.authenticated.get('user_id'),))
    else:
        results = executeGet(query)
    
     # Format the price for each product
    for product in results:
        product['price'] = "{:,.2f}".format(product['price'])
        product['qty'] = "{:,.2f}".format(product['qty'])  

    return results



def addProduct():
    product_name = request.form.get('productName')
    user_id = g.authenticated.get('user_id')
    category_id = request.form.get('category_menu')
    description = request.form.get('description')
    price = request.form.get('price')
    quantity = request.form.get('quantity')
    images = request.files.getlist('productImages[]')
    image_names = []

    if product_name is None or product_name == "":
        return responseData("error", "Product name is required", "", 200)
    if category_id is None or category_id == "":
        return responseData("error", "Please select a category", "", 200)
    if description is None or description.strip() == "" or description.strip() == "<p><br></p>":
        # Check for empty or default Quill editor content
        return responseData("error", "Please provide a description", "", 200)
    if price is None or price == "":
        return responseData("error", "Enter the price", "", 200)
    if quantity is None or quantity == "":
        return responseData("error", "Enter the quantity", "", 200)
    if not images or images[0].filename == '':
        return responseData("error", "Please select image", "", 200)

    #insert attacthment
    for image in images:
        if image and allowed_image_file(image.filename):  # Check if it's a valid file type
            file_extension = os.path.splitext(secure_filename(image.filename))[1]  # Get the file extension
            random_filename = generate_random_filename(file_extension)  # Generate random filename with extension
            image.save(os.path.join(UPLOAD_FOLDER, random_filename))  # Save the file
            image_names.append(random_filename)  # Store the random filename
            print(f"gooodsss {image_names}")
        else:
            print(f"heellooo {image_names}")
            return responseData("error", "Invalid file type", "", 200)   
        
        
    
        
    #Insert product
    
    insert_query = "INSERT INTO products (category_id, user_id, product_name, description, price, qty) VALUES (%s, %s, %s, %s, %s, %s)"
    result = executePost(insert_query, (category_id, user_id, product_name, description, price, quantity))
        
    if "last_inserted_id" in result: 
        # Loop through the image_names array and insert each filename into the database
        for name in image_names:
            attachment_query = "INSERT INTO product_attachments (product_id, attachment) VALUES (%s, %s)"
            try:
                executePost(attachment_query, (result['last_inserted_id'], name))  # Insert product_id and filename
            except Exception as e:
                print(f"Error inserting {name} into database: {str(e)}") 

        return responseData("success", "New product added", "", 200)
    else:
        return responseData("error", "Something went wrong!.", "", 200)
    


def productCategories():
    active_menu = ['product', 'categories']
    # if g.authenticated.get('role_id') == 1:
    #     categories = getCategories("")
    # else:
    categories = getCategories("")
    return render_template('views/products/categories.html', menu=active_menu, cat_data=categories)

def changeProductStatus():
    product_id = request.args.get('prod_id')
    status_to = request.args.get('status_to')
    res = changeStatus("products","product_id", product_id, status_to)
    if res:
        return responseData("success", "Product has been deleted.", product_id, 200)
    
def viewProduct(product_id):
    print(f"Viewing product with ID: {product_id}")  # Debugging line
    categories = getCategoriesInHome("WHERE status = 1")
    cart_items = session.get('cart', {})
    try:
        product_id = int(product_id)
        
        # Updated query to include product images
        query = "SELECT p.product_id, p.product_name, p.description, p.price, p.qty, COALESCE (pa.attachment, 'no-image.jpg') as attachment FROM products p LEFT JOIN product_attachments pa ON p.product_id = pa.product_id WHERE p.product_id = %s AND p.status = 1"
        
        product = executeGet(query, (product_id,))
        
        # Fetch product images
        images_query = "SELECT pa.attachment FROM product_attachments pa WHERE pa.product_id = %s"
        product_images = executeGet(images_query, (product_id,))
        product_images = [img['attachment'] for img in product_images]  # Extract image names
        
        if not product:
            print(f"No product found with ID: {product_id}")
            return render_template('views/404.html'), 404
            
        product = product[0]  # Get the first result
        
        # Prepare image URL
        image_path = product['attachment']
        if image_path and image_path != 'no-image.jpg':
            product_image_url = '/static/images/uploads/' + image_path
        else:
            product_image_url = '/static/images/no-image.jpg'
        
        return render_template('views/Products/view-products.html',
                             product_name=product['product_name'],
                             product_description=product['description'],
                             product_price=product['price'],
                             product_image_url=product_image_url,
                             product_qty=product['qty'],
                             product_id=product_id,
                             cat_data=categories,
                             product_images=product_images,
                             cart_items=cart_items)  # Pass images to template
    except Exception as e:
        print(f"Error in viewProduct: {str(e)}")
        return render_template('views/404.html'), 404





def getCategories(condition):
    # query = f"SELECT c.user_id, c.category_id, c.category_name, c.created_at, c.updated_at, c.status, u.firstname, u.lastname FROM categories c LEFT JOIN users u ON c.user_id = u.user_id {condition} ORDER BY created_at DESC"
    query = f"SELECT * FROM categories WHERE status = 1"
    if condition:
        results = executeGet(query, (g.authenticated.get('user_id'),))
    else:
        results = executeGet(query)
    return results


def getCategoriesByField(field, condition):
    query = f"SELECT {field} FROM categories {condition}"
    results = executeGet(query)
    return results

def getProductsByField(field, condition):
    query = f"SELECT {field} FROM products {condition}"
    results = executeGet(query)
    return results


def addCategories():
    # user_id = g.authenticated.get('user_id')
    category_name = request.form.get('catname')

    if category_name is None or category_name == "":
        return responseData("error", "Category field is required", "", 200)

    categories = getCategoriesByField("category_name",
                                      f"WHERE category_name = '{category_name}'")

    if categories:
        return responseData("error", "Category name is already exist", "", 200)
    else:
        insert_query = "INSERT INTO categories (category_name) VALUES (%s)"
        executePost(insert_query, (category_name,))
        return responseData("success", "New category has been added.", "", 200)



def changeCategoryStatus():
    category_id = request.args.get('cat_id')
    status_to = request.args.get('status_to')
    res = changeStatus("categories","category_id", category_id, status_to)
    if res:
        return responseData("success", "Category has been deleted.", category_id, 200)




def updateCategories():
    category_name = request.form.get('catname')
    category_id = request.form.get('category_id')

    if category_name is None or category_name == "":
        return responseData("error", "Category field is required", "", 200)

    categories = getCategoriesByField("category_name",
                                      f"WHERE category_name = '{category_name}'")

    if categories:
        return responseData("error", "Category name is already exist", "", 200)
    else:
        query = "UPDATE categories SET category_name = %s WHERE category_id = %s"
        executePost(query, (category_name, category_id))
        return responseData("success", "Category has been updated.", "", 200)
    

def updateProducts():
    product_name = request.form.get('prodname')
    category_id = request.form.get('category_id')
    description = request.form.get('description')
    price = request.form.get('price')
    quantity = request.form.get('quantity')
    product_id = request.form.get('product_id')

    # Consolidate validation checks into a single loop
    required_fields = {
        "Product name": product_name,
        "Category": category_id,
        "Description": description,
        "Price": price,
        "Quantity": quantity
    }

    for field_name, value in required_fields.items():
        if not value:
            return responseData("error", f"{field_name} is required", "", 200)

    # Check for existing product name in the same category
    products = getProductsByField("product_name", f"WHERE product_name = '{product_name}' AND category_id = {category_id}")
    if products:
        return responseData("error", "Product name already exists in this category", "", 200)

    # Perform the update query
    query = "UPDATE products SET product_name = %s, category_id = %s, description = %s, price = %s, qty = %s WHERE product_id = %s"
    executePost(query, (product_name, category_id, description, price, quantity, product_id))

    return responseData("success", "Product has been updated.", "", 200)

def addToCart():
    product_id = request.form.get('product_id')
    quantity = request.form.get('quantity', type=int)  # Get the quantity from the form
    user_id = g.authenticated.get('user_id')  # Get the logged-in user's ID

    if user_id and quantity is not None:  # Check if user is logged in and quantity is set
        # Check if the product already exists in the cart
        check_query = "SELECT quantity FROM order_items WHERE product_id = %s AND user_id = %s"
        existing_item = executeGet(check_query, (product_id, user_id))

        if existing_item:  # If the product exists, update the quantity
            new_quantity = existing_item[0]['quantity'] + quantity
            update_query = "UPDATE order_items SET quantity = %s WHERE product_id = %s AND user_id = %s"
            executePost(update_query, (new_quantity, product_id, user_id))
        else:  # If the product does not exist, insert it
            insert_query = "INSERT INTO order_items (product_id, user_id, quantity) VALUES (%s, %s, %s)"
            executePost(insert_query, (product_id, user_id, quantity))

    return responseData("success", "Product added to cart", "", 200)

def removeFromCart():
    product_id = request.form.get('product_id')
    user_id = g.authenticated.get('user_id')
    query = "DELETE FROM order_items WHERE product_id = %s AND user_id = %s"
    executePost(query, (product_id, user_id))
    return redirect(url_for('cart_page'))
def updateCart():
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = data.get('quantity')
    user_id = g.authenticated.get('user_id')

    if user_id and product_id and quantity is not None:
        # Update the quantity in the order_items table
        update_query = "UPDATE order_items SET quantity = %s WHERE product_id = %s AND user_id = %s"
        executePost(update_query, (quantity, product_id, user_id))

        # Get the updated price for the cart item
        total_price_query = "SELECT SUM(o.quantity * p.price) AS total_price FROM order_items o JOIN products p ON o.product_id = p.product_id WHERE o.user_id = %s"
        result = executeGet(total_price_query, (user_id,))
        total_price = result[0]['total_price'] if result else 0

        # Send the updated total price
        return responseData("success", "Quantity updated", {"total_price": total_price}, 200)

    return responseData("error", "Invalid request", "", 400)

def calculateTotalSum(user_id):
    query = "SELECT SUM(quantity * price) FROM order_items WHERE user_id = %s"
    result = executeGet(query, (user_id,))
    return result[0]['SUM(quantity * price)'] if result else 0

def checkout():
    user_id = g.authenticated.get('user_id')  # Get the logged-in user's ID
    if not user_id:
        return redirect(url_for('login_page'))  # Redirect to login if not authenticated

    # Check if the user has items in the cart
    cart_query = "SELECT COUNT(*) as item_count FROM order_items WHERE user_id = %s"
    cart_count = executeGet(cart_query, (user_id,))

    if cart_count and cart_count[0]['item_count'] == 0:
        return redirect(url_for('details_page'))  # Redirect to details.html if no items in cart

    return render_template('views/Products/checkout.html')

def details():
    categories = getCategoriesInHome("WHERE status = 1")
    return render_template('views/Products/details.html', cat_data=categories)

def detailsSubmit():
    user_id = g.authenticated.get('user_id')  # Get the logged-in user's ID

    # Retrieve form data
    floor_unit_number = request.form.get('floor_unit_number')
    region = request.form.get('region')
    province = request.form.get('province')
    city = request.form.get('city')
    barangay = request.form.get('barangay')
    street = request.form.get('street_text')  # Ensure this matches the name attribute
    other_notes = request.form.get('other_notes')  # Ensure this matches the name attribute

    # Debugging: Print the received data
    print("Received data:")
    print(f"User ID: {user_id}")
    print(f"Floor Unit Number: {floor_unit_number}")
    print(f"Region: {region}")
    print(f"Province: {province}")
    print(f"City: {city}")
    print(f"Barangay: {barangay}")
    print(f"Street: {street}")
    print(f"Other Notes: {other_notes}")

    # Check for required fields
    if not all([floor_unit_number, region, province, city, barangay]):
        return responseData("error", "All fields are required.", "", 200)

    # Insert into the database (example)
    insert_query = "INSERT INTO addresses (user_id, floor_unit_number, region, province, city_municipality, barangay, street, other_notes) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
    executePost(insert_query, (user_id, floor_unit_number, region, province, city, barangay, street, other_notes))

    return responseData("success", "Address submitted successfully!", "", 200)