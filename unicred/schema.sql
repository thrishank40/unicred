-- UniCred Database Schema
-- Run this script to initialize the database

CREATE DATABASE IF NOT EXISTS unicred CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE unicred;

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    roll_number VARCHAR(50) NOT NULL UNIQUE,
    department VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('Student', 'Faculty', 'Admin') DEFAULT 'Student',
    is_verified BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    is_frozen BOOLEAN DEFAULT FALSE,
    trust_score DECIMAL(3,2) DEFAULT 5.00,
    verification_token VARCHAR(255),
    violation_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Credits Table
CREATE TABLE IF NOT EXISTS credits (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    balance DECIMAL(10,2) DEFAULT 100.00,
    locked_credits DECIMAL(10,2) DEFAULT 0.00,
    total_earned DECIMAL(10,2) DEFAULT 0.00,
    total_spent DECIMAL(10,2) DEFAULT 0.00,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Resources Table
CREATE TABLE IF NOT EXISTS resources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    owner_id INT NOT NULL,
    title VARCHAR(200) NOT NULL,
    category ENUM('Electronics', 'Books', 'Sports', 'Tools', 'Clothing', 'Academic', 'Skill', 'Other') DEFAULT 'Other',
    description TEXT,
    quantity INT DEFAULT 1,
    available_from DATE,
    available_until DATE,
    location VARCHAR(200),
    security_deposit DECIMAL(10,2) DEFAULT 0.00,
    credits_per_day DECIMAL(10,2) DEFAULT 0.00,
    status ENUM('Available', 'Borrowed', 'Unavailable') DEFAULT 'Available',
    resource_type ENUM('Resource', 'Skill', 'Knowledge') DEFAULT 'Resource',
    image_path VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Requests Table
CREATE TABLE IF NOT EXISTS requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    resource_id INT NOT NULL,
    borrower_id INT NOT NULL,
    lender_id INT NOT NULL,
    borrow_days INT DEFAULT 1,
    total_credits DECIMAL(10,2),
    status ENUM('Pending', 'Approved', 'Rejected', 'Active', 'Returned', 'Cancelled') DEFAULT 'Pending',
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (resource_id) REFERENCES resources(id) ON DELETE CASCADE,
    FOREIGN KEY (borrower_id) REFERENCES users(id),
    FOREIGN KEY (lender_id) REFERENCES users(id)
);

-- Transactions Table
CREATE TABLE IF NOT EXISTS transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id VARCHAR(64) NOT NULL UNIQUE,
    request_id INT NOT NULL,
    borrower_id INT NOT NULL,
    lender_id INT NOT NULL,
    resource_id INT NOT NULL,
    credits_transferred DECIMAL(10,2),
    security_deposit DECIMAL(10,2),
    status ENUM('Initiated', 'ItemCollected', 'Active', 'Returned', 'Penalized', 'Disputed') DEFAULT 'Initiated',
    due_date DATE,
    collected_at TIMESTAMP NULL,
    returned_at TIMESTAMP NULL,
    qr_hash VARCHAR(64),
    return_qr_hash VARCHAR(64),
    penalty_applied DECIMAL(10,2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (request_id) REFERENCES requests(id),
    FOREIGN KEY (borrower_id) REFERENCES users(id),
    FOREIGN KEY (lender_id) REFERENCES users(id),
    FOREIGN KEY (resource_id) REFERENCES resources(id)
);

-- Ratings Table
CREATE TABLE IF NOT EXISTS ratings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id INT NOT NULL,
    rater_id INT NOT NULL,
    ratee_id INT NOT NULL,
    communication_rating INT CHECK (communication_rating BETWEEN 1 AND 5),
    timeliness_rating INT CHECK (timeliness_rating BETWEEN 1 AND 5),
    condition_rating INT CHECK (condition_rating BETWEEN 1 AND 5),
    overall_rating DECIMAL(3,2),
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id),
    FOREIGN KEY (rater_id) REFERENCES users(id),
    FOREIGN KEY (ratee_id) REFERENCES users(id)
);

-- QR Log Table
CREATE TABLE IF NOT EXISTS qr_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id VARCHAR(64) NOT NULL,
    qr_type ENUM('Collection', 'Return') DEFAULT 'Collection',
    qr_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    used_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Penalty Log Table
CREATE TABLE IF NOT EXISTS penalty_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    transaction_id INT,
    penalty_amount DECIMAL(10,2),
    reason VARCHAR(255),
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
);

-- Badges Table
CREATE TABLE IF NOT EXISTS badges (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(255),
    icon VARCHAR(10),
    criteria_type ENUM('transactions', 'credits_earned', 'trust_score', 'lending_streak') DEFAULT 'transactions',
    criteria_value INT DEFAULT 1
);

-- User Badges Table
CREATE TABLE IF NOT EXISTS user_badges (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    badge_id INT NOT NULL,
    earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (badge_id) REFERENCES badges(id)
);

-- Notifications Table
CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    type ENUM('info', 'success', 'warning', 'danger') DEFAULT 'info',
    is_read BOOLEAN DEFAULT FALSE,
    link VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Fraud Flags Table
CREATE TABLE IF NOT EXISTS fraud_flags (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    flag_type VARCHAR(100),
    details TEXT,
    reviewed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Insert Default Badges
INSERT IGNORE INTO badges (name, description, icon, criteria_type, criteria_value) VALUES
('First Lend', 'Completed your first lending transaction', '🎯', 'transactions', 1),
('Super Lender', 'Completed 10 lending transactions', '⭐', 'transactions', 10),
('Credit Master', 'Earned 500 credits total', '💰', 'credits_earned', 500),
('Trust Champion', 'Maintained 4.5+ trust score with 5+ transactions', '🏆', 'trust_score', 5),
('Community Pillar', 'Completed 25 transactions', '🌟', 'transactions', 25);

-- Insert Default Admin
INSERT IGNORE INTO users (name, email, roll_number, department, password_hash, role, is_verified, is_active)
VALUES ('Admin', 'admin@unicred.edu', 'ADMIN001', 'Administration',
    '$pbkdf2-sha256$29000$admin-placeholder-hash', 'Admin', TRUE, TRUE);
