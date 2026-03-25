-- SQL script to create the lessons table in PostgreSQL
-- Run this script in pgAdmin4 or your PostgreSQL client

-- Create lessons table
CREATE TABLE IF NOT EXISTS lessons (
    id SERIAL PRIMARY KEY,
    sign_level VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    image VARCHAR(500) NOT NULL,
    heading VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index on sign_level for faster filtering
CREATE INDEX IF NOT EXISTS idx_lessons_sign_level ON lessons(sign_level);

-- Create index on name for faster searching
CREATE INDEX IF NOT EXISTS idx_lessons_name ON lessons(name);

-- Sample insert statement (optional - for testing)
-- INSERT INTO lessons (sign_level, name, image, heading, description) 
-- VALUES ('Basic', 'Aa', '/static/images/sample.jpg', 'How to sign', '1. Make a fist with your dominant hand.\n2. Keep your thumb on the side of your fingers.\n3. Ensure your fingers are curled tightly.\n4. Palm faces outward.\n5. Keep your hand steady.');
