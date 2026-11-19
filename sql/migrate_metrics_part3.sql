-- =====================================================================
--  Миграция behavior_metrics: часть 2 → часть 3
--
--  Было (часть 2): одна строка метрик на заявку, application_id = PRIMARY KEY
--  и FOREIGN KEY → applications(id). Отсюда ошибка урока
--  «Behavior metrics for application 0 already exists»: вторая отправка с тем же
--  application_id (а фронт шлёт 0) упиралась в PK.
--
--  Стало (часть 3): метрики АНОНИМНЫЕ. Свой id, session_id (одна строка на визит),
--  application_id — просто число: nullable, без FK и без UNIQUE.
--
--  Что делает скрипт (только если таблица ещё в старом формате):
--    1. переименовывает старую таблицу в behavior_metrics_part2 (данные не теряются);
--    2. создаёт новую behavior_metrics;
--    3. переносит старые строки в новый формат (clicks → buttons_clicked и т.д.).
--  Повторный запуск ничего не делает. Backend применяет его при каждом старте.
--  Вручную: docker compose exec -T postgres psql -U autello -d autello < sql/migrate_metrics_part3.sql
-- =====================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'behavior_metrics' AND column_name = 'time_on_page_sec'
    ) THEN
        RAISE NOTICE 'behavior_metrics в формате части 2 — мигрирую';

        ALTER TABLE behavior_metrics RENAME TO behavior_metrics_part2;
        -- Имя индекса первичного ключа уникально в схеме — освобождаем его для новой таблицы
        ALTER TABLE behavior_metrics_part2 RENAME CONSTRAINT behavior_metrics_pkey TO behavior_metrics_part2_pkey;

        CREATE TABLE behavior_metrics (
            id                SERIAL PRIMARY KEY,
            session_id        VARCHAR(64) UNIQUE,
            application_id    INTEGER,
            time_on_page      INTEGER NOT NULL DEFAULT 0,
            buttons_clicked   JSONB   NOT NULL DEFAULT '{}'::jsonb,
            cursor_positions  JSONB   NOT NULL DEFAULT '[]'::jsonb,
            return_frequency  INTEGER NOT NULL DEFAULT 0,
            viewport_w        INTEGER,
            viewport_h        INTEGER,
            doc_w             INTEGER,
            doc_h             INTEGER,
            page              VARCHAR(200),
            extra             JSONB   NOT NULL DEFAULT '{}'::jsonb,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_behavior_metrics_created_at     ON behavior_metrics (created_at);
        CREATE INDEX IF NOT EXISTS ix_behavior_metrics_application_id ON behavior_metrics (application_id);

        -- clicks: [{"el":"submit","t":41.2}, ...] → buttons_clicked: {"submit": 1, ...}
        INSERT INTO behavior_metrics
            (application_id, time_on_page, buttons_clicked, cursor_positions, return_frequency, page, extra, created_at, updated_at)
        SELECT o.application_id,
               o.time_on_page_sec,
               COALESCE((SELECT jsonb_object_agg(c.el, c.n)
                         FROM (SELECT e->>'el' AS el, COUNT(*) AS n
                               FROM jsonb_array_elements(o.clicks) AS e
                               WHERE e ? 'el'
                               GROUP BY 1) AS c), '{}'::jsonb),
               '[]'::jsonb,
               o.return_count,
               '/',
               jsonb_build_object('source', 'migrated_part2', 'utm', o.utm, 'referrer', o.referrer,
                                  'user_agent', o.user_agent, 'screen', o.screen, 'language', o.language,
                                  'scroll_depth', o.scroll_depth, 'hovers', o.hovers),
               o.created_at,
               o.created_at
        FROM behavior_metrics_part2 AS o;

        COMMENT ON TABLE behavior_metrics_part2 IS 'Архив метрик части 2 (связь 1:1 с заявкой). Данные перенесены в behavior_metrics';
    END IF;
END $$;
