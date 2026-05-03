from flask import render_template, request, jsonify, session, redirect, url_for, current_app
from helpers.HelperFunction import responseData, hashing, allowed_image_file, generate_random_filename
from helpers.QueryHelpers import executeGet, executePost
from helpers.SupabaseStorage import upload_file_to_supabase, resolve_storage_url
from helpers.Session import setSession, sessionRemove
from helpers.VerificationHelper import (
    generate_otp,
    get_otp_expiry,
    hash_otp,
    verify_otp,
    seconds_until_resend,
    send_email_code,
)
from werkzeug.utils import secure_filename
import os
from datetime import datetime


def _initiate_user_verification(user_id, email, phone):
    email_code = generate_otp()
    email_hash = hash_otp(email_code)
    email_expiry = get_otp_expiry()

    now = datetime.utcnow()

    update_query = """
        UPDATE users
        SET email_code_hash = %s,
            email_code_expires_at = %s,
            email_code_attempts = 0,
            email_code_last_sent_at = %s,
            email_verified = 0
        WHERE user_id = %s
    """
    executePost(
        update_query,
        (email_hash, email_expiry, now, user_id)
    )

    email_sent = send_email_code(email, email_code)
    if not email_sent:
        executePost("UPDATE users SET email_code_last_sent_at = NULL WHERE user_id = %s", (user_id,))

    return {
        "email_sent": email_sent,
    }


def _activate_user_if_verified(user_id):
    activate_query = """
        UPDATE users
        SET status = 1
        WHERE user_id = %s AND email_verified = 1
    """
    executePost(activate_query, (user_id,))


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
    
    # First, check if user exists and get their basic info
    query = """
        SELECT u.*, 
               s.status as seller_status,
               dp.status as rider_status
        FROM users u
        LEFT JOIN seller_details s ON u.user_id = s.user_id
        LEFT JOIN delivery_partners dp ON u.user_id = dp.user_id
        WHERE u.email = %s AND u.password = %s
    """
    user = executeGet(query, (email, hashedValue))
    
    if user:
        user = user[0]
        
        if not user.get('email_verified'):
            return responseData("error", "Please verify your email before logging in.", {
                "email": user['email'],
                "phone": user.get('phone')
            }, 200)
        if user['status'] != 1:
            return responseData("error", "Your account is not active. Please contact support.", None, 200)
            
        # If user is a seller (role_id = 3), check if they're approved
        if user['role_id'] == 3:  # Seller role
            seller_status = user.get('seller_status')
            if seller_status is None:
                return responseData("error", "Seller account not properly set up. Please contact support.", None, 200)
            elif seller_status == 0:  # Pending approval
                return responseData("pending", "Your seller application is under review. We'll notify you once approved.", None, 200)
            elif seller_status == 2:  # Rejected
                return responseData("rejected", "Your seller application has been rejected. Please contact support for more information.", None, 200)
        
        # If user is a rider (role_id = 4), check delivery partner status
        if user['role_id'] == 4:  # Rider role
            rider_status = user.get('rider_status')
            if rider_status is None:
                return responseData("error", "Rider account not properly set up. Please contact support.", None, 200)
            elif rider_status == 0:  # Pending approval
                return responseData("pending", "Your rider application is under review. We'll notify you once approved.", None, 200)
            elif rider_status == 2:  # Rejected
                return responseData("rejected", "Your rider application has been rejected. Please contact support for more information.", None, 200)

        # If we get here, user is either approved or not restricted
        user_detail = {
            'user_id': user['user_id'],
            'role_id': user['role_id'],
            'firstname': user['firstname'],
            'lastname': user['lastname'],
        }

        setSession('authenticated', user_detail)
        return responseData("success", "Login Successful", user, 200)
    else:
        return responseData("error", "Invalid email or password", None, 200)


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
    if password != confirmPassword:
        return responseData("error", "Passwords do not match", "", 200)
    
    select_query = "SELECT email FROM users WHERE email = %s"
    check_email = executeGet(select_query, (email,))
    if check_email:
        return responseData("error", "Email already exist", "", 200)
    else:
        hashed_password = hashing(password)

        insert_query = "INSERT INTO users (firstname, lastname, email, password, phone, role_id, status) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        user_inserted = executePost(insert_query, (fname, lname, email, hashed_password, phone, 2, 1))

        if user_inserted and user_inserted.get('last_inserted_id'):
            verification_status = _initiate_user_verification(user_inserted['last_inserted_id'], email, phone)
            message = "Account created! Please verify your email to activate your account."
            return responseData("success", message, {
                "email": email,
                "email_sent": verification_status['email_sent'],
            }, 200)
        return responseData("error", "Failed to create user account", "", 200)


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


def deliveryPartnerSignup():
    """Public delivery partner signup page - no login required"""
    from controller.HomeController import getCategoriesInHome
    cart_items = session.get('cart', {})
    categories = getCategoriesInHome("WHERE status = 1")
    return render_template('views/deliver.html', cat_data=categories, cart_items=cart_items)


def sellerSignupSubmit():
    """Handle seller signup form submission with file uploads"""
    try:
        # Get form data
        full_name = request.form.get('fullName', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        store_name = request.form.get('storeName', '').strip()
        store_description = request.form.get('storeDescription', '').strip()
        
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
        if not store_description:
            return responseData("error", "Store description is required", "", 200)
        
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
        
        # Save government ID (required)
        if gov_id and gov_id.filename:
            if allowed_image_file(gov_id.filename) or gov_id.filename.lower().endswith('.pdf'):
                uploaded_url, upload_error = upload_file_to_supabase(gov_id, 'seller_documents')
                if upload_error or not uploaded_url:
                    return responseData("error", f"Unable to upload government ID to Supabase storage: {upload_error}", "", 200)
                gov_id_path = uploaded_url
            else:
                return responseData("error", "Invalid government ID file format", "", 200)
        else:
            return responseData("error", "Government ID is required", "", 200)
        
        # Save business permit (optional)
        if business_permit and business_permit.filename:
            if allowed_image_file(business_permit.filename) or business_permit.filename.lower().endswith('.pdf'):
                uploaded_url, upload_error = upload_file_to_supabase(business_permit, 'seller_documents')
                if upload_error or not uploaded_url:
                    return responseData("error", f"Unable to upload business permit to Supabase storage: {upload_error}", "", 200)
                business_permit_path = uploaded_url
        
        # Hash password
        hashed_password = hashing(password)

        # Insert user with role_id = 3 (Buyer/Seller)
        insert_user_query = "INSERT INTO users (firstname, lastname, email, password, phone, role_id, status) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        user_inserted = executePost(insert_user_query, (fname, lname, email, hashed_password, phone, 3, 1))
        
        if user_inserted and user_inserted.get('last_inserted_id'):
            user_id = user_inserted['last_inserted_id']
            
            # Insert seller details with address and documents
            insert_seller_query = """
                INSERT INTO seller_details 
                (user_id, store_name, description, region, province, city, barangay, street, gov_id_path, business_permit_path, status) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
            """
            seller_inserted = executePost(insert_seller_query, (
                user_id, store_name, store_description, region, province, city, barangay, street, 
                gov_id_path, business_permit_path
            ))
            
            if seller_inserted:
                verification_status = _initiate_user_verification(user_id, email, phone)
                message = "Seller application submitted! Please verify your email so we can keep you updated."
                return responseData("success", message, {
                    "email": email,
                    "email_sent": verification_status['email_sent'],
                }, 200)
            else:
                return responseData("error", "Failed to create seller profile", "", 200)
        else:
            return responseData("error", "Failed to create user account", "", 200)
            
    except Exception as e:
        return responseData("error", f"An error occurred: {str(e)}", "", 200)


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

        # Save driver's license (required)
        if drivers_license and drivers_license.filename:
            if allowed_image_file(drivers_license.filename) or drivers_license.filename.lower().endswith('.pdf'):
                uploaded_url, upload_error = upload_file_to_supabase(drivers_license, 'delivery_documents')
                if upload_error or not uploaded_url:
                    return responseData("error", f"Unable to upload driver's license to Supabase storage: {upload_error}", "", 200)
                drivers_license_path = uploaded_url
            else:
                return responseData("error", "Invalid driver's license file format", "", 200)
        else:
            return responseData("error", "Driver's license is required", "", 200)

        # Save government ID (required)
        if gov_id and gov_id.filename:
            if allowed_image_file(gov_id.filename) or gov_id.filename.lower().endswith('.pdf'):
                uploaded_url, upload_error = upload_file_to_supabase(gov_id, 'delivery_documents')
                if upload_error or not uploaded_url:
                    return responseData("error", f"Unable to upload government ID to Supabase storage: {upload_error}", "", 200)
                gov_id_path = uploaded_url
            else:
                return responseData("error", "Invalid government ID file format", "", 200)
        else:
            return responseData("error", "Government ID is required", "", 200)

        # Hash password
        hashed_password = hashing(password)

        # Insert user with role_id = 4 (Rider)
        insert_user_query = "INSERT INTO users (firstname, lastname, email, password, phone, role_id, status) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        user_inserted = executePost(insert_user_query, (fname, lname, email, hashed_password, phone, 4, 1))

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
                verification_status = _initiate_user_verification(user_id, email, phone)
                message = "Application submitted! Please verify your email so we can reach you."
                return responseData("success", message, {
                    "email": email,
                    "email_sent": verification_status['email_sent'],
                }, 200)
            else:
                return responseData("error", "Failed to create delivery partner profile", "", 200)
        else:
            return responseData("error", "Failed to create user account", "", 200)

    except Exception as e:
        return responseData("error", f"An error occurred: {str(e)}", "", 200)


def _format_document_path(path):
    if not path:
        return None

    if isinstance(path, str):
        path = path.strip()
        resolved_url = resolve_storage_url(path)
        if resolved_url:
            return resolved_url

    normalized = path.replace('\\', '/').lstrip('/')
    if normalized.startswith('static/'):
        normalized = normalized[len('static/'):]
    return url_for('static', filename=normalized)


def getDeliveryPartnerDocuments(user_id):
    """Fetch delivery partner documents from database"""
    try:
        query = """
            SELECT drivers_license_path, gov_id_path 
            FROM delivery_partners 
            WHERE user_id = %s
        """
        result = executeGet(query, (user_id,))
        
        if result and len(result) > 0:
            row = result[0]
            documents = []
            
            drivers_license_url = _format_document_path(row['drivers_license_path'])
            if drivers_license_url:
                documents.append({
                    'document_type': 'license',
                    'file_path': drivers_license_url,
                    'file_name': os.path.basename(row['drivers_license_path'].replace('\\', '/'))
                })
            
            gov_id_url = _format_document_path(row['gov_id_path'])
            if gov_id_url:
                documents.append({
                    'document_type': 'gov_id',
                    'file_path': gov_id_url,
                    'file_name': os.path.basename(row['gov_id_path'].replace('\\', '/'))
                })
            
            return responseData("success", "Documents fetched successfully", documents, 200)
        else:
            return responseData("error", "No delivery partner found with this ID", [], 200)
            
    except Exception as e:
        return responseData("error", f"Database error: {str(e)}", [], 200)


def getSellerDocuments(user_id):
    """Fetch seller documents from database"""
    try:
        query = """
            SELECT gov_id_path, business_permit_path 
            FROM seller_details 
            WHERE user_id = %s
        """
        result = executeGet(query, (user_id,))
        
        if result and len(result) > 0:
            row = result[0]
            documents = []
            
            gov_id_url = _format_document_path(row['gov_id_path'])
            if gov_id_url:
                documents.append({
                    'document_type': 'gov_id',
                    'file_path': gov_id_url,
                    'file_name': os.path.basename(row['gov_id_path'].replace('\\', '/'))
                })
            
            permit_url = _format_document_path(row['business_permit_path'])
            if permit_url:
                documents.append({
                    'document_type': 'business_permit',
                    'file_path': permit_url,
                    'file_name': os.path.basename(row['business_permit_path'].replace('\\', '/'))
                })
            
            return responseData("success", "Documents fetched successfully", documents, 200)
        else:
            return responseData("error", "No seller found with this ID", [], 200)
            
    except Exception as e:
        return responseData("error", f"Database error: {str(e)}", [], 200)


def verifyEmailPage():
    email = request.args.get('email', '')
    return render_template('views/verify-email.html', email=email)


def verifyEmailCode():
    email = request.form.get('email', '').strip()
    code = request.form.get('code', '').strip()

    if not email or not code:
        return responseData("error", "Email and code are required", "", 200)

    user = executeGet("""
        SELECT user_id, email_verified, email_code_hash, email_code_expires_at, email_code_attempts
        FROM users
        WHERE email = %s
    """, (email,))

    if not user or not isinstance(user, list):
        return responseData("error", "No account found for that email", "", 200)

    user = user[0]
    if user['email_verified']:
        return responseData("success", "Email is already verified.", "", 200)

    if not user.get('email_code_hash') or not user.get('email_code_expires_at'):
        return responseData("error", "Please request a new email code before verifying.", "", 200)

    if user['email_code_expires_at'] < datetime.utcnow():
        return responseData("error", "Email code has expired. Please request a new one.", "", 200)

    attempts = user.get('email_code_attempts') or 0
    max_attempts = current_app.config.get('OTP_MAX_ATTEMPTS', 3)

    if not verify_otp(code, user['email_code_hash']):
        attempts += 1
        executePost("UPDATE users SET email_code_attempts = %s WHERE user_id = %s", (attempts, user['user_id']))
        if attempts >= max_attempts:
            return responseData("error", "Maximum email code attempts reached. Please resend a new code.", "", 200)
        remaining = max_attempts - attempts
        return responseData("error", f"Invalid email code. You have {remaining} attempt(s) left.", "", 200)

    now = datetime.utcnow()
    executePost("""
        UPDATE users
        SET email_verified = 1,
            email_verified_at = %s,
            email_code_hash = NULL,
            email_code_expires_at = NULL,
            email_code_attempts = 0,
            email_code_last_sent_at = NULL
        WHERE user_id = %s
    """, (now, user['user_id']))
    _activate_user_if_verified(user['user_id'])

    return responseData("success", "Email verification successful!", "", 200)


def resendEmailCode():
    email = request.form.get('email', '').strip()
    if not email:
        return responseData("error", "Email is required", "", 200)

    user = executeGet("""
        SELECT user_id, email_verified, email_code_last_sent_at
        FROM users
        WHERE email = %s
    """, (email,))

    if not user or not isinstance(user, list):
        return responseData("error", "No account found for that email", "", 200)

    user = user[0]
    if user['email_verified']:
        return responseData("success", "Email is already verified.", "", 200)

    cooldown = seconds_until_resend(user.get('email_code_last_sent_at'))
    if cooldown > 0:
        return responseData("error", f"Please wait {cooldown} seconds before requesting another email code.", {"cooldown": cooldown}, 200)

    code = generate_otp()
    code_hash = hash_otp(code)
    expiry = get_otp_expiry()
    now = datetime.utcnow()

    executePost("""
        UPDATE users
        SET email_code_hash = %s,
            email_code_expires_at = %s,
            email_code_attempts = 0,
            email_code_last_sent_at = %s
        WHERE user_id = %s
    """, (code_hash, expiry, now, user['user_id']))

    email_sent = send_email_code(email, code)
    if not email_sent:
        executePost("UPDATE users SET email_code_last_sent_at = NULL WHERE user_id = %s", (user['user_id'],))
        return responseData("error", "Unable to send email code right now. Please try again later.", "", 200)

    return responseData("success", "Email verification code resent successfully.", "", 200)