-- Only the two receipts verified against the original PDFs.
-- Idempotent: already-corrected rows are left unchanged.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

DO $$
DECLARE matched integer;
BEGIN
    PERFORM id FROM opt_receipts WHERE id IN (37, 40) FOR UPDATE;
    SELECT count(*) INTO matched FROM opt_receipts
    WHERE (id, supplier_inn) IN ((37, '7751377028'), (40, '9729323581'))
      AND doc_kind = 'receipt' AND is_correction = true
      AND period_code IN ('1/26', '2/26')
      AND (metadata #>> '{parsed,period_code}' IS NULL
           OR metadata #>> '{parsed,period_code}' = '1/26');
    IF matched <> 2 THEN
        RAISE EXCEPTION 'Receipt identities or periods changed; no rows updated. Inspect IDs 37 and 40.';
    END IF;
END $$;

UPDATE opt_receipts
SET period_code = '1/26',
    metadata = jsonb_set(
        metadata || jsonb_build_object('period_repair', jsonb_build_object(
            'previous_period_code', period_code,
            'previous_parsed', metadata -> 'parsed',
            'reason', 'Original PDF verified: 1 квартал, 21, 2026 год',
            'repaired_at', now()
        )),
        '{parsed}',
        COALESCE(NULLIF(metadata -> 'parsed', 'null'::jsonb), '{}'::jsonb)
            || jsonb_build_object('period_code', '1/26')
    ),
    updated_at = now()
WHERE (id, supplier_inn) IN ((37, '7751377028'), (40, '9729323581'))
  AND period_code = '2/26'
RETURNING id, supplier_inn, period_code, metadata #>> '{parsed,period_code}' AS pdf_period;

COMMIT;
