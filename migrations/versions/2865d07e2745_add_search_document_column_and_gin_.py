"""add_search_document_column_and_gin_index_for_step_7

Revision ID: 2865d07e2745
Revises: 544554655cfb
Create Date: 2025-09-01 01:44:24.345840

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2865d07e2745'
down_revision: str | Sequence[str] | None = '544554655cfb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add search_document column
    op.add_column('items', sa.Column('search_document', sa.dialects.postgresql.TSVECTOR()))

    # Create function to compute search document from item data
    op.execute("""
        CREATE OR REPLACE FUNCTION items_compute_search_document(
            item_type TEXT,
            payload JSONB,
            tags TEXT[]
        ) RETURNS tsvector AS $$
        DECLARE
            content_text TEXT := '';
            tag_text TEXT := '';
        BEGIN
            -- Extract searchable text based on item type
            CASE item_type
                WHEN 'flashcard' THEN
                    content_text := CONCAT_WS(' ',
                        payload->>'front',
                        payload->>'back',
                        (SELECT string_agg(value::text, ' ') FROM jsonb_array_elements_text(payload->'examples')),
                        (SELECT string_agg(value::text, ' ') FROM jsonb_array_elements_text(payload->'hints')),
                        payload->>'pronunciation'
                    );
                WHEN 'mcq' THEN
                    content_text := CONCAT_WS(' ',
                        payload->>'stem',
                        (SELECT string_agg(value->>'text', ' ') FROM jsonb_array_elements(payload->'options') AS value),
                        (SELECT string_agg(value->>'rationale', ' ')
                         FROM jsonb_array_elements(payload->'options') AS value
                         WHERE value->>'rationale' IS NOT NULL)
                    );
                WHEN 'cloze' THEN
                    content_text := CONCAT_WS(' ',
                        payload->>'text',
                        payload->>'context_note',
                        (SELECT string_agg(answer, ' ')
                         FROM jsonb_array_elements(payload->'blanks') AS blank,
                              jsonb_array_elements_text(blank->'answers') AS answer)
                    );
                WHEN 'short_answer' THEN
                    content_text := CONCAT_WS(' ',
                        payload->>'prompt',
                        payload->'expected'->>'value',
                        payload->'expected'->>'unit',
                        (SELECT string_agg(value::text, ' ') FROM jsonb_array_elements_text(payload->'acceptable_patterns'))
                    );
                ELSE
                    content_text := payload::text;
            END CASE;

            -- Convert tags array to text
            tag_text := COALESCE(array_to_string(tags, ' '), '');

            -- Return weighted tsvector
            RETURN
                setweight(to_tsvector('english', COALESCE(content_text, '')), 'A') ||
                setweight(to_tsvector('english', tag_text), 'B') ||
                setweight(to_tsvector('english', item_type), 'C');
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;
    """)

    # Create trigger function to update search_document
    op.execute("""
        CREATE OR REPLACE FUNCTION items_update_search_document()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_document := items_compute_search_document(NEW.type, NEW.payload, NEW.tags);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger
    op.execute("""
        CREATE TRIGGER items_search_document_trigger
            BEFORE INSERT OR UPDATE OF type, payload, tags ON items
            FOR EACH ROW EXECUTE FUNCTION items_update_search_document();
    """)

    # Note: Existing rows will get search_document populated when they're next updated
    # The trigger will handle this automatically

    # Create GIN index for efficient full-text search
    op.create_index(
        'items_search_document_gin',
        'items',
        ['search_document'],
        postgresql_using='gin'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop the GIN index
    op.drop_index('items_search_document_gin', table_name='items')

    # Drop trigger
    op.execute("DROP TRIGGER IF EXISTS items_search_document_trigger ON items;")

    # Drop trigger function
    op.execute("DROP FUNCTION IF EXISTS items_update_search_document();")

    # Drop compute function
    op.execute("DROP FUNCTION IF EXISTS items_compute_search_document(TEXT, JSONB, TEXT[]);")

    # Drop the search_document column
    op.drop_column('items', 'search_document')
