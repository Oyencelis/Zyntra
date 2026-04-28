from flask import render_template, request, session, g
from helpers.QueryHelpers import executeGet, executePost
from helpers.HelperFunction import responseData

def seller():
    active_menu = ['users', 'seller']
    condition = ""
    sellers_data = getSellers(condition)
    print("\n=== SELLER DATA ===")
    for seller in sellers_data:
        print(f"Seller: {seller.get('firstname')} {seller.get('lastname')} | Status: {seller.get('status')} | Role: {seller.get('role_id')}")
    print("=================\n")
    return render_template('views/users/seller.html', menu=active_menu, sellers_data=sellers_data)

def getSellers(condition, params=None):
    user_id = g.authenticated['user_id']
    query = f"""
        SELECT 
            s.seller_detail_id, 
            s.user_id, 
            s.store_name, 
            s.description, 
            s.status as seller_status, 
            u.status as user_status,
            u.firstname, 
            u.lastname, 
            u.email, 
            u.phone, 
            u.updated_at, 
            u.role_id 
        FROM seller_details s 
        LEFT JOIN users u ON s.user_id = u.user_id 
        {condition} 
        ORDER BY s.updated_at DESC
    """
    results = executeGet(query, params)
    return results


def updateSeller():
    user_id = request.args.get('user_id')
    status_to = request.args.get('status_to')

    try:
        if status_to == "1":  # Approve seller
            executePost("UPDATE seller_details SET status = 1, updated_at = NOW() WHERE user_id = %s", (user_id,))
            executePost("UPDATE users SET role_id = 3, status = 1, updated_at = NOW() WHERE user_id = %s", (user_id,))
            return responseData("success", "Seller approved successfully.", "", 200)
        
        elif status_to == "2":  # Enable seller
            executePost("UPDATE seller_details SET status = 1, updated_at = NOW() WHERE user_id = %s", (user_id,))
            executePost("UPDATE users SET status = 1, updated_at = NOW() WHERE user_id = %s", (user_id,))
            return responseData("success", "Seller enabled successfully.", "", 200)

        elif status_to == "3":  # Disable seller
            executePost("UPDATE seller_details SET status = 2, updated_at = NOW() WHERE user_id = %s", (user_id,))
            executePost("UPDATE users SET status = 2, updated_at = NOW() WHERE user_id = %s", (user_id,))
            return responseData("success", "Seller disabled successfully.", "", 200)
        
        elif status_to == "0":  # Reject seller
            executePost("DELETE FROM seller_details WHERE user_id = %s", (user_id,))
            executePost("UPDATE users SET role_id = 2, status = 1, updated_at = NOW() WHERE user_id = %s", (user_id,))
            return responseData("success", "Seller rejected and removed successfully.", "", 200)

    except Exception as e:
        print("Error in updateSeller:", str(e))
        return responseData("error", str(e), "", 200)

def buyer():
    active_menu = ['users', 'customer']
    condition = ""
    buyer_data = getBuyers(condition)
    return render_template('views/users/customer.html', menu=active_menu, buyer_data=buyer_data)
    
def getBuyers(condition, params=None):
    user_id = g.authenticated['user_id']
    query = f"SELECT * FROM \"users\" WHERE role_id = 2 {condition} ORDER BY updated_at DESC"
    results = executeGet(query, params)
    return results

def updateBuyer():
    user_id = request.args.get('user_id')
    status_to = request.args.get('status_to')

    try:
        if status_to == "1":
            executePost("UPDATE \"users\" SET status = 1 WHERE user_id = %s", (user_id,))
            return responseData("success", "Buyer enabled successfully.", "", 200)
        
        elif status_to == "2":
            executePost("UPDATE \"users\" SET status = 2 WHERE user_id = %s", (user_id,))
            return responseData("success", "Buyer disabled successfully.", "", 200)


    except Exception as e:
        print("Error in updateBuyer:", str(e))
        return responseData("error", str(e), "", 200)
    

def rider():
    active_menu = ['users', 'rider']
    condition = ""
    rider_data = getRiders(condition)
    return render_template('views/users/rider.html', menu=active_menu, rider_data=rider_data)

def getRiders(condition, params=None):
    query = f"""
        SELECT 
            dp.partner_id as rider_detail_id,
            dp.user_id,
            dp.vehicle_type,
            dp.plate_number as license_number,
            CASE
                WHEN dp.status IN (3, 4) THEN 1
                WHEN dp.status IS NULL THEN 0
                ELSE dp.status
            END as rider_status,
            u.firstname,
            u.lastname,
            u.email,
            u.phone,
            u.status as user_status,
            dp.updated_at,
            u.role_id
        FROM delivery_partners dp
        LEFT JOIN users u ON dp.user_id = u.user_id
        {condition}
        ORDER BY dp.updated_at DESC
    """
    results = executeGet(query, params)
    return results

def updateRider():
    user_id = request.values.get('user_id')
    status_to = request.values.get('status_to')

    if not user_id or not status_to:
        return responseData("error", "Missing user_id or status_to", "", 400)

    try:
        if status_to == "1":  # Approve rider
            executePost("UPDATE delivery_partners SET status = 1, updated_at = NOW() WHERE user_id = %s", (user_id,))
            executePost("UPDATE \"users\" SET role_id = 4, status = 1, updated_at = NOW() WHERE user_id = %s", (user_id,))
            return responseData("success", "Rider approved successfully.", "", 200)
        
        elif status_to == "2":  # Enable rider
            executePost("UPDATE delivery_partners SET status = 1, updated_at = NOW() WHERE user_id = %s", (user_id,))
            executePost("UPDATE \"users\" SET status = 1, updated_at = NOW() WHERE user_id = %s", (user_id,))
            return responseData("success", "Rider enabled successfully.", "", 200)

        elif status_to == "3":  # Disable rider
            executePost("UPDATE delivery_partners SET status = 1, updated_at = NOW() WHERE user_id = %s", (user_id,))
            executePost("UPDATE \"users\" SET status = 2, updated_at = NOW() WHERE user_id = %s", (user_id,))
            return responseData("success", "Rider disabled successfully.", "", 200)
        
        elif status_to == "0":  # Reject rider
            executePost("DELETE FROM delivery_partners WHERE user_id = %s", (user_id,))
            executePost("UPDATE \"users\" SET role_id = 2, status = 1, updated_at = NOW() WHERE user_id = %s", (user_id,))
            return responseData("success", "Rider rejected and removed successfully.", "", 200)

        else:
            return responseData("error", "Invalid status provided", "", 400)

    except Exception as e:
        print("Error in updateRider:", str(e))
        return responseData("error", str(e), "", 200)

def getAdmin(condition, params=None):
    user_id = g.authenticated['user_id']
    query = f"SELECT * FROM \"users\" WHERE role_id = 1 {condition} ORDER BY updated_at DESC"
    results = executeGet(query, params)
    return results