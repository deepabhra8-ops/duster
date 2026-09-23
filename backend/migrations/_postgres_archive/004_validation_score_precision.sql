BEGIN;

ALTER TABLE validation_results
    ALTER COLUMN overall_score TYPE NUMERIC(6, 4);

COMMIT;
