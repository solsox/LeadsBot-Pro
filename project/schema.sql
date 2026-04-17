-- schema.sql
-- ============================================================
--  LeadAgent — Schema PostgreSQL
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Leads ────────────────────────────────────────────────────
CREATE TABLE leads (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    address     TEXT,
    phone       TEXT,
    email       TEXT,
    website     TEXT,
    rating      NUMERIC(2,1),
    reviews     INTEGER,
    category    TEXT,
    zone        TEXT,
    query       TEXT,
    maps_url    TEXT,

    -- scoring
    score       INTEGER DEFAULT 0,
    priority    TEXT DEFAULT 'low'
                CHECK (priority IN ('high', 'medium', 'low')),
    score_reasons JSONB DEFAULT '[]',

    -- estado del pipeline
    status      TEXT DEFAULT 'new'
                CHECK (status IN ('new', 'generating', 'ready', 'contacted', 'opened', 'replied', 'discarded')),

    -- timestamps
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_leads_priority ON leads(priority);
CREATE INDEX idx_leads_status   ON leads(status);
CREATE INDEX idx_leads_score    ON leads(score DESC);
CREATE INDEX idx_leads_zone     ON leads(zone);

-- ── Mensajes ─────────────────────────────────────────────────
CREATE TABLE messages (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id       UUID REFERENCES leads(id) ON DELETE CASCADE,
    channel       TEXT DEFAULT 'email'
                  CHECK (channel IN ('email', 'whatsapp', 'instagram')),
    subject       TEXT,
    content       TEXT NOT NULL,
    sent_at       TIMESTAMPTZ,
    opened_at     TIMESTAMPTZ,
    replied_at    TIMESTAMPTZ,
    response_text TEXT,
    message_id    TEXT,         -- ID del servidor SMTP
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_messages_lead_id ON messages(lead_id);
CREATE INDEX idx_messages_sent_at ON messages(sent_at);

-- ── Eventos de tracking ───────────────────────────────────────
CREATE TABLE tracking_events (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id    UUID REFERENCES leads(id) ON DELETE CASCADE,
    event      TEXT NOT NULL
               CHECK (event IN ('open', 'click', 'reply', 'bounce', 'unsubscribe')),
    ip_address TEXT,
    user_agent TEXT,
    metadata   JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tracking_lead_id ON tracking_events(lead_id);
CREATE INDEX idx_tracking_event   ON tracking_events(event);

-- ── Worker runs ───────────────────────────────────────────────
CREATE TABLE worker_runs (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    loop_number   INTEGER,
    leads_scraped INTEGER DEFAULT 0,
    leads_scored  INTEGER DEFAULT 0,
    messages_sent INTEGER DEFAULT 0,
    errors        JSONB DEFAULT '[]',
    started_at    TIMESTAMPTZ DEFAULT NOW(),
    finished_at   TIMESTAMPTZ
);

-- ── Trigger: updated_at automático ───────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_leads_updated_at
    BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();