CREATE INDEX IF NOT EXISTS term_sessions_user_idx ON term.sessions (user_id, created_at DESC);
