"""Work seasons independent from fiscal periods; preserve every existing order."""
from alembic import op
revision = "0123_sales_seasons"
down_revision = "0122_nulevka_role"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("""CREATE TABLE sales_seasons (
        id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE,
        starts_at TIMESTAMPTZ NOT NULL UNIQUE,
        created_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")
    op.execute("INSERT INTO sales_seasons (name, starts_at) VALUES ('2-й квартал 2026', '1970-01-01 00:00:00+00')")
    op.execute("ALTER TABLE lead_opt_orders ADD COLUMN season_id BIGINT REFERENCES sales_seasons(id) ON DELETE RESTRICT")
    op.execute("UPDATE lead_opt_orders SET season_id = (SELECT id FROM sales_seasons LIMIT 1)")
    op.execute("ALTER TABLE lead_opt_orders ALTER COLUMN season_id SET NOT NULL")
    op.execute("CREATE INDEX idx_opt_orders_season ON lead_opt_orders(season_id)")
    op.execute("""CREATE FUNCTION assign_order_season() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP = 'UPDATE' THEN
            IF NEW.season_id IS DISTINCT FROM OLD.season_id THEN
                RAISE EXCEPTION 'Order season cannot change';
            END IF;
        ELSE
            -- Explicit season is used only by the authorized historical importer.
            IF NEW.season_id IS NOT NULL THEN RETURN NEW; END IF;
            -- created_at is timestamp without timezone in CRM, stored in UTC.
            SELECT id INTO NEW.season_id FROM sales_seasons
            WHERE starts_at <= COALESCE(NEW.created_at AT TIME ZONE 'UTC', now())
            ORDER BY starts_at DESC LIMIT 1;
            IF NEW.season_id IS NULL THEN
                SELECT id INTO NEW.season_id FROM sales_seasons ORDER BY starts_at LIMIT 1;
            END IF;
        END IF;
        RETURN NEW;
    END $$""")
    op.execute("CREATE TRIGGER order_season BEFORE INSERT OR UPDATE OF season_id ON lead_opt_orders FOR EACH ROW EXECUTE FUNCTION assign_order_season()")

def downgrade():
    op.execute("DROP TRIGGER order_season ON lead_opt_orders")
    op.execute("DROP FUNCTION assign_order_season()")
    op.execute("ALTER TABLE lead_opt_orders DROP COLUMN season_id")
    op.execute("DROP TABLE sales_seasons")
