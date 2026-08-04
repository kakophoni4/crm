"""Round OPT commission/payments to whole rubles; close kopeck tails as paid.

Revision ID: 0093_opt_round_commission_rubles
Revises: 0092_opt_receipts_sent_at
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0093_opt_round_commission_rubles"
down_revision: str | None = "0092_opt_receipts_sent_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Round due/adjustment; leave amount_paid as stored (may already be whole).
    # Status: remainder under 1 ₽ → paid.
    op.execute(
        """
        UPDATE lead_opt_orders
        SET
            commission_due = ROUND(COALESCE(commission_due, 0)::numeric, 0),
            commission_adjustment = ROUND(COALESCE(commission_adjustment, 0)::numeric, 0),
            payment_status = CASE
                WHEN ROUND(COALESCE(commission_due, 0)::numeric, 0) <= 0 THEN 'paid'
                WHEN COALESCE(amount_paid, 0) <= 0 THEN 'unpaid'
                WHEN COALESCE(amount_paid, 0)
                     + 0.999 >= ROUND(COALESCE(commission_due, 0)::numeric, 0)
                    THEN 'paid'
                ELSE 'partial'
            END
        """
    )
    # Round commission values inside volume_by_category JSON (best-effort).
    op.execute(
        """
        UPDATE lead_opt_orders o
        SET volume_by_category = sub.rounded
        FROM (
            SELECT
                id,
                (
                    SELECT jsonb_object_agg(key, value)
                    FROM (
                        SELECT
                            e.key,
                            CASE
                                WHEN jsonb_typeof(e.value) = 'object'
                                     AND e.value ? 'commission'
                                THEN jsonb_set(
                                    e.value,
                                    '{commission}',
                                    to_jsonb(
                                        ROUND((e.value->>'commission')::numeric, 0)
                                    )
                                )
                                ELSE e.value
                            END AS value
                        FROM jsonb_each(
                            COALESCE(o2.volume_by_category::jsonb, '{}'::jsonb)
                        ) AS e
                    ) parts
                ) AS rounded
            FROM lead_opt_orders o2
            WHERE o2.volume_by_category IS NOT NULL
        ) sub
        WHERE o.id = sub.id
          AND sub.rounded IS NOT NULL
        """
    )


def downgrade() -> None:
    # Irreversible money rounding — no-op.
    pass
