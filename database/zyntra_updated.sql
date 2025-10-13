-- Zyntra Database Schema
-- Clean, simplified schema for marketplace application

-- Create fresh database and use it
DROP DATABASE IF EXISTS `zyntra`;
CREATE DATABASE `zyntra` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
USE `zyntra`;

-- Disable FK checks during creation
SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;

-- Roles table (matches code expectations)
CREATE TABLE `roles` (
  `role_id` INT(10) NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(255) DEFAULT NULL,
  PRIMARY KEY (`role_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO `roles` (`role_id`, `name`) VALUES
(1, 'Admin'),
(2, 'Buyer'),
(3, 'Seller'),
(4, 'Rider');

ALTER TABLE `roles` AUTO_INCREMENT=5;

-- Users table (all user types login here)
CREATE TABLE `users` (
  `user_id` INT(11) NOT NULL AUTO_INCREMENT,
  `role_id` INT(10) DEFAULT 2,
  `firstname` VARCHAR(255) DEFAULT NULL,
  `lastname` VARCHAR(255) DEFAULT NULL,
  `email` VARCHAR(255) NOT NULL,
  `password` VARCHAR(255) NOT NULL,
  `phone` VARCHAR(20) DEFAULT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `status` INT(1) DEFAULT 1,
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `uniq_users_email` (`email`),
  KEY `FK_users` (`role_id`),
  CONSTRAINT `FK_users` FOREIGN KEY (`role_id`) REFERENCES `roles` (`role_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Categories table
CREATE TABLE `categories` (
  `category_id` INT(10) NOT NULL AUTO_INCREMENT,
  `category_name` VARCHAR(255) DEFAULT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `status` INT(1) DEFAULT 1,
  PRIMARY KEY (`category_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Products table
CREATE TABLE `products` (
  `product_id` INT(11) NOT NULL AUTO_INCREMENT,
  `user_id` INT(11) DEFAULT NULL,
  `category_id` INT(10) DEFAULT NULL,
  `product_name` VARCHAR(255) DEFAULT NULL,
  `description` LONGTEXT DEFAULT NULL,
  `price` DECIMAL(10,2) DEFAULT NULL,
  `qty` INT(10) DEFAULT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `status` INT(1) DEFAULT 1,
  PRIMARY KEY (`product_id`),
  KEY `FK_products_category` (`category_id`),
  KEY `FK_products_user` (`user_id`),
  CONSTRAINT `FK_products_category` FOREIGN KEY (`category_id`) REFERENCES `categories` (`category_id`),
  CONSTRAINT `FK_products_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Product attachments table
CREATE TABLE `product_attachments` (
  `product_attachment_id` INT(10) NOT NULL AUTO_INCREMENT,
  `product_id` INT(10) DEFAULT NULL,
  `attachment` VARCHAR(255) DEFAULT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `status` INT(1) DEFAULT 1,
  PRIMARY KEY (`product_attachment_id`),
  KEY `FK_product_attachments` (`product_id`),
  CONSTRAINT `FK_product_attachments` FOREIGN KEY (`product_id`) REFERENCES `products` (`product_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Seller details table (for seller applications)
CREATE TABLE `seller_details` (
  `seller_detail_id` INT(11) NOT NULL AUTO_INCREMENT,
  `user_id` INT(10) NOT NULL,
  `store_name` VARCHAR(255) NOT NULL,
  `description` LONGTEXT DEFAULT NULL,
  `region` VARCHAR(100) DEFAULT NULL,
  `province` VARCHAR(100) DEFAULT NULL,
  `city` VARCHAR(100) DEFAULT NULL,
  `barangay` VARCHAR(100) DEFAULT NULL,
  `street` VARCHAR(255) DEFAULT NULL,
  `gov_id_path` VARCHAR(255) DEFAULT NULL,
  `business_permit_path` VARCHAR(255) DEFAULT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `status` INT(1) NOT NULL DEFAULT 0 COMMENT '0=pending, 1=approved, 2=rejected',
  PRIMARY KEY (`seller_detail_id`),
  KEY `seller_details_user_id` (`user_id`),
  CONSTRAINT `seller_details_user_fk` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Delivery partners table (for rider applications)
CREATE TABLE `delivery_partners` (
  `partner_id` INT(11) NOT NULL AUTO_INCREMENT,
  `user_id` INT(11) DEFAULT NULL,
  `full_name` VARCHAR(255) NOT NULL,
  `email` VARCHAR(255) NOT NULL,
  `phone` VARCHAR(20) NOT NULL,
  `vehicle_type` VARCHAR(50) NOT NULL COMMENT 'motorcycle, car',
  `plate_number` VARCHAR(50) NOT NULL,
  `region` VARCHAR(100) NOT NULL,
  `province` VARCHAR(100) NOT NULL,
  `city` VARCHAR(100) NOT NULL,
  `barangay` VARCHAR(100) NOT NULL,
  `street` VARCHAR(255) NOT NULL,
  `drivers_license_path` VARCHAR(255) NOT NULL,
  `gov_id_path` VARCHAR(255) NOT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `status` INT(1) NOT NULL DEFAULT 0 COMMENT '0=pending, 1=approved, 2=rejected, 3=active, 4=inactive',
  PRIMARY KEY (`partner_id`),
  UNIQUE KEY `uniq_partner_email` (`email`),
  KEY `delivery_partners_user_id` (`user_id`),
  CONSTRAINT `delivery_partners_user_fk` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Seed categories (active status for public viewing)
INSERT INTO `categories` (`category_name`, `status`) VALUES
('Mobile Phones & Accessories', 1),
('Laptops, Desktops & Monitors', 1),
('Audio & Video Equipment', 1),
('Smart Home Devices', 1),
('Cameras & Photography', 1),
('Wearable Technology', 1);

-- Re-enable FK/unique checks
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;
