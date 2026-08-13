CREATE TABLE IF NOT EXISTS rooms (
    id              SERIAL PRIMARY KEY,
    code            TEXT UNIQUE NOT NULL,
    columns_json    TEXT NOT NULL DEFAULT '[3,4,3,3,3]',
    lookback        INTEGER NOT NULL DEFAULT 1,
    active_round_id INTEGER,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS students (
    id         SERIAL PRIMARY KEY,
    room_id    INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    number     INTEGER,
    position   INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_students_room ON students(room_id, position);

CREATE TABLE IF NOT EXISTS rounds (
    id           SERIAL PRIMARY KEY,
    room_id      INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    round_no     INTEGER NOT NULL,
    columns_json TEXT NOT NULL,
    seats_json   TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rounds_room_no ON rounds(room_id, round_no);
