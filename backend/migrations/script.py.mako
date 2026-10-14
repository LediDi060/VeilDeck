"""${message}"""

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade():
    """Применяет миграцию."""
    ${upgrades if upgrades else "pass"}


def downgrade():
    """Отменяет миграцию."""
    ${downgrades if downgrades else "pass"}
