-- ============================================================
--  UniCred — Request System Migration
--  Run this ONCE against your unicred database:
--    mysql -u root -p unicred < migrations/add_request_system.sql
-- ============================================================

USE unicred;

-- ── 1. Resource Requests ──────────────────────────────────
CREATE TABLE IF NOT EXISTS resource_requests (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT          NOT NULL,
    title           VARCHAR(200) NOT NULL,
    category        ENUM('Electronics','Books','Sports','Tools','Clothing','Academic','Skill','Other') DEFAULT 'Other',
    description     TEXT,
    location        VARCHAR(200),
    duration_days   INT          DEFAULT 1,
    credits_offered DECIMAL(10,2) DEFAULT 0.00,
    status          ENUM('Open','Accepted','Completed','Cancelled') DEFAULT 'Open',
    accepted_by     INT          NULL,
    transaction_id  INT          NULL,          -- set when completed → links to transactions.id
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id)     REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (accepted_by) REFERENCES users(id) ON DELETE SET NULL
);

-- ── 2. Knowledge Requests ─────────────────────────────────
CREATE TABLE IF NOT EXISTS knowledge_requests (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT          NOT NULL,
    subject         VARCHAR(150) NOT NULL,
    topic           VARCHAR(200) NOT NULL,
    description     TEXT,
    credits_offered DECIMAL(10,2) DEFAULT 0.00,
    status          ENUM('Open','Accepted','Completed','Cancelled') DEFAULT 'Open',
    accepted_by     INT          NULL,
    transaction_id  INT          NULL,          -- set when completed
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id)     REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (accepted_by) REFERENCES users(id) ON DELETE SET NULL
);
