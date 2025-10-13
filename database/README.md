# Zyntra Database Schema Updates

## Summary of Changes

### New Tables

#### 1. **delivery_partners**
Stores delivery partner applications and information.

**Fields:**
- `partner_id` - Primary key
- `user_id` - Foreign key to users (nullable, linked after approval)
- `full_name` - Partner's full name
- `email` - Unique email address
- `phone` - Contact number
- `vehicle_type` - Type of vehicle (motorcycle, car, bicycle, scooter)
- `plate_number` - Vehicle plate number
- `region`, `province`, `city`, `barangay`, `street` - Complete address
- `drivers_license_path` - Path to uploaded driver's license
- `gov_id_path` - Path to uploaded government ID
- `status` - Application status:
  - `0` = Pending review
  - `1` = Approved
  - `2` = Rejected
  - `3` = Active (delivering)
  - `4` = Inactive

### Updated Tables

#### 2. **seller_details**
Enhanced to support the new seller signup flow.

**New Fields Added:**
- `region` - Seller's region
- `province` - Seller's province
- `city` - Seller's city/municipality
- `barangay` - Seller's barangay
- `street` - Seller's street address
- `gov_id_path` - Path to uploaded government-issued ID
- `business_permit_path` - Path to uploaded business permit (optional)
- `created_at` - Timestamp when seller registered
- `status` - Changed to:
  - `0` = Pending approval
  - `1` = Approved
  - `2` = Rejected

**Modified Fields:**
- `description` - Now nullable (LONGTEXT DEFAULT NULL)
- `store_logo` - Now nullable with default empty string

## Form Data Mapping

### Seller Signup Form → Database

| Form Field | Database Table | Column |
|------------|---------------|--------|
| Full Name | `users` | `firstname` + `lastname` (split) |
| Email | `users` | `email` |
| Phone | `users` | `phone` |
| Password | `users` | `password` (hashed) |
| Store Name | `seller_details` | `store_name` |
| Region | `seller_details` | `region` |
| Province | `seller_details` | `province` |
| City | `seller_details` | `city` |
| Barangay | `seller_details` | `barangay` |
| Street | `seller_details` | `street` |
| Valid ID (file) | `seller_details` | `gov_id_path` |
| Business Permit (file) | `seller_details` | `business_permit_path` |

### Delivery Partner Form → Database

| Form Field | Database Table | Column |
|------------|---------------|--------|
| Full Name | `delivery_partners` | `full_name` |
| Email | `delivery_partners` | `email` |
| Phone | `delivery_partners` | `phone` |
| Vehicle Type | `delivery_partners` | `vehicle_type` |
| Plate Number | `delivery_partners` | `plate_number` |
| Region | `delivery_partners` | `region` |
| Province | `delivery_partners` | `province` |
| City | `delivery_partners` | `city` |
| Barangay | `delivery_partners` | `barangay` |
| Street | `delivery_partners` | `street` |
| Driver's License (file) | `delivery_partners` | `drivers_license_path` |
| Valid ID (file) | `delivery_partners` | `gov_id_path` |

## Implementation Notes

### File Upload Handling
- Create an `uploads/` directory with subdirectories:
  - `uploads/seller_ids/` - For seller government IDs
  - `uploads/business_permits/` - For business permits
  - `uploads/driver_licenses/` - For driver's licenses
  - `uploads/partner_ids/` - For delivery partner IDs

### Workflow

#### Seller Signup:
1. User fills out seller signup form
2. Create user account in `users` table with `role_id = 3` (Buyer/Seller)
3. Upload files and save paths
4. Insert record in `seller_details` with `status = 0` (pending)
5. Admin reviews and approves/rejects
6. Update `status` to `1` (approved) or `2` (rejected)

#### Delivery Partner Signup:
1. Partner fills out delivery form
2. Upload files and save paths
3. Insert record in `delivery_partners` with `status = 0` (pending)
4. `user_id` is NULL initially
5. Admin reviews and approves/rejects
6. Upon approval, optionally create user account and link via `user_id`
7. Update `status` to `1` (approved) or `2` (rejected)
8. When partner goes online: `status = 3` (active)
9. When partner goes offline: `status = 4` (inactive)

## Migration Steps

1. Backup existing database
2. Run `zyntra_updated.sql`
3. Update Python controllers to handle new fields
4. Create file upload directories
5. Test seller and delivery partner signup flows
