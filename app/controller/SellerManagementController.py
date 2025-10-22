from flask import render_template, flash, redirect, url_for, request, jsonify, current_app
from helpers.QueryHelpers import executePost as execute, executeGet
from datetime import datetime

def get_all_sellers():
    """
    Get all sellers with their details
    """
    query = """
    SELECT 
        u.user_id, u.firstname, u.lastname, u.email, u.phone, u.status, u.created_at,
        sd.store_name, sd.city, sd.province
    FROM users u
    LEFT JOIN seller_details sd ON u.user_id = sd.user_id
    WHERE u.role_id = 3  -- Role ID for sellers
    ORDER BY u.status, u.created_at DESC
    """
    return executeGet(query)

def get_pending_sellers():
    """
    Get sellers with pending approval (status = 2)
    """
    query = """
    SELECT 
        u.user_id, u.firstname, u.lastname, u.email, u.phone, u.status, u.created_at,
        sd.store_name, sd.city, sd.province, sd.seller_detail_id
    FROM users u
    JOIN seller_details sd ON u.user_id = sd.user_id
    WHERE u.role_id = 3 AND u.status = 2  -- Status 2 = Pending
    ORDER BY u.created_at DESC
    """
    return executeGet(query)

def get_approved_sellers():
    """
    Get approved sellers (status = 1 or 4)
    """
    query = """
    SELECT 
        u.user_id, u.firstname, u.lastname, u.email, u.phone, u.status, u.created_at,
        sd.store_name, sd.city, sd.province, sd.seller_detail_id
    FROM users u
    LEFT JOIN seller_details sd ON u.user_id = sd.user_id
    WHERE u.role_id = 3 AND u.status IN (1, 4)  -- Status 1 = Active, 4 = Blocked
    ORDER BY 
        CASE WHEN u.status = 1 THEN 0 ELSE 1 END,  -- Active first
        u.created_at DESC
    """
    return executeGet(query)

def update_seller_status(user_id, status, admin_id=None):
    """
    Update seller status
    :param user_id: ID of the seller
    :param status: New status (1=Active, 2=Pending, 3=Rejected, 4=Blocked)
    :param admin_id: ID of admin performing the action (optional)
    """
    query = "UPDATE users SET status = %s WHERE user_id = %s"
    params = (status, user_id)
    
    # Add admin action log if admin_id is provided
    if admin_id:
        log_query = """
        INSERT INTO admin_actions (admin_id, action_type, target_type, target_id, details, created_at)
        VALUES (%s, 'status_update', 'seller', %s, %s, NOW())
        """
        details = f"Updated seller status to {status}"
        execute(log_query, (admin_id, user_id, details))
    
    return execute(query, params)

def delete_seller(user_id, admin_id=None):
    """
    Delete a seller (soft delete)
    """
    # First, check if the user is a seller
    check_query = "SELECT user_id FROM users WHERE user_id = %s AND role_id = 3"
    seller = executeGet(check_query, (user_id,), fetch_one=True)
    
    if not seller:
        return False
    
    # Soft delete by updating status to 0 (inactive)
    query = "UPDATE users SET status = 0 WHERE user_id = %s"
    
    # Log the deletion
    if admin_id:
        log_query = """
        INSERT INTO admin_actions (admin_id, action_type, target_type, target_id, details, created_at)
        VALUES (%s, 'delete', 'seller', %s, 'Seller account deactivated', NOW())
        """
        execute(log_query, (admin_id, user_id))
    
    return execute(query, (user_id,))

def get_seller_details(user_id):
    """
    Get detailed information about a specific seller
    """
    query = """
    SELECT 
        u.*, 
        sd.*,
        (SELECT COUNT(*) FROM products WHERE user_id = u.user_id) as product_count
    FROM users u
    LEFT JOIN seller_details sd ON u.user_id = sd.user_id
    WHERE u.user_id = %s AND u.role_id = 3
    """
    return executeGet(query, (user_id,), fetch_one=True)
