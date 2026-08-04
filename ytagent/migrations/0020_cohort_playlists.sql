-- M1 item 2 — the YouTube-side cohort marker (BACKLOG review 2026-08-04, approved with confinement).
-- The Shorts-vs-long-form success measurement needs the cohort to survive on YouTube, not only in this
-- DB, so an Analytics pull can reconstruct it via playlistItems.list. We record ONE UNLISTED playlist
-- per (channel, cohort) and mark each video once it has been placed (idempotent membership).
--
-- Confinement (mirrors update_public): playlistItems.insert adds ONLY our own uploaded youtube_video_id
-- to ONLY our own cohort playlist (its id lives here). NO delete, NO listing/adding to others'
-- playlists, NO comment/branding. force-ssl already permits both writes — no new scope; only the
-- code surface grew, which is why the review is on the record.
CREATE TABLE IF NOT EXISTS cohort_playlists (
    channel_id          bigint      NOT NULL REFERENCES channels(id),
    cohort              text        NOT NULL,
    youtube_playlist_id text        NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (channel_id, cohort)
);

-- The membership marker: set once a video has been added to its cohort playlist, so a second live
-- publish of the same video (upload-private then make-public) never inserts a duplicate playlist item.
ALTER TABLE videos ADD COLUMN IF NOT EXISTS cohort_playlist_id text;
