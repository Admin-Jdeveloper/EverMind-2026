-- MediaCompile PostgreSQL Database Initialization
-- Ensure required extensions are installed on the primary database

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Log installed extensions for verification
DO $$
BEGIN
    RAISE NOTICE 'Extensions installed successfully: uuid-ossp, vector';
END $$;
