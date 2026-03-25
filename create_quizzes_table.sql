-- SQL script to create the quizzes table in PostgreSQL
-- Run this script in pgAdmin4 or your PostgreSQL client
-- Database: GestureLab

-- Create quizzes table
CREATE TABLE IF NOT EXISTS quizzes (
    id SERIAL PRIMARY KEY,
    level VARCHAR(50) NOT NULL,
    question_text TEXT,
    question_image VARCHAR(500),
    option1_text VARCHAR(255),
    option2_text VARCHAR(255),
    option3_text VARCHAR(255),
    option4_text VARCHAR(255),
    option1_image VARCHAR(500),
    option2_image VARCHAR(500),
    option3_image VARCHAR(500),
    option4_image VARCHAR(500),
    correct_option INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index on level for faster filtering by quiz level (Beginner, Intermediate, Advance)
CREATE INDEX IF NOT EXISTS idx_quizzes_level ON quizzes(level);

-- Create index on correct_option for faster queries
CREATE INDEX IF NOT EXISTS idx_quizzes_correct_option ON quizzes(correct_option);

-- Add check constraint to ensure correct_option is between 1 and 4
ALTER TABLE quizzes ADD CONSTRAINT chk_correct_option_range 
    CHECK (correct_option >= 1 AND correct_option <= 4);

-- Sample insert statements (optional - for testing)
-- Beginner quiz example
-- INSERT INTO quizzes (level, question_text, option1_image, option2_image, option3_image, option4_image, correct_option) 
-- VALUES ('Beginner', 'Which of the following is the sign for the letter D?', '/static/images/sign-d.png', '/static/images/sign-b.png', '/static/images/sign-c.png', '/static/images/sign-e.png', 1);

-- Intermediate quiz example
-- INSERT INTO quizzes (level, question_text, question_image, option1_text, option2_text, option3_text, option4_text, correct_option) 
-- VALUES ('Intermediate', 'What letter is being shown in this image?', '/static/images/sign-h.png', 'h', 'f', 'g', 'a', 1);

-- Advance quiz example (text only)
-- INSERT INTO quizzes (level, question_text, question_image, option1_text, option2_text, option3_text, option4_text, correct_option) 
-- VALUES ('Advance', 'What letter is being shown in this image?', '/static/images/sign-h.png', 'h', 'f', 'g', 'a', 1);

-- Advance quiz example (images only)
-- INSERT INTO quizzes (level, question_text, question_image, option1_image, option2_image, option3_image, option4_image, correct_option) 
-- VALUES ('Advance', 'Which of the following is the sign for the letter D?', '/static/images/sign-d.png', '/static/images/sign-d.png', '/static/images/sign-b.png', '/static/images/sign-c.png', '/static/images/sign-e.png', 1);
