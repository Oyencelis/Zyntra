# pyrefly: ignore [missing-import]
from flask import render_template, session, request, g
from helpers.HelperFunction import responseData
from helpers.QueryHelpers import executePost, executeGet
from controller.HomeController import resolve_location_name
from datetime import datetime

def _format_join_date(value):
    if not value:
        return None
    try:
        if isinstance(value, str):
            value = value.split('.')[0]
            date_obj = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        else:
            date_obj = value
        return date_obj.strftime("%B %d, %Y")
    except Exception:
        return None

def _build_address_context(user_id):
    address_query = """
        SELECT floor_unit_number, region, province, city_municipality, barangay, street, other_notes
        FROM addresses
        WHERE user_id = %s
        ORDER BY updated_at DESC
        LIMIT 1
    """
    address_result = executeGet(address_query, (user_id,))
    user_address = address_result[0] if isinstance(address_result, list) and address_result else None

    formatted_address = None
    address_texts = {}

    if user_address:
        region_display = resolve_location_name(user_address.get('region'), 'region.json', 'region_code', 'region_name') or user_address.get('region')
        province_display = resolve_location_name(user_address.get('province'), 'province.json', 'province_code', 'province_name') or user_address.get('province')
        city_display = resolve_location_name(user_address.get('city_municipality'), 'city.json', 'city_code', 'city_name') or user_address.get('city_municipality')
        barangay_display = resolve_location_name(user_address.get('barangay'), 'barangay.json', 'brgy_code', 'brgy_name') or user_address.get('barangay')

        address_components = [
            user_address.get('floor_unit_number'),
            user_address.get('street'),
            barangay_display,
            city_display,
            province_display,
            region_display
        ]
        formatted_address = ", ".join([component for component in address_components if component])
        address_texts = {
            'region': region_display,
            'province': province_display,
            'city': city_display,
            'barangay': barangay_display
        }

    return {
        'user_address': user_address,
        'formatted_address': formatted_address,
        'address_texts': address_texts
    }

def _get_basic_profile(user_id):
    profile_query = """
        SELECT user_id, firstname, lastname, email, phone, created_at
        FROM users
        WHERE user_id = %s
        LIMIT 1
    """
    result = executeGet(profile_query, (user_id,))
    return result[0] if isinstance(result, list) and result else {}

def profileOverview():
    user_id = g.authenticated.get('user_id') if g.authenticated else None
    profile_data = {}
    join_date = None

    if user_id:
        profile_query = """
            SELECT user_id, firstname, lastname, email, phone, created_at
            FROM users
            WHERE user_id = %s
            LIMIT 1
        """
        profile_result = executeGet(profile_query, (user_id,))
        if isinstance(profile_result, list) and profile_result:
            profile_data = profile_result[0]
            join_date = _format_join_date(profile_data.get('created_at'))

    address_context = _build_address_context(user_id) if user_id else {
        'user_address': None,
        'formatted_address': None,
        'address_texts': {}
    }

    return render_template(
        'views/profile/profile_overview.html',
        profile=profile_data,
        join_date=join_date,
        **address_context
    )

def manageProfile():
    if not g.authenticated:
        return render_template('views/manage-profile/manageProfile.html', menu=['manage'])

    user_id = g.authenticated.get('user_id')
    role_id = g.authenticated.get('role_id')

    profile_data = _get_basic_profile(user_id) if user_id else {}
    join_date = _format_join_date(profile_data.get('created_at')) if profile_data else None
    address_context = _build_address_context(user_id) if user_id else {
        'user_address': None,
        'formatted_address': None,
        'address_texts': {}
    }

    seller_details = None
    rider_details = None

    if role_id == 3 and user_id:
        seller_query = """
            SELECT store_name, description, region, province, city, barangay, street,
                   gov_id_path, business_permit_path, status, updated_at
            FROM seller_details
            WHERE user_id = %s
            ORDER BY updated_at DESC
            LIMIT 1
        """
        seller_rows = executeGet(seller_query, (user_id,))
        seller_details = seller_rows[0] if isinstance(seller_rows, list) and seller_rows else None
    elif role_id == 4 and user_id:
        rider_query = """
            SELECT vehicle_type, plate_number, region, province, city, barangay, street,
                   drivers_license_path, gov_id_path, status, updated_at
            FROM delivery_partners
            WHERE user_id = %s
            ORDER BY updated_at DESC
            LIMIT 1
        """
        rider_rows = executeGet(rider_query, (user_id,))
        rider_details = rider_rows[0] if isinstance(rider_rows, list) and rider_rows else None

    active_menu = ['manage']
    return render_template(
        'views/manage-profile/manageProfile.html',
        menu=active_menu,
        profile=profile_data,
        join_date=join_date,
        seller_details=seller_details,
        rider_details=rider_details,
        **address_context
    )

def sellerRequest():
    user_id = g.authenticated['user_id']
    query = "SELECT user_id FROM seller_details WHERE user_id = %s"
    result = executeGet(query, (user_id,))
    if result:
        sellerRequestSubmit = True
    else:
        sellerRequestSubmit = False
    session['sellerRequestSubmit'] = sellerRequestSubmit

    return render_template('views/become-seller.html', sellerRequestSubmit=sellerRequestSubmit)


def sellerRequestSubmit():
    store_name = request.form.get('storeName')
    business_description = request.form.get('businessDescription')

    if not store_name:
        return responseData("error", "Store name is required", "", 200)
    if not business_description:
        return responseData("error", "Description is required", "", 200)
    
    insert_query = "INSERT INTO seller_details (user_id, store_name, description) VALUES (%s, %s, %s)"
    
    # Execute the insertion and check if it was successful
    if executePost(insert_query, (g.authenticated['user_id'], store_name, business_description)):
        return responseData("success", "Your request to become a seller has been submitted, please wait for approval.", "", 200)
    else:
        return responseData("error", "Failed to insert your request into the database.", "", 200)


def updateProfileInfo():
    if not g.authenticated:
        return responseData("error", "You must be logged in to update your profile.", "", 401)

    user_id = g.authenticated.get('user_id')
    firstname = request.form.get('firstname', '').strip()
    lastname = request.form.get('lastname', '').strip()
    phone = request.form.get('phone', '').strip() or None

    if not firstname or not lastname:
        return responseData("error", "First name and last name are required.", "", 200)

    update_query = """
        UPDATE users
        SET firstname = %s,
            lastname = %s,
            phone = %s,
            updated_at = NOW()
        WHERE user_id = %s
    """

    result = executePost(update_query, (firstname, lastname, phone, user_id))
    if isinstance(result, dict) and result.get('rowcount'):
        g.authenticated['firstname'] = firstname
        g.authenticated['lastname'] = lastname
        return responseData("success", "Profile updated successfully!", "", 200)

    return responseData("error", "Unable to update profile. Please try again.", "", 200)