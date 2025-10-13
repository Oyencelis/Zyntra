from flask import render_template, request, jsonify, session, redirect, url_for
from helpers.HelperFunction import responseData, hashing, allowed_image_file, generate_random_filename
from helpers.QueryHelpers import executeGet, executePost
from helpers.Session import setSession, sessionRemove
from werkzeug.utils import secure_filename
import os


def login():
    if 'user_id' in session:
        user_role = session.get('role_id')

        if user_role == 1:
            return redirect('/dashboard')
        else:
            return redirect('/') 
    return render_template('views/login.html')

def LoginSubmit():
    email = request.form.get('email')
    password = request.form.get('password')
    hashedValue = hashing(password)
    print(hashedValue)
    query = "SELECT * FROM users WHERE email = %s AND password = %s"
    user = executeGet(query, (email, hashedValue))
    
    if user:
        user = user[0]
        
        if user['status'] == 1:
            user_detail = {
                'user_id': user['user_id'],
                'role_id': user['role_id'],
                'firstname': user['firstname'],
                'lastname': user['lastname'],
            }

            setSession('authenticated', user_detail)
            return responseData("success", "Login Successfully", user, 200)
        else:
            return responseData("error", "Your account is banned. Please contact support.", None, 200)
    else:
        return responseData("error", "Invalid username or password", None, 200)


def signup():
    return render_template('views/signup.html')


def signupSubmit():
    fname = request.form.get('fname')
    lname = request.form.get('lname')
    email = request.form.get('email')
    phone = request.form.get('phone')
    password = request.form.get('password')
    confirmPassword = request.form.get('confirmPassword')

    # Validate all fields
    if fname is None or fname == "":
        return responseData("error", "First name is required", "", 200)
    if lname is None or lname == "":
        return responseData("error", "Last name is required", "", 200)
    if email is None or email == "":
        return responseData("error", "Email is required", "", 200)
    if phone is None or phone == "":
        return responseData("error", "Phone is required", "", 200)
    if password is None or password == "":
        return responseData("error", "Password is required", "", 200)
    if confirmPassword is None or confirmPassword == "":
        return responseData("error", "confirmPassword is required", "", 200)
    
    select_query = "SELECT email FROM users WHERE email = %s"
    check_email = executeGet(select_query, (email,))
    if check_email:
        return responseData("error", "Email already exist", "", 200)
    else:
        hashed_password = hashing(password)

        insert_query = "INSERT INTO users (firstname, lastname, email, password, phone) VALUES (%s, %s, %s, %s, %s)"
        executePost(insert_query, (fname, lname, email, hashed_password, phone))
        return responseData("success", "User registered successfully", "", 200)


def dashboard():
    return render_template('views/dashboard.html')


def logout():
    return redirect(url_for('home_page'))  # Redirect to home or login page


def sellerSignup():
    """Public seller signup page - no login required"""
    from controller.HomeController import getCategoriesInHome
    cart_items = session.get('cart', {})
    categories = getCategoriesInHome("WHERE status = 1")
    return render_template('views/sell.html', cat_data=categories, cart_items=cart_items)


def sellerSignupSubmit():
    """Handle seller signup form submission with file uploads"""
    try:
        # Get form data
        full_name = request.form.get('fullName', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        store_name = request.form.get('storeName', '').strip()
        
        # Address fields
        region = request.form.get('region_text', '').strip()
        province = request.form.get('province_text', '').strip()
        city = request.form.get('city_text', '').strip()
        barangay = request.form.get('barangay_text', '').strip()
        street = request.form.get('street', '').strip()
        
        # Split full name
        name_parts = full_name.split(' ', 1)
        fname = name_parts[0]
        lname = name_parts[1] if len(name_parts) > 1 else ''

        # Validate required fields
        if not full_name:
            return responseData("error", "Full name is required", "", 200)
        if not email:
            return responseData("error", "Email is required", "", 200)
        if not phone:
            return responseData("error", "Phone is required", "", 200)
        if not password:
            return responseData("error", "Password is required", "", 200)
        if not store_name:
            return responseData("error", "Store name is required", "", 200)
        if not region or not province or not city or not barangay:
            return responseData("error", "Complete address is required", "", 200)
        
        # Check if email already exists
        select_query = "SELECT email FROM users WHERE email = %s"
        check_email = executeGet(select_query, (email,))
        if check_email:
            return responseData("error", "Email already exists", "", 200)
        
        # Handle file uploads
        gov_id = request.files.get('govId')
        business_permit = request.files.get('businessPermit')
        
        gov_id_path = None
        business_permit_path = None
        
        # Upload directory
        upload_dir = 'static/uploads/seller_documents'
        os.makedirs(upload_dir, exist_ok=True)
        
        # Save government ID (required)
        if gov_id and gov_id.filename:
            if allowed_image_file(gov_id.filename) or gov_id.filename.endswith('.pdf'):
                file_ext = os.path.splitext(gov_id.filename)[1]
                filename = generate_random_filename(file_ext)
                gov_id_path = os.path.join(upload_dir, filename)
                gov_id.save(gov_id_path)
            else:
                return responseData("error", "Invalid government ID file format", "", 200)
        else:
            return responseData("error", "Government ID is required", "", 200)
        
        # Save business permit (optional)
        if business_permit and business_permit.filename:
            if allowed_image_file(business_permit.filename) or business_permit.filename.endswith('.pdf'):
                file_ext = os.path.splitext(business_permit.filename)[1]
                filename = generate_random_filename(file_ext)
                business_permit_path = os.path.join(upload_dir, filename)
                business_permit.save(business_permit_path)
        
        # Hash password
        hashed_password = hashing(password)

        # Insert user with role_id = 3 (Buyer/Seller)
        insert_user_query = "INSERT INTO users (firstname, lastname, email, password, phone, role_id) VALUES (%s, %s, %s, %s, %s, 3)"
        user_inserted = executePost(insert_user_query, (fname, lname, email, hashed_password, phone))
        
        if user_inserted and user_inserted.get('last_inserted_id'):
            user_id = user_inserted['last_inserted_id']
            
            # Insert seller details with address and documents
            insert_seller_query = """
                INSERT INTO seller_details 
                (user_id, store_name, region, province, city, barangay, street, gov_id_path, business_permit_path, status) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
            """
            seller_inserted = executePost(insert_seller_query, (
                user_id, store_name, region, province, city, barangay, street, 
                gov_id_path, business_permit_path
            ))
            
            if seller_inserted:
                return responseData("success", "Seller application submitted! We'll review and contact you within 48 hours.", "", 200)
            else:
                return responseData("error", "Failed to create seller profile", "", 200)
        else:
            return responseData("error", "Failed to create user account", "", 200)
            
    except Exception as e:
        return responseData("error", f"An error occurred: {str(e)}", "", 200)


def deliveryPartnerSignup():
    """Public delivery partner signup page"""
    from controller.HomeController import getCategoriesInHome
    cart_items = session.get('cart', {})
    categories = getCategoriesInHome("WHERE status = 1")
    return render_template('views/deliver.html', cat_data=categories, cart_items=cart_items)


def deliveryPartnerSignupSubmit():
    """Handle delivery partner signup form submission"""
    try:
        # Get form data
        full_name = request.form.get('fullName', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        vehicle_type = request.form.get('vehicleType', '').strip()
        plate_number = request.form.get('plateNumber', '').strip()

        # Address fields
        region = request.form.get('region_text', '').strip()
        province = request.form.get('province_text', '').strip()
        city = request.form.get('city_text', '').strip()
        barangay = request.form.get('barangay_text', '').strip()
        street = request.form.get('street', '').strip()

        # Split full name
        name_parts = full_name.split(' ', 1)
        fname = name_parts[0]
        lname = name_parts[1] if len(name_parts) > 1 else ''

        # Validate required fields
        if not full_name:
            return responseData("error", "Full name is required", "", 200)
        if not email:
            return responseData("error", "Email is required", "", 200)
        if not phone:
            return responseData("error", "Phone is required", "", 200)
        if not password:
            return responseData("error", "Password is required", "", 200)
        if not vehicle_type:
            return responseData("error", "Vehicle type is required", "", 200)
        if not plate_number:
            return responseData("error", "Plate number is required", "", 200)
        if not region or not province or not city or not barangay:
            return responseData("error", "Complete address is required", "", 200)

        # Check if email already exists in users table
        select_query = "SELECT email FROM users WHERE email = %s"
        check_email = executeGet(select_query, (email,))
        if check_email:
            return responseData("error", "Email already exists", "", 200)

        # Check if email already exists in delivery_partners table
        select_query = "SELECT email FROM delivery_partners WHERE email = %s"
        check_email_partner = executeGet(select_query, (email,))
        if check_email_partner:
            return responseData("error", "Email already registered as delivery partner", "", 200)

        # Handle file uploads
        drivers_license = request.files.get('driversLicense')
        gov_id = request.files.get('govId')

        drivers_license_path = None
        gov_id_path = None

        # Upload directory
        upload_dir = 'static/uploads/delivery_documents'
        os.makedirs(upload_dir, exist_ok=True)

        # Save driver's license (required)
        if drivers_license and drivers_license.filename:
            if allowed_image_file(drivers_license.filename) or drivers_license.filename.endswith('.pdf'):
                file_ext = os.path.splitext(drivers_license.filename)[1]
                filename = generate_random_filename(file_ext)
                drivers_license_path = os.path.join(upload_dir, filename)
                drivers_license.save(drivers_license_path)
            else:
                return responseData("error", "Invalid driver's license file format", "", 200)
        else:
            return responseData("error", "Driver's license is required", "", 200)

        # Save government ID (required)
        if gov_id and gov_id.filename:
            if allowed_image_file(gov_id.filename) or gov_id.filename.endswith('.pdf'):
                file_ext = os.path.splitext(gov_id.filename)[1]
                filename = generate_random_filename(file_ext)
                gov_id_path = os.path.join(upload_dir, filename)
                gov_id.save(gov_id_path)
            else:
                return responseData("error", "Invalid government ID file format", "", 200)
        else:
            return responseData("error", "Government ID is required", "", 200)

        # Hash password
        hashed_password = hashing(password)

        # Insert user with role_id = 4 (Rider)
        insert_user_query = "INSERT INTO users (firstname, lastname, email, password, phone, role_id) VALUES (%s, %s, %s, %s, %s, 4)"
        user_inserted = executePost(insert_user_query, (fname, lname, email, hashed_password, phone))

        if user_inserted and user_inserted.get('last_inserted_id'):
            user_id = user_inserted['last_inserted_id']

            # Insert delivery partner details with user_id link
            insert_query = """
                INSERT INTO delivery_partners
                (user_id, full_name, email, phone, vehicle_type, plate_number, region, province, city, barangay, street,
                 drivers_license_path, gov_id_path, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
            """
            partner_inserted = executePost(insert_query, (
                user_id, full_name, email, phone, vehicle_type, plate_number,
                region, province, city, barangay, street,
                drivers_license_path, gov_id_path
            ))

            if partner_inserted:
                return responseData("success", "Application submitted! We'll review and contact you within 48 hours.", "", 200)
            else:
                return responseData("error", "Failed to create delivery partner profile", "", 200)
        else:
            return responseData("error", "Failed to create user account", "", 200)

    except Exception as e:
        return responseData("error", f"An error occurred: {str(e)}", "", 200)