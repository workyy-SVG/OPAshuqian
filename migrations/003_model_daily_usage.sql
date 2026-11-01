CREATE TABLE model_daily_usage (
 provider TEXT NOT NULL CHECK(provider IN ('deepseek','qwen')),
 usage_date TEXT NOT NULL,
 request_count INTEGER NOT NULL DEFAULT 0 CHECK(request_count >= 0),
 updated_at TEXT NOT NULL,
 PRIMARY KEY(provider,usage_date)
);
