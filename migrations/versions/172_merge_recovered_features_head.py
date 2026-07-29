"""Merge the recovered Epic/Story/Trending-Issue migration branch into the main head.

Migrations 106_add_po_role through 111_add_trending_issues were authored off
105_fix_client_notifications_cascade_delete as an independent local branch that
was later reconstructed from a stale Docker image (see the "Recover lost local
commits" merge commit). Meanwhile mainline development continued past 105 on
its own path (106_add_reportlab_template_json onward) all the way to
171_merge_kanban_feature_heads. This leaves two heads; this no-op merge
migration rejoins them into one. Each branch is independent (adds its own
tables/columns), so no ordering constraint is imposed.

Revision ID: 172_merge_recovered_features_head
Revises: 111_add_trending_issues, 171_merge_kanban_feature_heads
"""

revision = "172_merge_recovered_features_head"
down_revision = (
    "111_add_trending_issues",
    "171_merge_kanban_feature_heads",
)
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
