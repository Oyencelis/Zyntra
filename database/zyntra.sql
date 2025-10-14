-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1
-- Generation Time: Oct 14, 2025 at 03:26 PM
-- Server version: 10.4.32-MariaDB
-- PHP Version: 8.2.12

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `zyntra`
--

-- --------------------------------------------------------

--
-- Table structure for table `categories`
--

CREATE TABLE `categories` (
  `category_id` int(10) NOT NULL,
  `category_name` varchar(255) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `status` int(1) DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `categories`
--

INSERT INTO `categories` (`category_id`, `category_name`, `created_at`, `updated_at`, `status`) VALUES
(1, 'Mobile Phones & Accessories', '2025-10-10 13:09:17', '2025-10-10 21:09:17', 1),
(2, 'Laptops, Desktops & Monitors', '2025-10-10 13:09:17', '2025-10-10 21:09:17', 1),
(3, 'Audio & Video Equipment', '2025-10-10 13:09:17', '2025-10-10 21:09:17', 1),
(4, 'Smart Home Devices', '2025-10-10 13:09:17', '2025-10-10 21:09:17', 1),
(5, 'Cameras & Photography', '2025-10-10 13:09:17', '2025-10-10 21:09:17', 1),
(6, 'Wearable Technology', '2025-10-10 13:09:17', '2025-10-10 21:09:17', 1);

-- --------------------------------------------------------

--
-- Table structure for table `delivery_partners`
--

CREATE TABLE `delivery_partners` (
  `partner_id` int(11) NOT NULL,
  `user_id` int(11) DEFAULT NULL,
  `full_name` varchar(255) NOT NULL,
  `email` varchar(255) NOT NULL,
  `phone` varchar(20) NOT NULL,
  `vehicle_type` varchar(50) NOT NULL COMMENT 'motorcycle, car',
  `plate_number` varchar(50) NOT NULL,
  `region` varchar(100) NOT NULL,
  `province` varchar(100) NOT NULL,
  `city` varchar(100) NOT NULL,
  `barangay` varchar(100) NOT NULL,
  `street` varchar(255) NOT NULL,
  `drivers_license_path` varchar(255) NOT NULL,
  `gov_id_path` varchar(255) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `status` int(1) NOT NULL DEFAULT 0 COMMENT '0=pending, 1=approved, 2=rejected, 3=active, 4=inactive'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `delivery_partners`
--

INSERT INTO `delivery_partners` (`partner_id`, `user_id`, `full_name`, `email`, `phone`, `vehicle_type`, `plate_number`, `region`, `province`, `city`, `barangay`, `street`, `drivers_license_path`, `gov_id_path`, `created_at`, `updated_at`, `status`) VALUES
(1, NULL, 'ASD ASD', 'asd@gmail.com', '09876543216', 'car', 'WEC 321', 'Region VIII (Eastern Visayas)', 'Eastern Samar', 'Llorente', 'Barangay 5 (Pob.)', '12', 'static/uploads/delivery_documents\\954826743318621.png', 'static/uploads/delivery_documents\\233030358315315.png', '2025-10-12 06:17:39', '2025-10-12 06:17:39', 0),
(2, 6, 'Arce LC', 'ventre@gmail.com', '09876543217', 'motorcycle', 'WEC 321', 'Region V (Bicol Region)', 'Camarines Sur', 'Canaman', 'San Francisco', '12', 'static/uploads/delivery_documents\\678678243999425.JPG', 'static/uploads/delivery_documents\\564670080972360.png', '2025-10-12 06:25:02', '2025-10-12 06:25:02', 0);

-- --------------------------------------------------------

--
-- Table structure for table `products`
--

CREATE TABLE `products` (
  `product_id` int(11) NOT NULL,
  `user_id` int(11) DEFAULT NULL,
  `category_id` int(10) DEFAULT NULL,
  `product_name` varchar(255) DEFAULT NULL,
  `description` longtext DEFAULT NULL,
  `price` decimal(10,2) DEFAULT NULL,
  `qty` int(10) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `status` int(1) DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `product_attachments`
--

CREATE TABLE `product_attachments` (
  `product_attachment_id` int(10) NOT NULL,
  `product_id` int(10) DEFAULT NULL,
  `attachment` varchar(255) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `status` int(1) DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `roles`
--

CREATE TABLE `roles` (
  `role_id` int(10) NOT NULL,
  `name` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `roles`
--

INSERT INTO `roles` (`role_id`, `name`) VALUES
(1, 'Admin'),
(2, 'Buyer'),
(3, 'Seller'),
(4, 'Rider');

-- --------------------------------------------------------

--
-- Table structure for table `seller_details`
--

CREATE TABLE `seller_details` (
  `seller_detail_id` int(11) NOT NULL,
  `user_id` int(10) NOT NULL,
  `store_name` varchar(255) NOT NULL,
  `description` longtext DEFAULT NULL,
  `region` varchar(100) DEFAULT NULL,
  `province` varchar(100) DEFAULT NULL,
  `city` varchar(100) DEFAULT NULL,
  `barangay` varchar(100) DEFAULT NULL,
  `street` varchar(255) DEFAULT NULL,
  `gov_id_path` varchar(255) DEFAULT NULL,
  `business_permit_path` varchar(255) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `status` int(1) NOT NULL DEFAULT 0 COMMENT '0=pending, 1=approved, 2=rejected'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `seller_details`
--

INSERT INTO `seller_details` (`seller_detail_id`, `user_id`, `store_name`, `description`, `region`, `province`, `city`, `barangay`, `street`, `gov_id_path`, `business_permit_path`, `created_at`, `updated_at`, `status`) VALUES
(1, 5, 'Techonologia', NULL, 'Cordillera Administrative Region (CAR)', 'Ifugao', 'Mayoyao', 'Guinihon', '12', 'static/uploads/seller_documents\\770661652449458.jpg', NULL, '2025-10-10 18:10:13', '2025-10-10 18:10:13', 0),
(2, 7, 'PATheTECH', NULL, 'Region I (Ilocos Region)', 'Pangasinan', 'Bugallon', 'Magtaking', '12', 'static/uploads/seller_documents\\452817055855753.JPG', 'static/uploads/seller_documents\\603101768859766.pdf', '2025-10-12 06:38:23', '2025-10-12 06:38:23', 0);

-- --------------------------------------------------------

--
-- Table structure for table `users`
--

CREATE TABLE `users` (
  `user_id` int(11) NOT NULL,
  `role_id` int(10) DEFAULT 2,
  `firstname` varchar(255) DEFAULT NULL,
  `lastname` varchar(255) DEFAULT NULL,
  `email` varchar(255) NOT NULL,
  `password` varchar(255) NOT NULL,
  `phone` varchar(20) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `status` int(1) DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `users`
--

INSERT INTO `users` (`user_id`, `role_id`, `firstname`, `lastname`, `email`, `password`, `phone`, `created_at`, `updated_at`, `status`) VALUES
(1, 2, 'Lawrence', 'Celis', 'serisuaruse@gmail.com', '96fe0b44f128aa191ed0e7fd7af9f8f37541f96098f9e242f3f042aee465c6c8', '09876543211', '2025-10-10 14:40:42', '2025-10-10 22:40:42', 1),
(2, 2, 'Risu', 'Ame', 'oyencelis@gmail.com', '96fe0b44f128aa191ed0e7fd7af9f8f37541f96098f9e242f3f042aee465c6c8', '09876543212', '2025-10-10 14:45:45', '2025-10-10 22:45:45', 1),
(3, 2, 'Risu', 'Ame', 'potanginanoellenanaman@gmail.com', '96fe0b44f128aa191ed0e7fd7af9f8f37541f96098f9e242f3f042aee465c6c8', '09876543213', '2025-10-10 15:13:39', '2025-10-10 23:13:39', 1),
(4, 2, 'Xarco', 'Batumbakal', 'resu0510@gmail.com', '96fe0b44f128aa191ed0e7fd7af9f8f37541f96098f9e242f3f042aee465c6c8', '09876543214', '2025-10-10 17:00:16', '2025-10-11 01:00:16', 1),
(5, 3, 'Arce', 'LC', 'arcelc@gmail.com', 'ef797c8118f02dfb649607dd5d3f8c7623048c9c063d532cc95c5ed7a898a64f', '09876543215', '2025-10-10 18:10:13', '2025-10-11 02:10:13', 1),
(6, 4, 'Arce', 'LC', 'ventre@gmail.com', 'ef797c8118f02dfb649607dd5d3f8c7623048c9c063d532cc95c5ed7a898a64f', '09876543217', '2025-10-12 06:25:02', '2025-10-12 14:25:02', 1),
(7, 3, 'Lawrence', 'Celis', 'asdfghj@gmail.com', 'ef797c8118f02dfb649607dd5d3f8c7623048c9c063d532cc95c5ed7a898a64f', '09876543218', '2025-10-12 06:38:23', '2025-10-12 14:38:23', 1),
(8, 1, 'Admin', 'Risu', 'admin@gmail.com', '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9', '09876543217', '2025-10-12 14:03:40', '2025-10-12 22:14:28', 1);

--
-- Indexes for dumped tables
--

--
-- Indexes for table `categories`
--
ALTER TABLE `categories`
  ADD PRIMARY KEY (`category_id`);

--
-- Indexes for table `delivery_partners`
--
ALTER TABLE `delivery_partners`
  ADD PRIMARY KEY (`partner_id`),
  ADD UNIQUE KEY `uniq_partner_email` (`email`),
  ADD KEY `delivery_partners_user_id` (`user_id`);

--
-- Indexes for table `products`
--
ALTER TABLE `products`
  ADD PRIMARY KEY (`product_id`),
  ADD KEY `FK_products_category` (`category_id`),
  ADD KEY `FK_products_user` (`user_id`);

--
-- Indexes for table `product_attachments`
--
ALTER TABLE `product_attachments`
  ADD PRIMARY KEY (`product_attachment_id`),
  ADD KEY `FK_product_attachments` (`product_id`);

--
-- Indexes for table `roles`
--
ALTER TABLE `roles`
  ADD PRIMARY KEY (`role_id`);

--
-- Indexes for table `seller_details`
--
ALTER TABLE `seller_details`
  ADD PRIMARY KEY (`seller_detail_id`),
  ADD KEY `seller_details_user_id` (`user_id`);

--
-- Indexes for table `users`
--
ALTER TABLE `users`
  ADD PRIMARY KEY (`user_id`),
  ADD UNIQUE KEY `uniq_users_email` (`email`),
  ADD KEY `FK_users` (`role_id`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `categories`
--
ALTER TABLE `categories`
  MODIFY `category_id` int(10) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=7;

--
-- AUTO_INCREMENT for table `delivery_partners`
--
ALTER TABLE `delivery_partners`
  MODIFY `partner_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=3;

--
-- AUTO_INCREMENT for table `products`
--
ALTER TABLE `products`
  MODIFY `product_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `product_attachments`
--
ALTER TABLE `product_attachments`
  MODIFY `product_attachment_id` int(10) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `roles`
--
ALTER TABLE `roles`
  MODIFY `role_id` int(10) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=5;

--
-- AUTO_INCREMENT for table `seller_details`
--
ALTER TABLE `seller_details`
  MODIFY `seller_detail_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=3;

--
-- AUTO_INCREMENT for table `users`
--
ALTER TABLE `users`
  MODIFY `user_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=9;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `delivery_partners`
--
ALTER TABLE `delivery_partners`
  ADD CONSTRAINT `delivery_partners_user_fk` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL;

--
-- Constraints for table `products`
--
ALTER TABLE `products`
  ADD CONSTRAINT `FK_products_category` FOREIGN KEY (`category_id`) REFERENCES `categories` (`category_id`),
  ADD CONSTRAINT `FK_products_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`);

--
-- Constraints for table `product_attachments`
--
ALTER TABLE `product_attachments`
  ADD CONSTRAINT `FK_product_attachments` FOREIGN KEY (`product_id`) REFERENCES `products` (`product_id`) ON DELETE CASCADE;

--
-- Constraints for table `seller_details`
--
ALTER TABLE `seller_details`
  ADD CONSTRAINT `seller_details_user_fk` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE;

--
-- Constraints for table `users`
--
ALTER TABLE `users`
  ADD CONSTRAINT `FK_users` FOREIGN KEY (`role_id`) REFERENCES `roles` (`role_id`);
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
