from flask import render_template, request, session, g
from helpers.QueryHelpers import executeGet, executePost
from helpers.HelperFunction import responseData

def seller():
    active_menu = ['users', 'seller']
    condition = ""
    sellers_data = getSellers(condition)
    return render_template('views/users/seller.html', menu=active_menu, sellers_data=sellers_data)

def getSellers(condition, params=None):
    user_id = g.authenticated['user_id']
    query = f"SELECT s.seller_detail_id, s.user_id, s.store_name, s.description, s.status, u.firstname, u.lastname, u.email, u.phone, u.updated_at, u.role_id FROM seller_details s LEFT JOIN users u ON s.user_id = u.user_id {condition} ORDER BY updated_at DESC"
    results = executeGet(query, params)
    return results


def updateSeller():
    user_id = request.args.get('user_id')
    status_to = request.args.get('status_to')

    try:
        if status_to == "1":
            executePost("UPDATE seller_details SET status = 2 WHERE user_id = %s", (user_id,))
            executePost("UPDATE users SET role_id = 3 WHERE user_id = %s", (user_id,))
            return responseData("success", "Seller approved successfully.", "", 200)
        
        elif status_to == "2":
            executePost("UPDATE seller_details SET status = 2 WHERE user_id = %s", (user_id,))
            executePost("UPDATE users SET role_id = 3 WHERE user_id = %s", (user_id,))
            return responseData("success", "Seller enabled successfully.", "", 200)

        elif status_to == "3":
            executePost("UPDATE seller_details SET status = 3 WHERE user_id = %s", (user_id,))
            executePost("UPDATE users SET role_id = 2 WHERE user_id = %s", (user_id,))
            return responseData("success", "Seller disabled successfully.", "", 200)
        
        elif status_to == "0":
            executePost("DELETE FROM seller_details WHERE user_id = %s", (user_id,))
            executePost("UPDATE users SET role_id = 2 WHERE user_id = %s", (user_id,))
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
    query = f"SELECT * FROM `users` WHERE role_id = 2 {condition} ORDER BY updated_at DESC"
    results = executeGet(query, params)
    return results

def updateBuyer():
    user_id = request.args.get('user_id')
    status_to = request.args.get('status_to')

    try:
        if status_to == "1":
            executePost("UPDATE users SET status = 1 WHERE user_id = %s", (user_id,))
            return responseData("success", "Buyer enabled successfully.", "", 200)
        
        elif status_to == "2":
            executePost("UPDATE users SET status = 2 WHERE user_id = %s", (user_id,))
            return responseData("success", "Buyer disabled successfully.", "", 200)


    except Exception as e:
        print("Error in updateBuyer:", str(e))
        return responseData("error", str(e), "", 200)
    

def getAdmin(condition, params=None):
    user_id = g.authenticated['user_id']
    query = f"SELECT * FROM `users` WHERE role_id = 1 {condition} ORDER BY updated_at DESC"
    results = executeGet(query, params)
    return results