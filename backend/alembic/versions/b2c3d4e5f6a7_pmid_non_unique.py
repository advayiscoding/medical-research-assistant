"""pmid is no longer a unique identity — dedup is by dedup_key only

The same paper can arrive DOI-keyed from one source (dedup_key="doi:…") and
PMID-keyed from another (dedup_key="pmid:…"), both carrying the same PMID under
different dedup_keys. A UNIQUE constraint on pmid would reject the second, so we
demote it to a plain index. Deduplication is solely by dedup_key.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_papers_pmid", table_name="papers")
    op.create_index("ix_papers_pmid", "papers", ["pmid"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_papers_pmid", table_name="papers")
    op.create_index("ix_papers_pmid", "papers", ["pmid"], unique=True)
