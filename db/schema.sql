-- Transcript Intelligence Dashboard Schema

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    grade TEXT NOT NULL,
    curriculum TEXT,
    target_exam TEXT,
    long_term_goal_summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    measurable_outcome TEXT,
    deadline TEXT,
    status TEXT DEFAULT 'not started' CHECK(status IN ('not started', 'in progress', 'achieved')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    topic_name TEXT NOT NULL,
    parent_topic_id INTEGER,
    mastery_score REAL DEFAULT 0 CHECK(mastery_score >= 0 AND mastery_score <= 100),
    confidence_score REAL DEFAULT 0 CHECK(confidence_score >= 0 AND confidence_score <= 100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_topic_id) REFERENCES topics(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    transcript_text TEXT NOT NULL,
    session_type TEXT DEFAULT 'session' CHECK(session_type IN ('trial', 'session')),
    session_date TEXT NOT NULL,
    extracted_summary TEXT,
    detected_topics TEXT,
    detected_misconceptions TEXT,
    detected_strengths TEXT,
    engagement_score REAL DEFAULT 0 CHECK(engagement_score >= 0 AND engagement_score <= 100),
    parent_summary TEXT,
    tutor_insight TEXT,
    recommended_next TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mental_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    first_detected TEXT NOT NULL,
    frequency_count INTEGER DEFAULT 1,
    severity_score REAL DEFAULT 1 CHECK(severity_score >= 0 AND severity_score <= 10),
    resolved INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);
