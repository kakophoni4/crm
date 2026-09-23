"""Durable collection queue for incoming beneficiary workbooks."""
from alembic import op
revision = '0126_benik_collection'
down_revision = '0125_task_notifications'
branch_labels = None
depends_on = None

def upgrade():
    op.execute("LOCK TABLE messages IN SHARE ROW EXCLUSIVE MODE")
    op.execute("CREATE TABLE benik_collection_state (id INTEGER PRIMARY KEY CHECK(id=1), historical_max_id BIGINT NOT NULL)")
    op.execute("INSERT INTO benik_collection_state SELECT 1, COALESCE(max(id),0) FROM messages")
    op.execute("""CREATE TABLE benik_collection_queue (
        message_id BIGINT PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        report JSONB NOT NULL DEFAULT '[]', updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX idx_benik_queue_pending ON benik_collection_queue(next_attempt_at) WHERE status='pending'")
    op.execute("""CREATE FUNCTION queue_benik_message() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.direction::text = 'inbound' AND jsonb_array_length(NEW.attachments) > 0 THEN
            INSERT INTO benik_collection_queue(message_id) VALUES(NEW.id)
            ON CONFLICT(message_id) DO UPDATE SET status='pending', next_attempt_at=now(), attempts=0;
        END IF;
        RETURN NEW;
    END $$""")
    op.execute("CREATE TRIGGER benik_message AFTER INSERT OR UPDATE OF attachments,lead_id ON messages FOR EACH ROW EXECUTE FUNCTION queue_benik_message()")

def downgrade():
    op.execute('DROP TRIGGER benik_message ON messages')
    op.execute('DROP FUNCTION queue_benik_message()')
    op.execute('DROP TABLE benik_collection_queue')
    op.execute('DROP TABLE benik_collection_state')
