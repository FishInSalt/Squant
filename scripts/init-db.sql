-- Squant 数据库初始化脚本
-- 启用 TimescaleDB 扩展

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 提示信息
DO $$
BEGIN
    RAISE NOTICE 'TimescaleDB extension enabled successfully';
    RAISE NOTICE 'UUID extension enabled successfully';
END $$;
