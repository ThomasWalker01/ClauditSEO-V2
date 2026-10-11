-- Item 249: which brief an analysis was written under, and which reader read it.
--
-- `brief_version` is `expert.brief_version(tool)` when the analysis ran: the
-- hash of its prompt, framing and split. Where it differs from the brief as
-- it now stands, the analysis says "analysed under an earlier brief". NULL
-- means not recorded (0072 fills what the analyst cache's keys still say).
--
-- `reader_version` is `contract.reader_version()` when the stored contract
-- was last read: the hash of the reader's rules. A stamped analysis whose
-- reader has since changed is re-read at startup, with no model call, so a
-- rule change reaches what is stored. NULL means never stamped: those rows
-- are re-read once by `clauditseo reparse-contracts`, which stamps them.
ALTER TABLE expert_reports ADD COLUMN brief_version TEXT;
ALTER TABLE expert_reports ADD COLUMN reader_version TEXT;
