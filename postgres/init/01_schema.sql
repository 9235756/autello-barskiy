-- Схема БД Autello. Выполняется один раз при первом создании тома pgdata.
-- Чтобы применить заново: make clean && make up

CREATE TABLE IF NOT EXISTS leads (
    id             BIGSERIAL PRIMARY KEY,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    name           TEXT        NOT NULL,
    phone          TEXT,
    email          TEXT,
    company        TEXT,
    business_info  TEXT,
    budget         TEXT,
    contact_method TEXT CHECK (contact_method IN ('phone', 'telegram', 'whatsapp', 'email')),
    comment        TEXT,
    metrics        JSONB NOT NULL DEFAULT '{}'::jsonb,  -- UTM, referrer, время заполнения
    tech_info      JSONB NOT NULL DEFAULT '{}'::jsonb   -- user-agent, язык, экран
);

CREATE INDEX IF NOT EXISTS leads_created_at_idx ON leads (created_at DESC);
CREATE INDEX IF NOT EXISTS leads_metrics_gin     ON leads USING GIN (metrics);

COMMENT ON TABLE  leads         IS 'Заявки «тёплых клиентов» с формы сайта';
COMMENT ON COLUMN leads.metrics IS 'Лид-метрики: utm_*, referrer, landing, fill_time_sec';
