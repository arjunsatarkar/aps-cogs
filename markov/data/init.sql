CREATE TABLE IF NOT EXISTS guild_total_completion_count (
    guild_id BLOB,
    first_token TEXT,
    total_completion_count INTEGER,
    UNIQUE (guild_id, first_token)
) STRICT;

CREATE TABLE IF NOT EXISTS guild_pairs (
    guild_id BLOB,
    first_token TEXT,
    second_token TEXT,
    frequency INTEGER,
    UNIQUE (guild_id, first_token, second_token)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_guild_pairs__guild_id__first_token__frequency__second_token ON guild_pairs (guild_id, first_token, frequency, second_token);

CREATE TABLE IF NOT EXISTS member_total_completion_count (
    guild_id BLOB,
    member_id BLOB,
    first_token TEXT,
    total_completion_count INTEGER,
    UNIQUE (guild_id, member_id, first_token)
) STRICT;

CREATE TABLE IF NOT EXISTS member_pairs (
    guild_id BLOB,
    member_id BLOB,
    first_token TEXT,
    second_token TEXT,
    frequency INTEGER,
    UNIQUE (guild_id, member_id, first_token, second_token)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_member_pairs__guild_id__member_id__first_token__frequency__second_token ON member_pairs (
    guild_id,
    member_id,
    first_token,
    frequency,
    second_token
);

PRAGMA analysis_limit = 1000;

PRAGMA optimize;
