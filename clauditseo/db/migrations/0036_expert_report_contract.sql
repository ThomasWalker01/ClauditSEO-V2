-- Brief v10 step AF: what the output contract made of a brief's answer.
-- JSON: status (read | needs-input), the questions a brief asked instead of
-- answering, the rows it emitted, the rows dropped and why, its assumptions
-- and what it could not assess. NULL on every report written before the
-- contract existed - those briefs answered the pipe-format index, not the
-- block, and nothing here describes them.
ALTER TABLE expert_reports ADD COLUMN contract TEXT;
