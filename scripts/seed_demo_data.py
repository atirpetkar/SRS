#!/usr/bin/env python3
"""
Demo Data Seeder - Populates the database with sample content for CLI testing

This script creates:
- Dev user and organization
- Sample flashcards and MCQs with various difficulties
- Some items with scheduler state to test reviews
- Mix of due and new items for a realistic demo
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.config.settings import settings
from api.v1.items.models import Item, Organization, User
from api.v1.review.models import SchedulerState


async def seed_demo_data():
    """Seed database with demo data for testing CLI"""

    # Create async engine and session
    engine = create_async_engine(settings.database_url)
    async_session = async_sessionmaker(engine)

    async with async_session() as db:
        try:
            # Create dev organization
            dev_org_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
            dev_user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")

            # Check if org already exists
            existing_org = await db.get(Organization, dev_org_id)
            if not existing_org:
                dev_org = Organization(
                    id=dev_org_id,
                    name="Development Organization",
                    meta={"created_by": "seed_script"},
                )
                db.add(dev_org)
                print("✅ Created development organization")
            else:
                print("ℹ️ Development organization already exists")

            # Check if user already exists
            existing_user = await db.get(User, dev_user_id)
            if not existing_user:
                dev_user = User(
                    id=dev_user_id,
                    org_id=dev_org_id,
                    email="dev@learning-os.com",
                    meta={"created_by": "seed_script"},
                )
                db.add(dev_user)
                print("✅ Created development user")
            else:
                print("ℹ️ Development user already exists")

            await db.flush()

            # Check if items already exist
            existing_items = await db.execute(
                select(Item).where(Item.org_id == dev_org_id).limit(1)
            )
            if existing_items.scalar_one_or_none():
                print("ℹ️ Demo items already exist, skipping creation")
                await db.commit()
                return

            # Create sample flashcards
            flashcards = [
                {
                    "type": "flashcard",
                    "tags": ["italian", "basics", "greetings"],
                    "difficulty": "intro",
                    "payload": {
                        "front": "Ciao",
                        "back": "Hello (informal)",
                        "examples": ["Ciao Maria!", "Ciao, come stai?"],
                        "pronunciation": "CHAH-oh",
                    },
                },
                {
                    "type": "flashcard",
                    "tags": ["italian", "basics", "greetings"],
                    "difficulty": "intro",
                    "payload": {
                        "front": "Buongiorno",
                        "back": "Good morning/Good day (formal)",
                        "examples": ["Buongiorno, signore!", "Buongiorno a tutti!"],
                        "pronunciation": "bwohn-JOR-noh",
                    },
                },
                {
                    "type": "flashcard",
                    "tags": ["italian", "numbers"],
                    "difficulty": "intro",
                    "payload": {
                        "front": "Uno",
                        "back": "One",
                        "examples": ["Un gelato", "Una pizza"],
                        "pronunciation": "OO-noh",
                    },
                },
                {
                    "type": "flashcard",
                    "tags": ["italian", "numbers"],
                    "difficulty": "intro",
                    "payload": {
                        "front": "Due",
                        "back": "Two",
                        "examples": ["Due caffè", "Due euro"],
                        "pronunciation": "DOO-eh",
                    },
                },
                {
                    "type": "flashcard",
                    "tags": ["italian", "verbs", "present"],
                    "difficulty": "core",
                    "payload": {
                        "front": "Io sono",
                        "back": "I am",
                        "examples": ["Io sono Mario", "Io sono italiana"],
                        "hints": ["From the verb 'essere' (to be)"],
                    },
                },
            ]

            # Create sample MCQs
            mcqs = [
                {
                    "type": "mcq",
                    "tags": ["physics", "mechanics", "units"],
                    "difficulty": "core",
                    "payload": {
                        "stem": "What is the SI unit of force?",
                        "options": [
                            {
                                "id": "A",
                                "text": "Newton",
                                "is_correct": True,
                                "rationale": "The Newton (N) is the SI unit of force, defined as kg⋅m/s².",
                            },
                            {
                                "id": "B",
                                "text": "Joule",
                                "is_correct": False,
                                "rationale": "Joule is the unit of energy, not force.",
                            },
                            {
                                "id": "C",
                                "text": "Watt",
                                "is_correct": False,
                                "rationale": "Watt is the unit of power, not force.",
                            },
                            {
                                "id": "D",
                                "text": "Pascal",
                                "is_correct": False,
                                "rationale": "Pascal is the unit of pressure, not force.",
                            },
                        ],
                    },
                },
                {
                    "type": "mcq",
                    "tags": ["physics", "mechanics", "kinematics"],
                    "difficulty": "core",
                    "payload": {
                        "stem": "If an object moves with constant velocity, what is its acceleration?",
                        "options": [
                            {
                                "id": "A",
                                "text": "Zero",
                                "is_correct": True,
                                "rationale": "Constant velocity means no change in velocity, so acceleration = 0.",
                            },
                            {
                                "id": "B",
                                "text": "Positive",
                                "is_correct": False,
                                "rationale": "Positive acceleration would mean increasing velocity.",
                            },
                            {
                                "id": "C",
                                "text": "Negative",
                                "is_correct": False,
                                "rationale": "Negative acceleration would mean decreasing velocity.",
                            },
                            {
                                "id": "D",
                                "text": "Cannot be determined",
                                "is_correct": False,
                                "rationale": "Constant velocity always means zero acceleration.",
                            },
                        ],
                    },
                },
                {
                    "type": "mcq",
                    "tags": ["math", "algebra", "equations"],
                    "difficulty": "intro",
                    "payload": {
                        "stem": "Solve for x: 2x + 3 = 11",
                        "options": [
                            {
                                "id": "A",
                                "text": "x = 4",
                                "is_correct": True,
                                "rationale": "2x = 11 - 3 = 8, so x = 4.",
                            },
                            {
                                "id": "B",
                                "text": "x = 5",
                                "is_correct": False,
                                "rationale": "If x = 5, then 2(5) + 3 = 13, not 11.",
                            },
                            {
                                "id": "C",
                                "text": "x = 3",
                                "is_correct": False,
                                "rationale": "If x = 3, then 2(3) + 3 = 9, not 11.",
                            },
                            {
                                "id": "D",
                                "text": "x = 7",
                                "is_correct": False,
                                "rationale": "If x = 7, then 2(7) + 3 = 17, not 11.",
                            },
                        ],
                    },
                },
            ]

            # Create sample short answer questions
            short_answers = [
                {
                    "type": "short_answer",
                    "tags": ["programming", "python", "basics"],
                    "difficulty": "intro",
                    "payload": {
                        "prompt": "What Python keyword is used to define a function?",
                        "expected": {"value": "def"},
                        "acceptable_patterns": ["^def$", "^DEF$"],
                        "grading": {"method": "exact_match", "case_sensitive": False},
                    },
                },
                {
                    "type": "short_answer",
                    "tags": ["geography", "capitals"],
                    "difficulty": "intro",
                    "payload": {
                        "prompt": "What is the capital of France?",
                        "expected": {"value": "Paris"},
                        "acceptable_patterns": ["^Paris$", "^paris$"],
                        "grading": {"method": "exact_match", "case_sensitive": False},
                    },
                },
            ]

            # Create sample cloze questions
            cloze_questions = [
                {
                    "type": "cloze",
                    "tags": ["english", "grammar", "tenses"],
                    "difficulty": "core",
                    "payload": {
                        "text": "I [[have been]] studying English for three years.",
                        "blanks": [
                            {
                                "id": 1,
                                "answers": ["have been"],
                                "alt_answers": ["have been"],
                                "case_sensitive": False,
                            }
                        ],
                        "context_note": "Present perfect continuous tense",
                    },
                }
            ]

            # Combine all items
            all_items = flashcards + mcqs + short_answers + cloze_questions

            # Create Item objects
            created_items = []
            for item_data in all_items:
                item = Item(
                    id=uuid.uuid4(),
                    org_id=dev_org_id,
                    type=item_data["type"],
                    tags=item_data["tags"],
                    difficulty=item_data["difficulty"],
                    payload=item_data["payload"],
                    content_hash=f"demo_hash_{len(created_items)}",
                    status="published",
                    created_by="seed_script",
                )
                db.add(item)
                created_items.append(item)

            await db.flush()
            print(f"✅ Created {len(created_items)} demo items")

            # Create some scheduler states (some items already studied)
            now = datetime.now(UTC)

            # Make some items due for review
            due_items = created_items[:3]  # First 3 items are due
            for i, item in enumerate(due_items):
                state = SchedulerState(
                    user_id=dev_user_id,
                    item_id=item.id,
                    stability=2.5 + i,  # Different stabilities
                    difficulty=0.5 + (i * 0.2),  # Different difficulties
                    due_at=now - timedelta(hours=i + 1),  # Overdue by different amounts
                    last_interval=1 + i,  # Different intervals
                    reps=2 + i,  # Different rep counts
                    lapses=0,
                    last_reviewed_at=now - timedelta(days=2),
                    scheduler_name="fsrs_v7",
                    version=1,
                )
                db.add(state)

            # Make some items not yet due (reviewed recently)
            future_items = created_items[3:6] if len(created_items) > 6 else []
            for i, item in enumerate(future_items):
                state = SchedulerState(
                    user_id=dev_user_id,
                    item_id=item.id,
                    stability=3.0 + i,
                    difficulty=0.3 + (i * 0.1),
                    due_at=now + timedelta(days=1 + i),  # Due in future
                    last_interval=2 + i,
                    reps=3 + i,
                    lapses=0,
                    last_reviewed_at=now - timedelta(hours=12),
                    scheduler_name="fsrs_v7",
                    version=1,
                )
                db.add(state)

            await db.flush()
            print(
                f"✅ Created scheduler states for {len(due_items)} due items and {len(future_items)} future items"
            )

            # Remaining items are "new" (no scheduler state)
            new_items = created_items[6:]
            print(f"ℹ️ {len(new_items)} items remain as 'new' (no scheduler state)")

            await db.commit()
            print("🎉 Demo data seeded successfully!")
            print("\n📋 Summary:")
            print(f"   • Organization: {dev_org_id}")
            print(f"   • User: {dev_user_id}")
            print(f"   • Total items: {len(created_items)}")
            print(f"   • Due for review: {len(due_items)}")
            print(f"   • Scheduled for future: {len(future_items)}")
            print(f"   • New items: {len(new_items)}")
            print("\n🚀 Try: learning-os review queue")

        except Exception as e:
            await db.rollback()
            print(f"❌ Error seeding data: {e}")
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_demo_data())
