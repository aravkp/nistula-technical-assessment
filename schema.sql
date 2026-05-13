-- =====================================================================
-- Nistula guest messaging — Part 2 schema
--
-- PostgreSQL 14+. Uses pgcrypto's gen_random_uuid() for primary keys.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------

CREATE TYPE message_source AS ENUM (
    'whatsapp',
    'booking_com',
    'airbnb',
    'instagram',
    'direct'
);

CREATE TYPE message_direction AS ENUM ('inbound', 'outbound');

CREATE TYPE reservation_status AS ENUM (
    'pending',
    'confirmed',
    'cancelled',
    'completed'
);

CREATE TYPE conversation_status AS ENUM (
    'open',
    'pending_agent',
    'resolved'
);

-- Allowed values for messages.draft_origin (outbound only).
CREATE TYPE draft_origin AS ENUM (
    'ai_drafted',
    'ai_drafted_agent_edited',
    'agent_written'
);

-- ---------------------------------------------------------------------
-- guests — one row per *person* across channels.
-- A guest may have multiple identities (a WhatsApp number, an Airbnb
-- profile, a Booking.com profile). Identity unification happens in
-- guest_identities, so we keep this table deliberately thin.
-- ---------------------------------------------------------------------

CREATE TABLE guests (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name  TEXT NOT NULL,                -- the name the guest goes by; not necessarily their legal name
    email         TEXT,                         -- nullable: WhatsApp-only guests may never share email
    phone         TEXT,                         -- nullable for the same reason
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Email is not UNIQUE on purpose: families share inboxes, and OTAs sometimes
-- relay through a generic forwarding address. Deduplication is a soft job
-- that happens in the application layer.

CREATE INDEX idx_guests_email ON guests (email) WHERE email IS NOT NULL;
CREATE INDEX idx_guests_phone ON guests (phone) WHERE phone IS NOT NULL;

-- ---------------------------------------------------------------------
-- guest_identities — (channel, channel_user_id) pairs pointing at a guest.
-- This is what lets us say "the WhatsApp +91-… and the Airbnb profile abc123
-- are the same person" without forcing every guest to log in to anything.
-- ---------------------------------------------------------------------

CREATE TABLE guest_identities (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guest_id         UUID NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
    channel          message_source NOT NULL,   -- which platform this identity lives on
    channel_user_id  TEXT NOT NULL,             -- the platform's own ID for them (phone, OTA user id, instagram handle, etc.)
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- A given (channel, channel_user_id) can only ever map to one guest.
    -- Two real people on the same channel would have different ids, so this
    -- is safe even for shared family WhatsApps (they share a phone number
    -- and therefore are treated as one "guest" by the platform).
    UNIQUE (channel, channel_user_id)
);

CREATE INDEX idx_guest_identities_lookup
    ON guest_identities (channel, channel_user_id);

-- ---------------------------------------------------------------------
-- properties — Villas. JSONB `details` carries the long tail of
-- amenity / policy fields that change frequently and don't deserve their
-- own columns.
-- ---------------------------------------------------------------------

CREATE TABLE properties (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    location        TEXT NOT NULL,
    bedrooms        SMALLINT NOT NULL CHECK (bedrooms > 0),
    max_guests      SMALLINT NOT NULL CHECK (max_guests > 0),
    base_rate_inr   INTEGER NOT NULL CHECK (base_rate_inr >= 0),  -- stored as paise-free INR to dodge floats
    check_in_time   TIME NOT NULL,
    check_out_time  TIME NOT NULL,
    details         JSONB NOT NULL DEFAULT '{}'::jsonb,           -- amenities, house rules, contacts, etc.
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- GIN index so the operations team can search inside `details` without
-- scanning the whole table (e.g. find all villas with "pool" amenity).
CREATE INDEX idx_properties_details ON properties USING GIN (details);

-- ---------------------------------------------------------------------
-- reservations — confirmed/pending/cancelled bookings.
-- booking_ref is the public-facing reference shared with the guest and the
-- OTA; we use it as the natural key in webhook payloads.
-- ---------------------------------------------------------------------

CREATE TABLE reservations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_ref   TEXT NOT NULL UNIQUE,                                -- e.g. "NIS-2026-0142"
    guest_id      UUID NOT NULL REFERENCES guests(id) ON DELETE RESTRICT,
    property_id   UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
    check_in      DATE NOT NULL,
    check_out     DATE NOT NULL,
    num_guests    SMALLINT NOT NULL CHECK (num_guests > 0),
    status        reservation_status NOT NULL DEFAULT 'pending',
    total_inr     INTEGER NOT NULL CHECK (total_inr >= 0),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (check_out > check_in)
);

CREATE INDEX idx_reservations_booking_ref ON reservations (booking_ref);
CREATE INDEX idx_reservations_guest       ON reservations (guest_id);
CREATE INDEX idx_reservations_property    ON reservations (property_id, check_in);

-- ---------------------------------------------------------------------
-- conversations — a thread of messages with one guest.
--
-- reservation_id is NULLABLE on purpose: pre-sales enquiries arrive
-- before any booking exists. When a booking is eventually made, the app
-- backfills reservation_id on the conversation.
-- ---------------------------------------------------------------------

CREATE TABLE conversations (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guest_id         UUID NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
    reservation_id   UUID REFERENCES reservations(id) ON DELETE SET NULL,
    primary_channel  message_source NOT NULL,    -- where the thread started; messages may arrive on other channels later
    status           conversation_status NOT NULL DEFAULT 'open',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_message_at  TIMESTAMPTZ NOT NULL DEFAULT now()              -- denormalised for cheap "recent activity" sorting
);

CREATE INDEX idx_conversations_guest    ON conversations (guest_id, last_message_at DESC);
CREATE INDEX idx_conversations_status   ON conversations (status) WHERE status <> 'resolved';
CREATE INDEX idx_conversations_resv     ON conversations (reservation_id) WHERE reservation_id IS NOT NULL;

-- ---------------------------------------------------------------------
-- messages — single table for inbound AND outbound across all channels.
--
-- Rationale: every guest-facing channel uses the same "text in / text out"
-- shape. Splitting into per-channel tables would mean N joins to render a
-- thread and N migrations every time we add a field. We instead keep one
-- table with nullable role-specific columns and rely on `direction` /
-- `source` to disambiguate.
-- ---------------------------------------------------------------------

CREATE TABLE messages (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id           UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    source                    message_source NOT NULL,                    -- channel this specific message was sent on
    direction                 message_direction NOT NULL,
    body                      TEXT NOT NULL,
    sent_at                   TIMESTAMPTZ NOT NULL,                        -- when the channel says it was sent
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),          -- when we wrote it to the DB

    -- Inbound-specific fields (NULL for outbound)
    query_type                TEXT,                                        -- output of the rule-based classifier
    confidence_score          NUMERIC(3, 2),                               -- composite score, [0.00, 1.00]
    classifier_version        TEXT,                                        -- e.g. "rules-v1" — lets us re-classify old messages later

    -- Outbound-specific fields (NULL for inbound)
    draft_origin              draft_origin,
    was_auto_sent             BOOLEAN,                                     -- TRUE when the system sent without agent review
    drafted_from_message_id   UUID REFERENCES messages(id) ON DELETE SET NULL,  -- the inbound message this reply answers
    sent_by_agent_id          UUID,                                        -- no FK on purpose — agents table is out of scope here

    -- Direction-shape consistency checks. Keep these forgiving: we still
    -- want to be able to insert partial records during ingestion.
    CHECK (
        direction = 'inbound'
        OR (
            direction = 'outbound'
            AND draft_origin IS NOT NULL
            AND was_auto_sent IS NOT NULL
        )
    ),
    CHECK (
        direction = 'outbound'
        OR (
            direction = 'inbound'
            AND query_type IS NOT NULL
        )
    )
);

CREATE INDEX idx_messages_conversation     ON messages (conversation_id, sent_at);
CREATE INDEX idx_messages_drafted_from     ON messages (drafted_from_message_id) WHERE drafted_from_message_id IS NOT NULL;
CREATE INDEX idx_messages_inbound_review   ON messages (created_at DESC) WHERE direction = 'inbound';


-- =====================================================================
-- HARDEST DESIGN DECISION
-- =====================================================================
-- TODO: write a short paragraph here explaining the hardest design
-- decision you made and why. Candidates: single messages table vs split
-- tables per channel, nullable reservation_id on conversations, guest
-- identity unification strategy.
