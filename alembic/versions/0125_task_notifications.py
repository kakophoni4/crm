"""Transactional generic task notifications; no task content leaves CRM."""
from alembic import op
revision = '0125_task_notifications'
down_revision = '0124_pricing_snapshot'
branch_labels = None
depends_on = None

def upgrade():
    op.execute("""CREATE TABLE task_notification_outbox (
        id BIGSERIAL PRIMARY KEY,
        task_id BIGINT NOT NULL REFERENCES department_tasks(id) ON DELETE CASCADE,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind TEXT NOT NULL DEFAULT 'assigned', event_key TEXT UNIQUE,
        due_at TIMESTAMPTZ, status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        delivered_to JSONB NOT NULL DEFAULT '[]',
        error_code TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX idx_task_notifications_due ON task_notification_outbox(next_attempt_at) WHERE status IN ('pending','waiting','failed')")
    op.execute("""CREATE FUNCTION queue_task_notification() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP = 'INSERT' OR NEW.assignee_id IS DISTINCT FROM OLD.assignee_id THEN
            INSERT INTO task_notification_outbox(task_id,user_id) VALUES(NEW.id,NEW.assignee_id);
        END IF;
        RETURN NEW;
    END $$""")
    op.execute("CREATE TRIGGER task_notification AFTER INSERT OR UPDATE OF assignee_id ON department_tasks FOR EACH ROW EXECUTE FUNCTION queue_task_notification()")

def downgrade():
    op.execute('DROP TRIGGER task_notification ON department_tasks')
    op.execute('DROP FUNCTION queue_task_notification()')
    op.execute('DROP TABLE task_notification_outbox')
