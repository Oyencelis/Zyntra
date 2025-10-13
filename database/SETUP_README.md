# Zyntra Database Setup

## Quick Start

1. **Run the SQL script** in MySQL Workbench or phpMyAdmin:
   ```sql
   -- Copy and paste the entire contents of zyntra_updated.sql
   ```

2. **Or run it from command line:**
   ```bash
   mysql -u root -p < zyntra_updated.sql
   ```

## Database Structure

### Tables Created:
- `roles` - User roles (Admin, Buyer, Seller, Rider)
- `users` - All user accounts (login here)
- `categories` - Product categories
- `products` - Marketplace products
- `product_attachments` - Product images
- `seller_details` - Seller applications
- `delivery_partners` - Rider applications

## User Flow

1. **Public browsing** - No login required
2. **Signup as:**
   - Buyer (`/signup`) - Role ID 2
   - Seller (`/sell`) - Role ID 3 + seller_details record
   - Rider (`/deliver`) - Role ID 4 + delivery_partners record
3. **Login** - One login page for all user types
4. **Role-based redirection** after login

## Features

✅ **Public viewing** - Browse products without login
✅ **3 signup types** - Separate flows for each user type
✅ **Unified login** - Single login page for all users
✅ **Role-based access** - Different dashboards per role
✅ **Clean schema** - Simplified structure matching your code

## Next Steps

1. Run the SQL script to create database
2. Test signup flows (buyer, seller, rider)
3. Test login and role-based redirection
4. Start adding products and testing marketplace features
