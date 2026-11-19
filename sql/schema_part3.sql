-- =====================================================================
--  Схема части 3: новые и изменённые таблицы. Идемпотентна (IF NOT EXISTS).
--  Backend применяет файл при каждом старте (после create_all).
--  Тот же SQL — в docstring моделей backend/app/models/*.py.
--
--  Вручную (pgAdmin → Query Tool, или):
--    docker compose exec -T postgres psql -U autello -d autello < sql/schema_part3.sql
-- =====================================================================

-- ---------- Администраторы (новая) ----------
CREATE TABLE IF NOT EXISTS admins (
    id               SERIAL PRIMARY KEY,
    username         VARCHAR(50)  NOT NULL UNIQUE,
    hashed_password  VARCHAR(100) NOT NULL,          -- bcrypt: $2b$12$..., 60 символов
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);
COMMENT ON TABLE admins IS 'Администраторы /admin. Пароль — только bcrypt-хеш';

-- ---------- Поведенческие метрики (изменена: анонимные, одна строка на визит) ----------
-- Если таблица осталась от части 2 — её сначала переделывает sql/migrate_metrics_part3.sql
CREATE TABLE IF NOT EXISTS behavior_metrics (
    id                SERIAL PRIMARY KEY,
    session_id        VARCHAR(64) UNIQUE,              -- crypto.randomUUID() из браузера
    application_id    INTEGER,                         -- принимаем, НЕ проверяем: без FK и UNIQUE
    time_on_page      INTEGER NOT NULL DEFAULT 0,      -- секунд на странице
    buttons_clicked   JSONB   NOT NULL DEFAULT '{}'::jsonb,  -- {"submit": 1, "service": 3}
    cursor_positions  JSONB   NOT NULL DEFAULT '[]'::jsonb,  -- [{"x":0.41,"y":0.37}] доли 0..1 документа
    return_frequency  INTEGER NOT NULL DEFAULT 0,      -- возвратов на вкладку (visibilitychange)
    viewport_w        INTEGER,
    viewport_h        INTEGER,
    doc_w             INTEGER,
    doc_h             INTEGER,
    page              VARCHAR(200),
    extra             JSONB   NOT NULL DEFAULT '{}'::jsonb,  -- utm, referrer, user_agent
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_behavior_metrics_created_at     ON behavior_metrics (created_at);
CREATE INDEX IF NOT EXISTS ix_behavior_metrics_application_id ON behavior_metrics (application_id);
COMMENT ON TABLE behavior_metrics IS 'Анонимные метрики визитов главной. Фронт шлёт снимок раз в секунду (upsert по session_id)';

-- ---------- Заявки (изменена): роль «собственник» для приоритизации ----------
ALTER TABLE applications DROP CONSTRAINT IF EXISTS ck_applications_role;
ALTER TABLE applications ADD CONSTRAINT ck_applications_role
    CHECK (role IN ('сотрудник', 'руководитель', 'собственник'));
