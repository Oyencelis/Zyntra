# pyrefly: ignore [missing-import]
from flask import render_template, request, jsonify, session, redirect, url_for, current_app, g
from helpers.HelperFunction import responseData, hashing, allowed_image_file, generate_random_filename
from helpers.QueryHelpers import executeGet, executePost
from helpers.SupabaseAuth import sign_in_with_supabase, sign_up_with_supabase, send_password_reset_email
from helpers.SupabaseStorage import upload_file_to_supabase, resolve_storage_url
from helpers.Session import setSession, sessionRemove
import os
import re
from datetime import datetime


def _supabase_redirect_url():
    configured_url = os.environ.get('SUPABASE_AUTH_REDIRECT_URL')
    if configured_url:
        return configured_url
    try:
        return url_for('login_page', _external=True)
    except Exception:
        return None


def _supabase_public_auth_key():
    return (
        os.environ.get('SUPABASE_ANON_KEY')
        or os.environ.get('SUPABASE_PUBLISHABLE_KEY')
        or ''
    )


def _should_mask_password_reset_error(error_message):
    lowered = (error_message or '').strip().lower()
    if not lowered:
        return False
    return any(fragment in lowered for fragment in (
        'user not found',
        'email not found',
        'no user found',
        'invalid email',
        'for security purposes',
    ))


def _supabase_password_reset_redirect_url():
    configured_url = os.environ.get('SUPABASE_PASSWORD_RESET_REDIRECT_URL')
    if configured_url:
        return configured_url

    base_url = _supabase_redirect_url()
    if base_url:
        separator = '&' if '?' in base_url else '?'
        return f"{base_url}{separator}mode=recovery"

    try:
        return url_for('login_page', mode='recovery', _external=True)
    except Exception:
        return None


def _password_policy_message():
    return 'Password must be at least 8 characters long and include uppercase, lowercase, a number, and a special character.'


def _validate_password_strength(password):
    if password is None or password == '':
        return 'Password is required'
    if len(password) < 8:
        return _password_policy_message()
    if not re.search(r'[A-Z]', password):
        return _password_policy_message()
    if not re.search(r'[a-z]', password):
        return _password_policy_message()
    if not re.search(r'\d', password):
        return _password_policy_message()
    if not re.search(r'[^A-Za-z0-9]', password):
        return _password_policy_message()
    return None


def _auth_user_id(auth_user):
    if not auth_user:
        return None
    return auth_user.get('id') or auth_user.get('user_id')


def _auth_user_confirmed(auth_user):
    if not auth_user:
        return False
    return bool(
        auth_user.get('email_confirmed_at')
        or auth_user.get('confirmed_at')
        or auth_user.get('email_verified_at')
    )


def _get_user_with_status_by_email(email):
    query = """
        SELECT u.*, 
               s.status as seller_status,
               dp.status as rider_status
        FROM users u
        LEFT JOIN seller_details s ON u.user_id = s.user_id
        LEFT JOIN delivery_partners dp ON u.user_id = dp.user_id
        WHERE LOWER(u.email) = LOWER(%s)
        ORDER BY u.user_id ASC
        LIMIT 1
    """
    results = executeGet(query, (email,))
    return results[0] if results else None


def _get_user_with_status_by_auth_or_email(auth_user_id, email):
    if auth_user_id:
        query = """
            SELECT u.*, 
                   s.status as seller_status,
                   dp.status as rider_status
            FROM users u
            LEFT JOIN seller_details s ON u.user_id = s.user_id
            LEFT JOIN delivery_partners dp ON u.user_id = dp.user_id
            WHERE u.auth_user_id = %s OR LOWER(u.email) = LOWER(%s)
            ORDER BY CASE WHEN u.auth_user_id = %s THEN 0 ELSE 1 END, u.user_id ASC
            LIMIT 1
        """
        results = executeGet(query, (auth_user_id, email, auth_user_id))
        return results[0] if results else None
    return _get_user_with_status_by_email(email)


def _sync_public_user_from_auth(email, auth_user=None, role_id=None, firstname=None, lastname=None, phone=None):
    auth_user_id = _auth_user_id(auth_user)
    existing_user = _get_user_with_status_by_auth_or_email(auth_user_id, email)
    email_verified = _auth_user_confirmed(auth_user)
    email_verified_at = datetime.utcnow() if email_verified else None

    if existing_user:
        executePost(
            """
            UPDATE users
            SET auth_user_id = COALESCE(%s, auth_user_id),
                firstname = COALESCE(%s, firstname),
                lastname = COALESCE(%s, lastname),
                phone = COALESCE(%s, phone),
                role_id = COALESCE(%s, role_id),
                email_verified = CASE WHEN %s THEN 1 ELSE email_verified END,
                email_verified_at = CASE WHEN %s THEN COALESCE(email_verified_at, %s) ELSE email_verified_at END
            WHERE user_id = %s
            """,
            (
                auth_user_id,
                firstname,
                lastname,
                phone,
                role_id,
                email_verified,
                email_verified,
                email_verified_at,
                existing_user['user_id'],
            ),
        )
        return _get_user_with_status_by_auth_or_email(auth_user_id, email)

    executePost(
        """
        INSERT INTO users (
            auth_user_id,
            role_id,
            firstname,
            lastname,
            email,
            password,
            phone,
            email_verified,
            email_verified_at,
            status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            auth_user_id,
            role_id or 2,
            firstname,
            lastname,
            email,
            None,
            phone,
            1 if email_verified else 0,
            email_verified_at,
            1,
        ),
    )
    return _get_user_with_status_by_auth_or_email(auth_user_id, email)


def _enforce_account_access(user):
    if not user.get('email_verified'):
        return responseData("error", "Please check your email and confirm your Supabase account before logging in.", None, 200)

    if user['status'] != 1:
        return responseData("error", "Your account is not active. Please contact support.", None, 200)

    if user['role_id'] == 3:
        seller_status = user.get('seller_status')
        if seller_status is None:
            return responseData("error", "Seller account not properly set up. Please contact support.", None, 200)
        if seller_status == 0:
            return responseData("pending", "Your seller application is under review. We'll notify you once approved.", None, 200)
        if seller_status == 2:
            return responseData("rejected", "Your seller application has been rejected. Please contact support for more information.", None, 200)

    if user['role_id'] == 4:
        rider_status = user.get('rider_status')
        if rider_status is None:
            return responseData("error", "Rider account not properly set up. Please contact support.", None, 200)
        if rider_status == 0:
            return responseData("pending", "Your rider application is under review. We'll notify you once approved.", None, 200)
        if rider_status == 2:
            return responseData("rejected", "Your rider application has been rejected. Please contact support for more information.", None, 200)

    return None


def _set_authenticated_session(user):
    user_detail = {
        'user_id': user['user_id'],
        'role_id': user['role_id'],
        'firstname': user['firstname'],
        'lastname': user['lastname'],
    }
    setSession('authenticated', user_detail)


def login():
    if 'user_id' in session:
        user_role = session.get('role_id')

        if user_role == 1:
            return redirect('/dashboard')
        else:
            return redirect('/')
    return render_template(
        'views/login.html',
        recovery_mode=(request.args.get('mode') == 'recovery'),
        supabase_project_url=os.environ.get('SUPABASE_PROJECT_URL', ''),
        supabase_public_key=_supabase_public_auth_key(),
    )


def LoginSubmit():
    email = request.form.get('email')
    password = request.form.get('password')
    if not email or not password:
        return responseData("error", "Email and password are required.", None, 200)

    user = _get_user_with_status_by_email(email)
    auth_user = None
    auth_error = None

    if user and user.get('auth_user_id'):
        auth_user, auth_error = sign_in_with_supabase(email, password)
        if auth_error:
            return responseData("error", auth_error, None, 200)
        user = _sync_public_user_from_auth(
            email,
            auth_user=auth_user,
            role_id=user.get('role_id'),
            firstname=user.get('firstname'),
            lastname=user.get('lastname'),
            phone=user.get('phone'),
        )
    elif user:
        auth_user, auth_error = sign_in_with_supabase(email, password)
        if auth_user:
            user = _sync_public_user_from_auth(
                email,
                auth_user=auth_user,
                role_id=user.get('role_id'),
                firstname=user.get('firstname'),
                lastname=user.get('lastname'),
                phone=user.get('phone'),
            )
        else:
            if auth_error and auth_error != 'Invalid email or password.':
                return responseData("error", auth_error, None, 200)
            hashed_value = hashing(password)
            if user.get('password') != hashed_value:
                return responseData("error", "Invalid email or password", None, 200)
    else:
        auth_user, auth_error = sign_in_with_supabase(email, password)
        if auth_error:
            return responseData("error", auth_error, None, 200)
        user = _sync_public_user_from_auth(email, auth_user=auth_user)

    if not user:
        return responseData("error", "Unable to load your account. Please contact support.", None, 200)

    access_error = _enforce_account_access(user)
    if access_error:
        return access_error

    _set_authenticated_session(user)
    return responseData("success", "Login Successful", user, 200)


def forgotPasswordSubmit():
    email = (request.form.get('email') or '').strip()
    if not email:
        return responseData("error", "Email is required.", None, 200)

    reset_error = send_password_reset_email(
        email,
        redirect_url=_supabase_password_reset_redirect_url(),
    )

    if reset_error:
        if _should_mask_password_reset_error(reset_error):
            return responseData(
                "success",
                "If that email is registered, a secure password reset link has been sent. Please check your inbox.",
                {"email": email},
                200,
            )
        return responseData("error", reset_error, None, 200)

    return responseData(
        "success",
        "If that email is registered, a secure password reset link has been sent. Please check your inbox.",
        {"email": email},
        200,
    )


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
    password_error = _validate_password_strength(password)
    if password_error:
        return responseData("error", password_error, "", 200)
    if password != confirmPassword:
        return responseData("error", "Passwords do not match", "", 200)
    
    select_query = "SELECT email FROM users WHERE LOWER(email) = LOWER(%s)"
    check_email = executeGet(select_query, (email,))
    if check_email:
        return responseData("error", "Email already exist", "", 200)

    auth_user, auth_error = sign_up_with_supabase(
        email,
        password,
        metadata={
            'first_name': fname,
            'last_name': lname,
            'phone': phone,
        },
        redirect_url=_supabase_redirect_url(),
    )
    if auth_error:
        return responseData("error", auth_error, "", 200)

    _sync_public_user_from_auth(
        email,
        auth_user=auth_user,
        role_id=2,
        firstname=fname,
        lastname=lname,
        phone=phone,
    )
    return responseData(
        "success",
        "Account created! Please check your email for the Supabase confirmation link before logging in.",
        {"email": email},
        200,
    )


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
        confirm_password = request.form.get('confirmPassword', '')
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
        password_error = _validate_password_strength(password)
        if password_error:
            return responseData("error", password_error, "", 200)
        if password != confirm_password:
            return responseData("error", "Passwords do not match", "", 200)
        if not store_name:
            return responseData("error", "Store name is required", "", 200)
        if not region or not province or not city or not barangay:
            return responseData("error", "Complete address is required", "", 200)
        if not store_description:
            return responseData("error", "Store description is required", "", 200)
        
        # Check if email already exists
        select_query = "SELECT email FROM users WHERE LOWER(email) = LOWER(%s)"
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
        
        auth_user, auth_error = sign_up_with_supabase(
            email,
            password,
            metadata={
                'first_name': fname,
                'last_name': lname,
                'phone': phone,
            },
            redirect_url=_supabase_redirect_url(),
        )
        if auth_error:
            return responseData("error", auth_error, "", 200)

        public_user = _sync_public_user_from_auth(
            email,
            auth_user=auth_user,
            role_id=3,
            firstname=fname,
            lastname=lname,
            phone=phone,
        )
        if not public_user:
            return responseData("error", "Unable to prepare your seller account. Please contact support.", "", 200)

        insert_seller_query = """
            INSERT INTO seller_details 
            (user_id, store_name, description, region, province, city, barangay, street, gov_id_path, business_permit_path, status) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
        """
        seller_inserted = executePost(insert_seller_query, (
            public_user['user_id'], store_name, store_description, region, province, city, barangay, street, 
            gov_id_path, business_permit_path
        ))
        
        if seller_inserted:
            message = "Seller application submitted! Please check your email and confirm your Supabase account. After confirmation, you can log in while your seller application stays under review."
            return responseData("success", message, {"email": email}, 200)
        return responseData("error", "Failed to create seller profile", "", 200)
            
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
        confirm_password = request.form.get('confirmPassword', '')
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
        password_error = _validate_password_strength(password)
        if password_error:
            return responseData("error", password_error, "", 200)
        if password != confirm_password:
            return responseData("error", "Passwords do not match", "", 200)
        if not vehicle_type:
            return responseData("error", "Vehicle type is required", "", 200)
        if not plate_number:
            return responseData("error", "Plate number is required", "", 200)
        if not region or not province or not city or not barangay:
            return responseData("error", "Complete address is required", "", 200)

        # Check if email already exists in users table
        select_query = "SELECT email FROM users WHERE LOWER(email) = LOWER(%s)"
        check_email = executeGet(select_query, (email,))
        if check_email:
            return responseData("error", "Email already exists", "", 200)

        # Check if email already exists in delivery_partners table
        select_query = "SELECT email FROM delivery_partners WHERE LOWER(email) = LOWER(%s)"
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

        auth_user, auth_error = sign_up_with_supabase(
            email,
            password,
            metadata={
                'first_name': fname,
                'last_name': lname,
                'phone': phone,
            },
            redirect_url=_supabase_redirect_url(),
        )
        if auth_error:
            return responseData("error", auth_error, "", 200)

        public_user = _sync_public_user_from_auth(
            email,
            auth_user=auth_user,
            role_id=4,
            firstname=fname,
            lastname=lname,
            phone=phone,
        )
        if not public_user:
            return responseData("error", "Unable to prepare your rider account. Please contact support.", "", 200)

        insert_query = """
            INSERT INTO delivery_partners
            (user_id, full_name, email, phone, vehicle_type, plate_number, region, province, city, barangay, street,
             drivers_license_path, gov_id_path, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
        """
        partner_inserted = executePost(insert_query, (
            public_user['user_id'], full_name, email, phone, vehicle_type, plate_number,
            region, province, city, barangay, street,
            drivers_license_path, gov_id_path
        ))

        if partner_inserted:
            message = "Application submitted! Please check your email and confirm your Supabase account. After confirmation, you can log in while your rider application stays under review."
            return responseData("success", message, {"email": email}, 200)
        return responseData("error", "Failed to create delivery partner profile", "", 200)

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


def _require_admin_for_sensitive_api():
    auth = getattr(g, 'authenticated', None) or {}
    if auth.get('role_id') != 1:
        return responseData("error", "Unauthorized", [], 403)
    return None


def getDeliveryPartnerDocuments(user_id):
    """Fetch delivery partner documents from database"""
    auth_error = _require_admin_for_sensitive_api()
    if auth_error:
        return auth_error
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
    auth_error = _require_admin_for_sensitive_api()
    if auth_error:
        return auth_error
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
    return redirect(url_for('login_page'))


def verifyEmailCode():
    return responseData("error", "Email verification is now handled by Supabase. Please check your email for the confirmation link.", "", 200)


def resendEmailCode():
    return responseData("error", "Email verification emails are now sent by Supabase. Please use the original confirmation email or resend it from Supabase if needed.", "", 200)
