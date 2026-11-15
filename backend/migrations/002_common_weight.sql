-- Schema v2: 共同权重名次研究扩展 efficiency_runs。
-- 新字段对旧 CCR 研究为空/默认值，kind 默认 'dea'，原效率研究链路不变。
-- 本地演示库仍由 SQLAlchemy metadata 直接创建；本脚本记录升级口径。
ALTER TABLE efficiency_runs ADD COLUMN kind VARCHAR(20) DEFAULT 'dea';
ALTER TABLE efficiency_runs ADD COLUMN weight_lower JSON;
ALTER TABLE efficiency_runs ADD COLUMN weight_upper JSON;
ALTER TABLE efficiency_runs ADD COLUMN time_budget FLOAT DEFAULT 60.0;
-- 新增运行状态：degraded（超时降级，档案未完成但保留已证明名次界限）。
