# pyrefly: ignore [missing-import]
from flask import render_template, session, g, request, redirect, url_for
import html
from helpers.QueryHelpers import executeGet, executePost, changeStatus
from helpers.HelperFunction import responseData, allowed_image_file, generate_random_filename, init_app_locale
from helpers.SupabaseStorage import upload_file_to_supabase, resolve_storage_url
from helpers.delivery_media import save_compressed_proof
from helpers.marketplace_settings import get_bool_setting, get_float_setting
import os
import json
# pyrefly: ignore [missing-import]
from werkzeug.utils import secure_filename
import uuid
from controller.HomeController import getCategoriesInHome, get_user_wishlist_ids
from controller.UserController import getSellers
import locale
import re

init_app_locale()

ALLOWED_VARIANT_TYPES = {'none', 'sizes', 'colors'}

def _normalize_variant_values(raw_values):
    if not raw_values:
        return None
    values = [value.strip() for value in raw_values.split(',')]
    cleaned = [value for value in values if value]
    return ', '.join(cleaned) if cleaned else None

def _variant_columns_available():
    """
    Check if variant_type and variant_values columns exist in products table.
    We query every time to avoid stale cache when migrations run while the app stays alive.
    """
    variant_type_col = executeGet(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'products'
          AND column_name = 'variant_type'
        """
    )
    if isinstance(variant_type_col, tuple) or not variant_type_col:
        return False
    variant_values_col = executeGet(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'products'
          AND column_name = 'variant_values'
        """
    )
    if isinstance(variant_values_col, tuple) or not variant_values_col:
        return False
    return True

def _get_product_id_from_request():
    payload = request.get_json(silent=True)
    product_id = None
    if payload and 'product_id' in payload:
        product_id = payload.get('product_id')
    elif 'product_id' in request.form:
        product_id = request.form.get('product_id')
    variant_type = (request.form.get('variant_type') or 'none').lower()
    variant_values_input = request.form.get('variant_values')

    try:
        return int(product_id)
    except (TypeError, ValueError):
        return None

def _ensure_buyer_authenticated():
    if not g.authenticated:
        return None, responseData("error", "Please login to continue.", "", 401)

    user_id = g.authenticated.get('user_id')
    role_id = g.authenticated.get('role_id')

    if role_id != 2:
        return None, responseData("error", "Only buyers can perform this action.", "", 403)

    return user_id, None

def _get_wishlist_count(user_id):
    query = "SELECT COUNT(*) AS total FROM wishlists WHERE user_id = %s"
    result = executeGet(query, (user_id,))
    if isinstance(result, tuple):
        return 0
    return (result[0].get('total') if result else 0) or 0

def _get_cart_count(user_id):
    query = """
        SELECT COUNT(*) AS total
        FROM order_items
        WHERE user_id = %s
          AND status = 1
          AND (reference = '' OR reference IS NULL)
    """
    result = executeGet(query, (user_id,))
    if isinstance(result, tuple):
        return 0
    return (result[0].get('total') if result else 0) or 0

def build_product_image_url(attachment):
    if not attachment or attachment in ('no-image.jpg', ''):
        return '/static/images/no-image.jpg'

    if isinstance(attachment, str):
        attachment = attachment.strip()
        if attachment.startswith(('http://', 'https://')):
            return resolve_storage_url(attachment) or attachment

        url_match = re.search(r'https?://[^\s\'\"]+', attachment)
        if url_match:
            extracted_url = url_match.group(0)
            return resolve_storage_url(extracted_url) or extracted_url

    clean_path = attachment.replace('\\', '/').lstrip('/')

    if clean_path.startswith('static/'):
        return '/' + clean_path if not clean_path.startswith('/') else clean_path

    if clean_path.startswith('images/'):
        return f"/static/{clean_path}"

    if clean_path.startswith('uploads/'):
        return f"/static/{clean_path}"

    if clean_path.startswith('products/'):
        return f"/static/uploads/{clean_path}"

    return f"/static/uploads/products/{clean_path}"

def products():
    active_menu = ['product', 'products']
    categories = getCategories("")
    if g.authenticated.get('role_id') == 1:
        products = getProducts("")
        
    else:
        products = getProducts("AND p.user_id = %s")
    
    # Add product images to each product
    for product in products:
        product_id = product['product_id']
        # Get product images
        query = "SELECT attachment FROM product_attachments WHERE product_id = %s AND status = 1"
        images = executeGet(query, (product_id,))
        product['images'] = [img['attachment'] for img in images]
    
    return render_template('views/products/index.html', 
                         menu=active_menu, 
                         categories=categories, 
                         products=products,
                         current_user_id=g.authenticated.get('user_id'))

def getProducts(condition):
    variant_columns = _variant_columns_available()
    variant_select = "p.variant_type, p.variant_values," if variant_columns else "'none' AS variant_type, NULL AS variant_values,"
    query = f"""SELECT p.product_id,
                       p.category_id,
                       p.product_name,
                       c.category_name,
                       p.description,
                       p.price,
                       p.qty,
                       {variant_select}
                       p.created_at,
                       p.status,
                       u.user_id,
                       u.firstname,
                       u.lastname
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.category_id
                LEFT JOIN users u ON p.user_id = u.user_id
                WHERE p.status = 1 AND c.status != 2 {condition}"""
    if condition:
        results = executeGet(query, (g.authenticated.get('user_id'),))
    else:
        results = executeGet(query)
    
    if isinstance(results, tuple):
        # Underlying DB error; return empty list to avoid crashes while surfacing message elsewhere.
        return []
    
    # Convert and format price and quantity for each product
    for product in results:
        try:
            # Ensure price is a float
            if product['price'] is not None:
                if isinstance(product['price'], str):
                    # Remove any non-numeric characters except decimal point
                    price_str = ''.join(c for c in product['price'] if c.isdigit() or c == '.')
                    product['price'] = float(price_str) if price_str else 0.0
                else:
                    product['price'] = float(product['price'])
            else:
                product['price'] = 0.0
                
            # Ensure quantity is an integer
            if product['qty'] is not None:
                if isinstance(product['qty'], str):
                    # Remove any non-numeric characters
                    qty_str = ''.join(c for c in product['qty'] if c.isdigit())
                    product['qty'] = int(qty_str) if qty_str else 0
                else:
                    product['qty'] = int(product['qty'])
            else:
                product['qty'] = 0
                
        except (ValueError, TypeError) as e:
            print(f"Error formatting product data: {e}")
            product['price'] = 0.0
            product['qty'] = 0

    return results

def addProduct():
    try:
        product_name = request.form.get('productName')
        user_id = g.authenticated.get('user_id')
        category_id = request.form.get('category_menu')
        description = request.form.get('description')
        price = request.form.get('price')
        quantity = request.form.get('quantity')
        images = request.files.getlist('productImages[]')
        variant_type = (request.form.get('variant_type') or 'none').lower()
        variant_values_input = request.form.get('variant_values')

        # Input validation
        if not all([product_name, category_id, description, price, quantity]):
            return responseData("error", "All fields are required", "", 200)
            
        if description.strip() in ["", "<p><br></p>"]:
            return responseData("error", "Please provide a description", "", 200)
            
        if not images or not images[0].filename:
            return responseData("error", "Please select at least one image", "", 200)

        variant_columns = _variant_columns_available()
        if not variant_columns:
            # Database not yet migrated; silently drop variant metadata to keep flow working.
            variant_type = 'none'
            normalized_variant_values = None
        else:
            if variant_type not in ALLOWED_VARIANT_TYPES:
                variant_type = 'none'

            normalized_variant_values = None
            if variant_type != 'none':
                normalized_variant_values = _normalize_variant_values(variant_values_input or "")
                if not normalized_variant_values:
                    return responseData("error", "Please provide at least one variant option.", "", 200)

        # Process each image
        image_names = []
        for image in images:
            if not image or not allowed_image_file(image.filename):
                continue  # Skip invalid files instead of failing the entire upload

            try:
                public_url, upload_error = upload_file_to_supabase(image, 'products')
                if upload_error or not public_url:
                    print(f"Error uploading file {image.filename} to Supabase: {upload_error}")
                    continue
                image_names.append(public_url)
            except Exception as e:
                print(f"Error uploading file {image.filename}: {str(e)}")
                continue
        
        if not image_names:
            return responseData("error", "No valid images were uploaded", "", 200)
        
        # Insert product
        if not variant_columns:
            insert_query = """
                INSERT INTO products 
                (category_id, user_id, product_name, description, price, qty) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            insert_params = (category_id, user_id, product_name, description, price, quantity)
        else:
            insert_query = """
                INSERT INTO products 
                (category_id, user_id, product_name, description, price, qty, variant_type, variant_values) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            insert_params = (category_id, user_id, product_name, description, price, quantity, variant_type, normalized_variant_values)

        result = executePost(insert_query, insert_params)
        
        if not result or 'last_inserted_id' not in result:
            return responseData("error", "Failed to save product information", "", 500)
        
        # Save image references to database
        product_id = result['last_inserted_id']
        attachment_query = """
            INSERT INTO product_attachments 
            (product_id, attachment) 
            VALUES (%s, %s)
        """
        
        success_count = 0
        for img_path in image_names:
            try:
                executePost(attachment_query, (product_id, img_path))
                success_count += 1
            except Exception as e:
                print(f"Error saving attachment {img_path}: {str(e)}")
        
        if success_count == 0:
            # If no attachments were saved, clean up the product record
            executePost("DELETE FROM products WHERE product_id = %s", (product_id,))
            return responseData("error", "Failed to save product images", "", 500)
        
        return responseData("success", "Product added successfully", {"product_id": product_id}, 200)
        
    except Exception as e:
        print(f"Unexpected error in addProduct: {str(e)}")
        return responseData("error", "An unexpected error occurred: " + str(e), "", 500)

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
        
        # Updated query to include product images and store name
        query = """
            SELECT 
                p.product_id, 
                p.user_id AS seller_id,
                p.product_name, 
                p.description, 
                p.price, 
                p.qty, 
                p.variant_type,
                p.variant_values,
                COALESCE(p.protection_eligible, TRUE) AS protection_eligible,
                COALESCE(pa.attachment, 'no-image.jpg') as attachment,
                sd.store_name,
                sd.description AS store_description
            FROM 
                products p 
            LEFT JOIN 
                product_attachments pa ON p.product_id = pa.product_id AND pa.status = 1
            LEFT JOIN
                seller_details sd ON p.user_id = sd.user_id
            WHERE 
                p.product_id = %s 
                AND p.status = 1
            LIMIT 1
        """
        
        product = executeGet(query, (product_id,))
        
        if not product:
            print(f"No product found with ID: {product_id}")
            return render_template('views/404.html'), 404
            
        product = product[0]  # Get the first result
        
        # Prepare main image URL
        product_image_url = build_product_image_url(product['attachment'])

        # Fetch and prepare product images for the slider
        images_query = """
            SELECT pa.attachment
            FROM product_attachments pa
            WHERE pa.product_id = %s AND pa.status = 1
            GROUP BY pa.attachment
            ORDER BY MIN(pa.created_at) ASC
        """
        product_images = executeGet(images_query, (product_id,))

        clean_images = []
        seen_images = set()
        for img in product_images or []:
            attachment = img.get('attachment')
            if not attachment or attachment in seen_images:
                continue
            seen_images.add(attachment)
            clean_images.append(build_product_image_url(attachment))

        if not clean_images:
            clean_images = [product_image_url]

        wishlist_ids = set()
        user_id = None
        if g.authenticated and g.authenticated.get('user_id'):
            user_id = g.authenticated.get('user_id')
            wishlist_ids = get_user_wishlist_ids(user_id)

        is_in_wishlist = product_id in wishlist_ids

        variant_type = product.get('variant_type') or 'none'
        raw_variant_values = product.get('variant_values') or ''
        variant_values = [value.strip() for value in raw_variant_values.split(',') if value.strip()]

        reviews, review_count, average_rating = _get_product_reviews(product_id)
        can_review = _buyer_can_review_product(user_id, product_id) if user_id else False
        protection_show_badge = bool(product.get("protection_eligible", True)) and get_bool_setting(
            "protection_enabled", True
        )
        free_ship = int(get_float_setting("shipping_free_threshold", 2000))

        return render_template('views/products/view-product.html',
                             product_name=product['product_name'],
                             product_description=product['description'],
                             product_price=product['price'],
                             product_image_url=product_image_url,
                             product_qty=product['qty'],
                             product_id=product_id,
                             cat_data=categories,
                             product_images=clean_images,
                             cart_items=cart_items,
                             store_name=product.get('store_name', 'Zyntra Store'),
                             store_description=product.get('store_description'),
                             seller_id=product.get('seller_id'),
                             is_in_wishlist=is_in_wishlist,
                             wishlist_ids=list(wishlist_ids),
                             reviews=reviews,
                             review_count=review_count,
                             average_rating=average_rating,
                             can_review=can_review,
                             variant_type=variant_type,
                             variant_values=variant_values,
                             protection_show_badge=protection_show_badge,
                             free_shipping_threshold=free_ship)
    except Exception as e:
        print(f"Error in viewProduct: {str(e)}")
        return render_template('views/404.html'), 404

def storeProducts(seller_id):
    categories = getCategoriesInHome("WHERE status = 1")
    cart_items = session.get('cart', {})

    try:
        seller_id = int(seller_id)
    except (TypeError, ValueError):
        return render_template('views/404.html'), 404

    store_query = """
        SELECT 
            sd.user_id,
            sd.store_name,
            sd.description,
            sd.region,
            sd.province,
            sd.city,
            sd.barangay,
            sd.street,
            sd.gov_id_path,
            sd.business_permit_path,
            u.firstname,
            u.lastname
        FROM seller_details sd
        LEFT JOIN users u ON sd.user_id = u.user_id
        WHERE sd.user_id = %s AND sd.status IN (1, 2)
    """

    store_result = executeGet(store_query, (seller_id,))

    if not isinstance(store_result, (list, tuple)):
        return store_result

    if not store_result:
        return render_template('views/404.html'), 404

    store = store_result[0]

    if not isinstance(store, dict):
        return store

    def build_store_image(image_path, fallback='/static/images/store-cover.jpg'):
        if not image_path:
            return fallback
        return build_product_image_url(image_path)

    store['logo_url'] = build_store_image(store.get('gov_id_path'), '/static/images/store-logo.png')
    store['banner_url'] = build_store_image(store.get('business_permit_path'), '/static/images/store-cover.jpg')

    address_parts = [
        store.get('street'),
        store.get('barangay'),
        store.get('city'),
        store.get('province'),
        store.get('region')
    ]
    store['address_text'] = ", ".join([part for part in address_parts if part])

    products_query = """
        SELECT 
            p.product_id,
            p.product_name,
            p.price,
            p.qty,
            p.description,
            COALESCE(
                (
                    SELECT pa.attachment 
                    FROM product_attachments pa 
                    WHERE pa.product_id = p.product_id AND pa.status = 1 
                    ORDER BY pa.created_at ASC LIMIT 1
                ),
                'images/no-image.jpg'
            ) AS attachment
        FROM products p
        WHERE p.user_id = %s AND p.status = 1
        ORDER BY p.updated_at DESC
    """

    seller_products = executeGet(products_query, (seller_id,))

    if not isinstance(seller_products, (list, tuple)):
        return seller_products

    wishlist_ids = set()
    if g.authenticated and g.authenticated.get('user_id'):
        wishlist_ids = get_user_wishlist_ids(g.authenticated.get('user_id'))

    for product in seller_products:
        product['image_url'] = build_product_image_url(product.get('attachment'))
        try:
            product['price'] = float(product['price']) if product['price'] is not None else 0.0
        except (TypeError, ValueError):
            product['price'] = 0.0
        product['qty'] = product.get('qty') or 0
        product['is_in_wishlist'] = product.get('product_id') in wishlist_ids

    total_inventory = sum(prod['qty'] for prod in seller_products)

    stats = {
        'products': len(seller_products),
        'inventory': total_inventory,
        'rating': '4.9'
    }

    return render_template(
        'views/products/store.html',
        store=store,
        products=seller_products,
        stats=stats,
        seller_id=seller_id,
        cat_data=categories,
        cart_items=cart_items,
        wishlist_ids=list(wishlist_ids)
    )

def getCategories(condition):
    # query = f"SELECT c.user_id, c.category_id, c.category_name, c.created_at, c.updated_at, c.status, u.firstname, u.lastname FROM categories c LEFT JOIN users u ON c.user_id = u.user_id {condition} ORDER BY created_at DESC"
    query = f"SELECT * FROM categories WHERE status = 1"
    if condition:
        results = executeGet(query, (g.authenticated.get('user_id'),))
    else:
        results = executeGet(query)
    return results

def addCategories():
    # user_id = g.authenticated.get('user_id')
    category_name = request.form.get('catname')

    if category_name is None or category_name == "":
        return responseData("error", "Category field is required", "", 200)

    categories = executeGet(
        "SELECT category_name FROM categories WHERE category_name = %s",
        (category_name,),
    )

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

    categories = executeGet(
        "SELECT category_name FROM categories WHERE category_name = %s",
        (category_name,),
    )

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
    variant_type = (request.form.get('variant_type') or 'none').lower()
    variant_values_input = request.form.get('variant_values')

    # Consolidate validation checks into a single loop
    required_fields = {
        "Product name": product_name,
        "Category": category_id,
        "Description": description,
        "Price": price,
        "Quantity": quantity,
        "Product ID": product_id
    }

    for field_name, value in required_fields.items():
        if not value:
            return responseData("error", f"{field_name} is required", "", 200)

    try:
        product_id_int = int(product_id)
        category_id_int = int(category_id)
    except (TypeError, ValueError):
        return responseData("error", "Invalid product or category identifier.", "", 400)

    variant_columns = _variant_columns_available()

    if variant_type not in ALLOWED_VARIANT_TYPES or not variant_columns:
        variant_type = 'none'

    normalized_variant_values = None
    if variant_type != 'none':
        normalized_variant_values = _normalize_variant_values(variant_values_input or "")
        if not normalized_variant_values:
            return responseData("error", "Please provide at least one variant option.", "", 200)

    # Get the current product to check if the name is being changed
    current_product = executeGet(
        "SELECT product_name, category_id FROM products WHERE product_id = %s",
        (product_id_int,),
    )

    if not current_product:
        return responseData("error", "Product not found", "", 404)

    current_name = current_product[0]['product_name']
    current_category = current_product[0]['category_id']

    # Only check for duplicate name if the name or category has changed
    try:
        current_category_int = int(current_category)
    except (TypeError, ValueError):
        return responseData("error", "Invalid stored category for this product.", "", 500)

    if product_name != current_name or category_id_int != current_category_int:
        products = executeGet(
            """
            SELECT product_id FROM products
            WHERE product_name = %s AND category_id = %s AND product_id != %s
            """,
            (product_name, category_id_int, product_id_int),
        )
        if products:
            return responseData("error", "Product name already exists in this category", "", 200)

    try:
        # Perform the update query
        if variant_columns:
            query = """
                UPDATE products 
                SET product_name = %s, 
                    category_id = %s, 
                    description = %s, 
                    price = %s, 
                    qty = %s,
                    variant_type = %s,
                    variant_values = %s
                WHERE product_id = %s
            """
            params = (
                product_name,
                category_id_int,
                description,
                price,
                quantity,
                variant_type,
                normalized_variant_values,
                product_id_int,
            )
        else:
            query = """
                UPDATE products 
                SET product_name = %s, 
                    category_id = %s, 
                    description = %s, 
                    price = %s, 
                    qty = %s
                WHERE product_id = %s
            """
            params = (
                product_name,
                category_id_int,
                description,
                price,
                quantity,
                product_id_int,
            )

        executePost(query, params)
        return responseData("success", "Product has been updated successfully.", "", 200)
    except Exception as e:
        print(f"Error updating product: {str(e)}")
        return responseData("error", "An error occurred while updating the product", "", 500)

def addToCart():
    if not g.authenticated:
        return responseData("error", "Please login to add products to your cart.", "", 401)

    user_id = g.authenticated.get('user_id')
    role_id = g.authenticated.get('role_id')

    if role_id != 2:  # Only buyers can add to cart
        return responseData("error", "Only buyers can add items to the cart.", "", 403)

    product_id = request.form.get('product_id', type=int)
    quantity = request.form.get('quantity', type=int)
    selected_variant_value = (request.form.get('variant_selection') or '').strip()

    if not product_id or not quantity or quantity <= 0:
        return responseData("error", "Invalid product or quantity.", "", 400)

    # Validate product availability and fetch variant metadata
    product_rows = executeGet(
        "SELECT qty, variant_type, variant_values FROM products WHERE product_id = %s AND status = 1",
        (product_id,)
    )
    if isinstance(product_rows, tuple):  # Propagate DB errors
        return product_rows

    if not product_rows:
        return responseData("error", "Product is unavailable or no longer exists.", "", 404)

    product_row = product_rows[0]
    available_qty = int(product_row.get('qty') or 0)
    if available_qty <= 0:
        return responseData("error", "This product is currently out of stock.", "", 400)

    product_variant_type = (product_row.get('variant_type') or 'none').lower()
    normalized_variant_type = product_variant_type if product_variant_type in ALLOWED_VARIANT_TYPES else 'none'
    normalized_variant_value = None

    if normalized_variant_type != 'none':
        raw_values = product_row.get('variant_values') or ''
        allowed_values = [value.strip() for value in raw_values.split(',') if value.strip()]
        if not selected_variant_value:
            return responseData("error", f"Please select a {normalized_variant_type[:-1] if normalized_variant_type.endswith('s') else normalized_variant_type}.", "", 400)

        matched_value = next(
            (value for value in allowed_values if value.lower() == selected_variant_value.lower()),
            None
        )
        if not matched_value:
            return responseData("error", "Selected variant option is invalid.", "", 400)
        normalized_variant_value = matched_value
    else:
        normalized_variant_type = 'none'

    # Load existing cart entry for same product + variant
    check_query = """
        SELECT order_items_id, quantity
        FROM order_items
        WHERE product_id = %s
          AND user_id = %s
          AND status = 1
          AND (reference = '' OR reference IS NULL)
          AND variant_type = %s
          AND (
                (variant_value IS NULL AND %s IS NULL)
                OR variant_value = %s
          )
    """
    check_params = (product_id, user_id, normalized_variant_type, normalized_variant_value, normalized_variant_value)
    existing_item = executeGet(check_query, check_params)
    if isinstance(existing_item, tuple):
        return existing_item

    if existing_item:
        new_quantity = int(existing_item[0]['quantity']) + quantity
        update_query = """
            UPDATE order_items
            SET quantity = %s
            WHERE order_items_id = %s
              AND user_id = %s
              AND status = 1
              AND (reference = '' OR reference IS NULL)
        """
        update_result = executePost(update_query, (new_quantity, existing_item[0]['order_items_id'], user_id))
        if isinstance(update_result, tuple):
            return update_result
        executePost("UPDATE products SET qty = qty - %s WHERE product_id = %s", (quantity, product_id))
    else:
        insert_query = """
            INSERT INTO order_items (product_id, user_id, quantity, reference, status, variant_type, variant_value)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        insert_result = executePost(
            insert_query,
            (product_id, user_id, quantity, '', 1, normalized_variant_type, normalized_variant_value)
        )
        if isinstance(insert_result, tuple):
            return insert_result
        executePost("UPDATE products SET qty = qty - %s WHERE product_id = %s", (quantity, product_id))

    counts = {
        "cart_count": _get_cart_count(user_id),
        "wishlist_count": _get_wishlist_count(user_id)
    }
    return responseData("success", "Product added to cart", counts, 200)

def removeFromCart():
    order_item_id = request.form.get('order_item_id', type=int)
    user_id = g.authenticated.get('user_id')

    if not order_item_id or not user_id:
        return redirect(url_for('cart_page'))

    item = executeGet("SELECT product_id, quantity FROM order_items WHERE order_items_id = %s", (order_item_id,))
    if item:
        executePost("UPDATE products SET qty = qty + %s WHERE product_id = %s", (item[0]['quantity'], item[0]['product_id']))

    query = """
        DELETE FROM order_items
        WHERE order_items_id = %s
          AND user_id = %s
          AND status = 1
          AND (reference = '' OR reference IS NULL)
    """
    executePost(query, (order_item_id, user_id))
    return redirect(url_for('cart_page'))
def updateCart():
    data = request.get_json()
    order_item_id = data.get('order_item_id')
    quantity = data.get('quantity')
    user_id = g.authenticated.get('user_id')

    if user_id and order_item_id and quantity is not None:
        item = executeGet("SELECT product_id, quantity FROM order_items WHERE order_items_id = %s", (order_item_id,))
        if item:
            item_qty = item[0]['quantity']
            prod_id = item[0]['product_id']
            diff = quantity - item_qty
            if diff > 0:
                executePost("UPDATE products SET qty = qty - %s WHERE product_id = %s", (diff, prod_id))
            elif diff < 0:
                executePost("UPDATE products SET qty = qty + %s WHERE product_id = %s", (-diff, prod_id))

        # Update the quantity in the order_items table
        update_query = """
            UPDATE order_items
            SET quantity = %s
            WHERE order_items_id = %s
              AND user_id = %s
              AND status = 1
              AND (reference = '' OR reference IS NULL)
        """
        executePost(update_query, (quantity, order_item_id, user_id))

        # Get the updated price for the cart item
        total_price_query = """
            SELECT SUM(o.quantity * p.price) AS total_price
            FROM order_items o
            JOIN products p ON o.product_id = p.product_id
            WHERE o.user_id = %s
              AND o.status = 1
              AND (o.reference = '' OR o.reference IS NULL)
        """
        result = executeGet(total_price_query, (user_id,))
        total_price = result[0]['total_price'] if result else 0

        # Send the updated total price
        return responseData("success", "Quantity updated", {"total_price": total_price}, 200)

    return responseData("error", "Invalid request", "", 400)

def calculateTotalSum(user_id):
    query = """
        SELECT SUM(o.quantity * p.price) AS total
        FROM order_items o
        JOIN products p ON o.product_id = p.product_id
        WHERE o.user_id = %s
          AND o.status = 1
          AND (o.reference = '' OR o.reference IS NULL)
    """
    result = executeGet(query, (user_id,))
    return result[0]['total'] if result else 0


def toggleWishlist():
    user_id, auth_error = _ensure_buyer_authenticated()
    if auth_error:
        return auth_error

    product_id = _get_product_id_from_request()
    if not product_id:
        return responseData("error", "Invalid product.", "", 400)

    product_rows = executeGet("SELECT product_id FROM products WHERE product_id = %s AND status = 1", (product_id,))
    if isinstance(product_rows, tuple):
        return product_rows
    if not product_rows:
        return responseData("error", "Product not found.", "", 404)

    wishlist_entry = executeGet(
        """
            SELECT wishlist_id
            FROM wishlists
            WHERE user_id = %s AND product_id = %s
        """,
        (user_id, product_id)
    )
    if isinstance(wishlist_entry, tuple):
        return wishlist_entry

    if wishlist_entry:
        delete_result = executePost("DELETE FROM wishlists WHERE wishlist_id = %s", (wishlist_entry[0]['wishlist_id'],))
        if isinstance(delete_result, tuple):
            return delete_result
        is_wishlist = False
        message = "Removed from wishlist."
    else:
        insert_result = executePost(
            """
                INSERT INTO wishlists (user_id, product_id)
                VALUES (%s, %s)
            """,
            (user_id, product_id)
        )
        if isinstance(insert_result, tuple):
            return insert_result
        is_wishlist = True
        message = "Saved to wishlist."

    data = {
        "is_wishlist": is_wishlist,
        "wishlist_count": _get_wishlist_count(user_id),
        "cart_count": _get_cart_count(user_id)
    }
    return responseData("success", message, data, 200)


def wishlistMoveToCart():
    user_id, auth_error = _ensure_buyer_authenticated()
    if auth_error:
        return auth_error

    product_id = _get_product_id_from_request()
    if not product_id:
        return responseData("error", "Invalid product.", "", 400)

    wishlist_item = executeGet(
        """
            SELECT wishlist_id
            FROM wishlists
            WHERE user_id = %s AND product_id = %s
        """,
        (user_id, product_id)
    )
    if isinstance(wishlist_item, tuple):
        return wishlist_item
    if not wishlist_item:
        return responseData("error", "Item not found in wishlist.", "", 404)

    product_rows = executeGet("SELECT qty FROM products WHERE product_id = %s AND status = 1", (product_id,))
    if isinstance(product_rows, tuple):
        return product_rows
    if not product_rows:
        return responseData("error", "Product not found.", "", 404)

    available_qty = int(product_rows[0].get('qty') or 0)
    if available_qty <= 0:
        return responseData("error", "This product is currently out of stock.", "", 400)

    cart_item = executeGet(
        """
            SELECT order_items_id, quantity
            FROM order_items
            WHERE user_id = %s AND product_id = %s AND status = 1
              AND (reference = '' OR reference IS NULL)
        """,
        (user_id, product_id)
    )
    if isinstance(cart_item, tuple):
        return cart_item

    wishlist_entry_id = wishlist_item[0]['wishlist_id']

    if cart_item:
        new_quantity = int(cart_item[0]['quantity'] or 0) + 1
        update_cart_result = executePost(
            """
            UPDATE order_items
            SET quantity = %s
            WHERE order_items_id = %s
              AND user_id = %s
              AND status = 1
              AND (reference = '' OR reference IS NULL)
            """,
            (new_quantity, cart_item[0]['order_items_id'], user_id)
        )
        if isinstance(update_cart_result, tuple):
            return update_cart_result

        delete_result = executePost("DELETE FROM wishlists WHERE wishlist_id = %s", (wishlist_entry_id,))
        if isinstance(delete_result, tuple):
            return delete_result
    else:
        insert_cart = executePost(
            """
                INSERT INTO order_items (product_id, user_id, quantity, reference, status)
                VALUES (%s, %s, %s, %s, %s)
            """,
            (product_id, user_id, 1, '', 1)
        )
        if isinstance(insert_cart, tuple):
            return insert_cart

        delete_result = executePost("DELETE FROM wishlists WHERE wishlist_id = %s", (wishlist_entry_id,))
        if isinstance(delete_result, tuple):
            return delete_result

    data = {
        "wishlist_count": _get_wishlist_count(user_id),
        "cart_count": _get_cart_count(user_id)
    }
    return responseData("success", "Item moved to cart.", data, 200)

def _get_product_reviews(product_id):
    if not product_id:
        return [], 0, 0.0

    query = """
        SELECT r.review_id,
               r.rating,
               r.comment,
               r.created_at,
               r.seller_response,
               r.moderation_status,
               u.firstname,
               u.lastname,
               COALESCE(
                   (
                       SELECT json_agg(pr.image_path ORDER BY pr.photo_id)
                       FROM product_review_photos pr
                       WHERE pr.review_id = r.review_id
                   ),
                   '[]'::json
               ) AS photo_paths
        FROM product_reviews r
        LEFT JOIN users u ON r.user_id = u.user_id
        WHERE r.product_id = %s
          AND COALESCE(r.moderation_status, 'approved') = 'approved'
        ORDER BY r.created_at DESC
    """
    rows = executeGet(query, (product_id,)) or []
    if isinstance(rows, tuple):
        return [], 0, 0.0

    total_rating = 0
    for row in rows:
        row['reviewer_name'] = f"{row.get('firstname', '')} {row.get('lastname', '')}".strip() or 'Buyer'
        try:
            row['rating'] = int(row.get('rating') or 0)
        except (TypeError, ValueError):
            row['rating'] = 0
        total_rating += row['rating']
        ph = row.get("photo_paths")
        if isinstance(ph, str):
            try:
                ph = json.loads(ph)
            except Exception:
                ph = []
        elif ph is None:
            ph = []
        elif not isinstance(ph, list):
            ph = list(ph) if ph else []
        row["review_photos"] = ph

    count = len(rows)
    avg = (total_rating / count) if count else 0.0
    return rows, count, avg


def _review_spam_score(comment: str) -> float:
    words = re.findall(r"\w+", (comment or "").lower())
    if len(words) < 6:
        return 0.0
    return 1.0 - (len(set(words)) / len(words))


def _buyer_can_review_product(user_id, product_id):
    if not user_id or not product_id:
        return False

    # Buyer can review if they have at least one completed (status 6) order item for this product
    purchase_query = """
        SELECT COUNT(*) AS cnt
        FROM order_items oi
        WHERE oi.user_id = %s
          AND oi.product_id = %s
          AND oi.status = 6
    """
    rows = executeGet(purchase_query, (user_id, product_id)) or []
    if isinstance(rows, tuple) or not rows:
        return False

    if int(rows[0].get('cnt') or 0) <= 0:
        return False

    # Prevent additional reviews when one already exists for this buyer/product pair
    existing_review = executeGet(
        """
        SELECT review_id
        FROM product_reviews
        WHERE user_id = %s AND product_id = %s
        LIMIT 1
        """,
        (user_id, product_id)
    ) or []

    if isinstance(existing_review, tuple):
        return False

    return len(existing_review) == 0


def submitProductReview():
    user_id, auth_error = _ensure_buyer_authenticated()
    if auth_error:
        return auth_error

    product_id = request.form.get('product_id', type=int)
    rating = request.form.get('rating', type=int)
    comment_raw = (request.form.get('comment') or '').strip()
    comment = html.escape(comment_raw)[:8000]

    if not product_id or not rating or rating < 1 or rating > 5:
        return responseData("error", "Invalid review data.", "", 400)

    if not comment_raw:
        return responseData("error", "Please enter a review comment.", "", 400)

    spam_score = _review_spam_score(comment_raw)
    moderation_status = "pending" if spam_score > 0.82 else "approved"

    # Ensure product exists
    product_rows = executeGet("SELECT product_id FROM products WHERE product_id = %s AND status = 1", (product_id,))
    if isinstance(product_rows, tuple):
        return product_rows
    if not product_rows:
        return responseData("error", "Product not found.", "", 404)

    if not _buyer_can_review_product(user_id, product_id):
        return responseData("error", "You can only review products you have completed an order for.", "", 403)

    # Optional: find a completed order item to link
    order_item_row = executeGet(
        """
        SELECT oi.order_items_id, oi.reference
        FROM order_items oi
        WHERE oi.user_id = %s
          AND oi.product_id = %s
          AND oi.status = 6
        ORDER BY oi.order_items_id DESC
        LIMIT 1
        """,
        (user_id, product_id)
    ) or []

    order_items_id = order_item_row[0].get('order_items_id') if order_item_row else None
    reference = order_item_row[0].get('reference') if order_item_row else None

    existing = executeGet(
        """
        SELECT review_id
        FROM product_reviews
        WHERE product_id = %s AND user_id = %s
        LIMIT 1
        """,
        (product_id, user_id)
    ) or []

    if isinstance(existing, tuple):
        return existing

    if existing:
        return responseData("error", "You have already submitted a review for this product.", "", 409)

    insert_query = """
        INSERT INTO product_reviews (product_id, user_id, order_items_id, reference, rating, comment, moderation_status, spam_score)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    ins = executePost(
        insert_query,
        (
            product_id,
            user_id,
            order_items_id,
            reference,
            rating,
            comment,
            moderation_status,
            f"{spam_score:.4f}",
        ),
    )
    if isinstance(ins, tuple):
        insert_query = """
            INSERT INTO product_reviews (product_id, user_id, order_items_id, reference, rating, comment)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        ins = executePost(insert_query, (product_id, user_id, order_items_id, reference, rating, comment))
        moderation_status = "approved"

    review_id = (ins or {}).get("last_inserted_id") if not isinstance(ins, tuple) else None

    if review_id and request.files:
        uploaded = 0
        for f in request.files.getlist("review_photos"):
            if uploaded >= 3:
                break
            rel = save_compressed_proof(f, subdir="review_photos")
            if not rel:
                continue
            photo_ins = executePost(
                "INSERT INTO product_review_photos (review_id, image_path) VALUES (%s, %s)",
                (review_id, rel),
            )
            if not isinstance(photo_ins, tuple):
                uploaded += 1

    reviews, review_count, average_rating = _get_product_reviews(product_id)
    payload = {
        "product_id": product_id,
        "review_count": review_count,
        "average_rating": average_rating,
        "reviews": reviews,
        "moderation_status": moderation_status,
    }
    msg = "Review submitted." if moderation_status == "approved" else "Review received and is pending moderation."
    return responseData("success", msg, payload, 200)


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

    if not user_id:
        return responseData("error", "You must be logged in to manage addresses.", "", 401)

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

    # Determine whether to insert a new record or update the latest one
    existing_query = "SELECT address_id FROM addresses WHERE user_id = %s ORDER BY updated_at DESC LIMIT 1"
    existing_address = executeGet(existing_query, (user_id,))

    params = (floor_unit_number, region, province, city, barangay, street, other_notes, user_id)

    if existing_address:
        update_query = """
            UPDATE addresses
            SET floor_unit_number = %s,
                region = %s,
                province = %s,
                city_municipality = %s,
                barangay = %s,
                street = %s,
                other_notes = %s
            WHERE user_id = %s
        """
        executePost(update_query, params)
        message = "Address updated successfully!"
    else:
        insert_query = """
            INSERT INTO addresses
            (floor_unit_number, region, province, city_municipality, barangay, street, other_notes, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        executePost(insert_query, params)
        message = "Address saved successfully!"

    return responseData("success", message, "", 200)