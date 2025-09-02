"""fix search triggers and functions properly

Revision ID: 12ff5e1154c0
Revises: 83f4a9eb5d3f
Create Date: 2025-09-02 10:10:43.444939

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "12ff5e1154c0"
down_revision: Union[str, Sequence[str], None] = "83f4a9eb5d3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix search triggers and functions properly."""
    # Step 1: Drop all existing triggers to ensure clean state
    op.execute("DROP TRIGGER IF EXISTS items_search_document_trigger ON items;")

    # Step 2: Create or replace the compute function (idempotent)
    op.execute(
        """
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
                        (SELECT string_agg(value::text, ' ') FROM jsonb_array_elements_text(COALESCE(payload->'examples', '[]'::jsonb))),
                        (SELECT string_agg(value::text, ' ') FROM jsonb_array_elements_text(COALESCE(payload->'hints', '[]'::jsonb))),
                        payload->>'pronunciation'
                    );
                WHEN 'mcq' THEN
                    content_text := CONCAT_WS(' ',
                        payload->>'stem',
                        (SELECT string_agg(value->>'text', ' ') FROM jsonb_array_elements(COALESCE(payload->'options', '[]'::jsonb)) AS value),
                        (SELECT string_agg(value->>'rationale', ' ')
                         FROM jsonb_array_elements(COALESCE(payload->'options', '[]'::jsonb)) AS value
                         WHERE value->>'rationale' IS NOT NULL)
                    );
                WHEN 'cloze' THEN
                    content_text := CONCAT_WS(' ',
                        payload->>'text',
                        payload->>'context_note',
                        (SELECT string_agg(answer, ' ')
                         FROM jsonb_array_elements(COALESCE(payload->'blanks', '[]'::jsonb)) AS blank,
                              jsonb_array_elements_text(COALESCE(blank->'answers', '[]'::jsonb)) AS answer)
                    );
                WHEN 'short_answer' THEN
                    content_text := CONCAT_WS(' ',
                        payload->>'prompt',
                        payload->'expected'->>'value',
                        payload->'expected'->>'unit',
                        (SELECT string_agg(value::text, ' ') FROM jsonb_array_elements_text(COALESCE(payload->'acceptable_patterns', '[]'::jsonb)))
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
    """
    )

    # Step 3: Create or replace the trigger function (idempotent)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION items_update_search_document()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_document := items_compute_search_document(NEW.type::text, NEW.payload::jsonb, NEW.tags);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """
    )

    # Step 4: Create the trigger once with clean state
    op.execute(
        """
        CREATE TRIGGER items_search_document_trigger
            BEFORE INSERT OR UPDATE OF type, payload, tags ON items
            FOR EACH ROW EXECUTE FUNCTION items_update_search_document();
    """
    )


def downgrade() -> None:
    """Downgrade - remove the trigger only (keep functions for other migrations)."""
    op.execute("DROP TRIGGER IF EXISTS items_search_document_trigger ON items;")
