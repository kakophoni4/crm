"""SBIS credentials and official company contacts."""
from alembic import op
import sqlalchemy as sa
revision = "0120_shop_access_contacts"
down_revision = "0119_kesher_user_org"
branch_labels = None
depends_on = None
FIELDS = ("sbis_access", "sbis_login", "official_email", "official_phone")
def upgrade():
    for field in FIELDS:
        op.add_column("lawyer_shops", sa.Column(field, sa.Text(), nullable=True))
    op.add_column("lawyer_shops", sa.Column("sbis_password_encrypted", sa.LargeBinary(), nullable=True))
def downgrade():
    op.drop_column("lawyer_shops", "sbis_password_encrypted")
    for field in reversed(FIELDS):
        op.drop_column("lawyer_shops", field)
