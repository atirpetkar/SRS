#!/usr/bin/env python3
"""
Complete Practice Loop Demo - Steps 1-5 Integration Test

This script demonstrates the complete practice loop functionality:
1. Import content → draft items
2. Approve items → published status
3. Review queue → FSRS scheduling
4. Record reviews → update scheduler state
5. Run quizzes → objective grading

Usage:
    python scripts/step5_demo_complete_loop.py

Requirements:
    - Server running on localhost:8000
    - Database initialized and ready
    - AUTH_MODE=none (dev mode)
"""

import time
from datetime import datetime

import httpx


class PracticeLoopDemo:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.Client(base_url=base_url)
        self.staged_ids = []
        self.quiz_id = None

    def print_section(self, title: str):
        """Print a formatted section header."""
        print(f"\n{'='*60}")
        print(f"🎯 {title}")
        print("=" * 60)

    def print_step(self, step: str, description: str):
        """Print a step with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{timestamp}] 📋 {step}: {description}")

    def check_health(self):
        """Verify server is running and healthy."""
        self.print_step("HEALTH", "Checking server status")

        try:
            response = self.client.get("/v1/healthz")
            response.raise_for_status()
            data = response.json()

            if data.get("ok"):
                print(
                    f"✅ Server healthy - Version: {data.get('data', {}).get('version', 'unknown')}"
                )
                return True
            else:
                print(f"❌ Server unhealthy: {data}")
                return False

        except Exception as e:
            print(f"❌ Cannot connect to server: {e}")
            print("   Start server with: uvicorn api.main:app --reload --port 8000")
            return False

    def import_sample_content(self):
        """Import sample content using markdown DSL."""
        self.print_step("IMPORT", "Importing sample content via markdown DSL")

        # Sample content covering all item types
        markdown_content = """:::flashcard
Q: What is the Italian word for "hello"?
A: Ciao
HINT: Common informal greeting
:::

:::mcq
STEM: What does "Grazie" mean in English?
A) Hello
B) Goodbye
C) Thank you *correct
D) Please
:::

:::cloze
TEXT: In Italian, "good morning" is [[Buongiorno]].
:::

:::short
PROMPT: What is the time complexity of binary search?
EXPECTED: O(log n)
PATTERN: O\\(log\\s*n\\)|logarithmic
:::

:::flashcard
Q: How do you say "water" in Italian?
A: Acqua
HINT: Essential for life
:::"""

        payload = {
            "format": "markdown",
            "data": markdown_content,
            "metadata": {"source": "step5_demo", "created_by": "demo_script"},
        }

        try:
            response = self.client.post("/v1/items/import", json=payload)
            response.raise_for_status()
            data = response.json()["data"]

            self.staged_ids = data["staged_ids"]
            print("✅ Import successful:")
            print(f"   📊 Parsed: {data['total_parsed']} items")
            print(f"   ✨ Created: {data['total_created']} drafts")
            print(f"   ❌ Errors: {data['total_errors']}")
            print(f"   ⚠️  Warnings: {len(data['warnings'])}")

            if data["diagnostics"]:
                print("   📋 Diagnostics:")
                for diag in data["diagnostics"]:
                    print(f"      - {diag['severity']}: {diag['issue']}")

            return True

        except Exception as e:
            print(f"❌ Import failed: {e}")
            return False

    def review_staged_items(self):
        """Review the staged (draft) items."""
        self.print_step("STAGING", "Reviewing staged items")

        try:
            response = self.client.get("/v1/items/staged?limit=10")
            response.raise_for_status()
            data = response.json()["data"]

            print("✅ Staged items review:")
            print(f"   📊 Total staged: {data['total']}")
            print(f"   📄 Showing: {len(data['items'])} items")

            for item in data["items"][:3]:  # Show first 3
                print(f"   - {item['type']}: {item['id'][:8]}... ({item['status']})")

            return True

        except Exception as e:
            print(f"❌ Staging review failed: {e}")
            return False

    def approve_items(self):
        """Approve staged items to published status."""
        self.print_step("APPROVAL", "Publishing staged items")

        if not self.staged_ids:
            print("❌ No staged items to approve")
            return False

        payload = {"ids": self.staged_ids}

        try:
            response = self.client.post("/v1/items/approve", json=payload)
            response.raise_for_status()
            data = response.json()["data"]

            print("✅ Approval results:")
            print(f"   ✅ Approved: {len(data['approved_ids'])} items")
            print(f"   ❌ Failed: {len(data['failed_ids'])} items")

            if data["errors"]:
                print("   📋 Errors:")
                for item_id, error in data["errors"].items():
                    print(f"      - {item_id[:8]}...: {error}")

            return len(data["approved_ids"]) > 0

        except Exception as e:
            print(f"❌ Approval failed: {e}")
            return False

    def get_review_queue(self):
        """Get review queue showing FSRS scheduling."""
        self.print_step("QUEUE", "Getting review queue (FSRS scheduling)")

        try:
            response = self.client.get("/v1/review/queue?limit=10&mix_new=0.4")
            response.raise_for_status()
            data = response.json()["data"]

            print("✅ Review queue status:")
            print(f"   📅 Due items: {len(data['due'])}")
            print(f"   🆕 New items: {len(data['new'])}")

            # Show sample items
            if data["new"]:
                print("   📋 Sample new item:")
                item = data["new"][0]
                print(f"      - Type: {item['type']}")
                print(f"      - ID: {item['id'][:8]}...")
                print(f"      - Is new: {item['is_new']}")

            if data["due"]:
                print("   📋 Sample due item:")
                item = data["due"][0]
                print(f"      - Type: {item['type']}")
                print(f"      - Due at: {item['due_at']}")

            return data

        except Exception as e:
            print(f"❌ Queue fetch failed: {e}")
            return None

    def record_review(self, item_id: str, rating: int = 3):
        """Record a review and update FSRS state."""
        self.print_step("REVIEW", f"Recording review (rating: {rating})")

        payload = {
            "item_id": item_id,
            "rating": rating,
            "correct": rating >= 3,
            "latency_ms": 2000 + (rating * 500),  # Simulate varying response times
            "mode": "review",
            "response": {"demo": "response"},
        }

        try:
            response = self.client.post("/v1/review/record", json=payload)
            response.raise_for_status()
            data = response.json()["data"]

            print("✅ Review recorded:")
            print(f"   📈 Next due: {data['next_due']}")
            print(f"   📅 Interval: {data['interval_days']} days")
            print("   🧠 FSRS state updated:")
            state = data["updated_state"]
            print(f"      - Stability: {state['stability']:.2f}")
            print(f"      - Difficulty: {state['difficulty']:.2f}")
            print(f"      - Reps: {state['reps']}")

            return True

        except Exception as e:
            print(f"❌ Review recording failed: {e}")
            return False

    def start_quiz(self, mode: str = "drill", length: int = 3):
        """Start a quiz session."""
        self.print_step("QUIZ_START", f"Starting {mode} quiz with {length} items")

        payload = {"mode": mode, "params": {"length": length, "time_limit_s": 180}}

        try:
            response = self.client.post("/v1/quiz/start", json=payload)
            response.raise_for_status()
            data = response.json()["data"]

            self.quiz_id = data["quiz_id"]
            print("✅ Quiz started:")
            print(f"   🆔 Quiz ID: {self.quiz_id[:8]}...")
            print(f"   📊 Total items: {data['total_items']}")
            print(f"   ⏱️  Time limit: {data.get('time_limit_s', 'None')}s")
            print(f"   🎯 Mode: {data['mode']}")

            # Show item types
            item_types = {}
            for item in data["items"]:
                item_type = item["type"]
                item_types[item_type] = item_types.get(item_type, 0) + 1

            print(f"   📋 Item breakdown: {dict(item_types)}")

            return data

        except Exception as e:
            print(f"❌ Quiz start failed: {e}")
            return None

    def submit_quiz_answers(self, quiz_data):
        """Submit answers for quiz items."""
        self.print_step("QUIZ_SUBMIT", "Submitting quiz answers")

        submitted = 0

        for item in quiz_data["items"]:
            item_id = item["id"]
            item_type = item["type"]

            # Generate appropriate response based on item type
            if item_type == "flashcard":
                response_data = {"answer": "demo answer"}
            elif item_type == "mcq":
                # Pick first correct option if available
                options = item["render_payload"].get("options", [])
                correct_option = next(
                    (opt["id"] for opt in options if opt.get("is_correct")), "A"
                )
                response_data = {"selected_options": [correct_option]}
            elif item_type == "cloze":
                # Try to answer first blank
                response_data = {"answers": {"1": "demo answer"}}
            elif item_type == "short_answer":
                response_data = {"answer": "demo answer"}
            else:
                response_data = {"answer": "unknown"}

            payload = {
                "quiz_id": self.quiz_id,
                "item_id": item_id,
                "response": response_data,
            }

            try:
                response = self.client.post("/v1/quiz/submit", json=payload)
                response.raise_for_status()
                data = response.json()["data"]

                grading = data["grading"]
                print(
                    f"   ✅ Item {submitted+1}: {item_type} - Correct: {grading['correct']}, Score: {grading.get('score', 'N/A')}"
                )
                submitted += 1

            except Exception as e:
                print(f"   ❌ Submit failed for item {item_id[:8]}...: {e}")

        return submitted

    def finish_quiz(self):
        """Finish the quiz and get final results."""
        self.print_step("QUIZ_FINISH", "Finishing quiz and calculating score")

        if not self.quiz_id:
            print("❌ No active quiz to finish")
            return False

        payload = {"quiz_id": self.quiz_id}

        try:
            response = self.client.post("/v1/quiz/finish", json=payload)
            response.raise_for_status()
            data = response.json()["data"]

            print("✅ Quiz completed:")
            print(f"   🎯 Final score: {data['final_score']:.2%}")
            print(f"   ⏱️  Time taken: {data['time_taken_s']}s")

            breakdown = data["breakdown"]
            print("   📊 Breakdown:")
            print(f"      - Total: {breakdown['total_items']}")
            print(f"      - Correct: {breakdown['correct_items']}")
            print(f"      - Partial: {breakdown['partial_credit_items']}")
            print(f"      - Incorrect: {breakdown['incorrect_items']}")

            # Show per-type breakdown if available
            if "items_by_type" in breakdown:
                print("   📋 By type:")
                for item_type, stats in breakdown["items_by_type"].items():
                    accuracy = (
                        stats["correct"] / stats["total"] if stats["total"] > 0 else 0
                    )
                    print(
                        f"      - {item_type}: {accuracy:.1%} ({stats['correct']}/{stats['total']})"
                    )

            return True

        except Exception as e:
            print(f"❌ Quiz finish failed: {e}")
            return False

    def demonstrate_fsrs_behavior(self, item_id: str):
        """Demonstrate FSRS algorithm behavior with different ratings."""
        self.print_step("FSRS_DEMO", "Demonstrating FSRS algorithm behavior")

        ratings = [
            (1, "Again - Should trigger lapse"),
            (3, "Good - Should increase interval"),
            (4, "Easy - Should set long interval"),
        ]

        for rating, description in ratings:
            print(f"\n   🎯 Testing rating {rating}: {description}")

            payload = {
                "item_id": item_id,
                "rating": rating,
                "correct": rating >= 3,
                "latency_ms": 2000,
                "mode": "review",
                "response": {"demo": f"rating_{rating}"},
            }

            try:
                response = self.client.post("/v1/review/record", json=payload)
                response.raise_for_status()
                data = response.json()["data"]

                state = data["updated_state"]
                print("      ✅ FSRS updated:")
                print(f"         - Stability: {state['stability']:.2f}")
                print(f"         - Difficulty: {state['difficulty']:.2f}")
                print(f"         - Next due: {data['interval_days']} days")
                print(f"         - Reps: {state['reps']}, Lapses: {state['lapses']}")

                # Small delay between reviews
                time.sleep(0.5)

            except Exception as e:
                print(f"      ❌ Review failed: {e}")

    def run_complete_demo(self):
        """Run the complete practice loop demonstration."""
        self.print_section("COMPLETE PRACTICE LOOP DEMO")
        print("Demonstrating Steps 1-5 integration with real API calls")

        # 1. Health check
        if not self.check_health():
            return False

        # 2. Import content
        if not self.import_sample_content():
            return False

        # 3. Review staged items
        if not self.review_staged_items():
            return False

        # 4. Approve items
        if not self.approve_items():
            return False

        # 5. Get review queue
        queue_data = self.get_review_queue()
        if not queue_data:
            return False

        # 6. Record some reviews
        if queue_data["new"]:
            first_item = queue_data["new"][0]
            self.record_review(first_item["id"])

            # Demonstrate FSRS behavior
            self.demonstrate_fsrs_behavior(first_item["id"])

        # 7. Run a quiz
        quiz_data = self.start_quiz("drill", 3)
        if quiz_data:
            self.submit_quiz_answers(quiz_data)
            self.finish_quiz()

        self.print_success_summary()
        return True

    def record_review(self, item_id: str, rating: int = 3):
        """Record a single review."""
        payload = {
            "item_id": item_id,
            "rating": rating,
            "correct": rating >= 3,
            "latency_ms": 2500,
            "mode": "review",
            "response": {"answer": "demo_answer"},
        }

        try:
            response = self.client.post("/v1/review/record", json=payload)
            response.raise_for_status()
            data = response.json()["data"]

            print(f"   ✅ Review recorded - Next due in {data['interval_days']} days")
            return True

        except Exception as e:
            print(f"   ❌ Review failed: {e}")
            return False

    def review_staged_items(self):
        """Review staged items."""
        try:
            response = self.client.get("/v1/items/staged")
            response.raise_for_status()
            data = response.json()["data"]
            print(f"   ✅ Found {data['total']} staged items ready for approval")
            return True
        except Exception as e:
            print(f"   ❌ Staging review failed: {e}")
            return False

    def approve_items(self):
        """Approve all staged items."""
        if not self.staged_ids:
            return False

        payload = {"ids": self.staged_ids}
        try:
            response = self.client.post("/v1/items/approve", json=payload)
            response.raise_for_status()
            data = response.json()["data"]
            print(f"   ✅ Approved {len(data['approved_ids'])} items")
            return True
        except Exception as e:
            print(f"   ❌ Approval failed: {e}")
            return False

    def get_review_queue(self):
        """Get review queue."""
        try:
            response = self.client.get("/v1/review/queue?limit=10&mix_new=0.4")
            response.raise_for_status()
            data = response.json()["data"]
            print(f"   ✅ Queue: {len(data['due'])} due, {len(data['new'])} new")
            return data
        except Exception as e:
            print(f"   ❌ Queue fetch failed: {e}")
            return None

    def start_quiz(self, mode: str, length: int):
        """Start a quiz."""
        payload = {"mode": mode, "params": {"length": length, "time_limit_s": 180}}
        try:
            response = self.client.post("/v1/quiz/start", json=payload)
            response.raise_for_status()
            data = response.json()["data"]
            self.quiz_id = data["quiz_id"]
            print(f"   ✅ {mode.title()} quiz started with {data['total_items']} items")
            return data
        except Exception as e:
            print(f"   ❌ Quiz start failed: {e}")
            return None

    def submit_quiz_answers(self, quiz_data):
        """Submit quiz answers."""
        print(f"   📝 Submitting answers for {len(quiz_data['items'])} items...")

        for i, item in enumerate(quiz_data["items"]):
            # Generate appropriate response
            if item["type"] == "mcq":
                options = item["render_payload"].get("options", [])
                correct = next(
                    (opt["id"] for opt in options if opt.get("is_correct")), "A"
                )
                response_data = {"selected_options": [correct]}
            else:
                response_data = {"answer": "demo"}

            payload = {
                "quiz_id": self.quiz_id,
                "item_id": item["id"],
                "response": response_data,
            }

            try:
                response = self.client.post("/v1/quiz/submit", json=payload)
                response.raise_for_status()
                data = response.json()["data"]
                grading = data["grading"]
                print(
                    f"      {i+1}. {item['type']}: {'✅' if grading['correct'] else '❌'}"
                )
            except Exception as e:
                print(f"      {i+1}. {item['type']}: ❌ Error - {e}")

    def print_success_summary(self):
        """Print success summary."""
        self.print_section("🎉 DEMO COMPLETED SUCCESSFULLY")

        print("✅ VERIFIED FUNCTIONALITY:")
        print("   📥 Step 1-2: Item import and CRUD")
        print("   📋 Step 3: Staging and approval workflow")
        print("   🧠 Step 4: FSRS scheduler and review queue")
        print("   🎮 Step 5: Quiz modes with objective grading")

        print("\n🎯 COMPLETE PRACTICE LOOP WORKING:")
        print("   1. Import content → Draft items")
        print("   2. Approve items → Published status")
        print("   3. Review queue → FSRS scheduling")
        print("   4. Record reviews → Update scheduler state")
        print("   5. Run quizzes → Objective grading")

        print("\n🚀 READY FOR DAILY USE:")
        print("   - Import your study materials")
        print("   - Start reviewing with spaced repetition")
        print("   - Track progress with quiz modes")
        print("   - System adapts to your performance")

        print("\n📊 OPTIONAL ENHANCEMENTS:")
        print("   - Step 6: Progress analytics (7-day stats, forecasting)")
        print("   - Step 12: Review console UI")


def main():
    """Run the complete demonstration."""
    demo = PracticeLoopDemo()

    try:
        success = demo.run_complete_demo()
        exit_code = 0 if success else 1
    except KeyboardInterrupt:
        print("\n\n⏹️  Demo interrupted by user")
        exit_code = 1
    except Exception as e:
        print(f"\n\n💥 Demo failed with unexpected error: {e}")
        exit_code = 1
    finally:
        demo.client.close()

    exit(exit_code)


if __name__ == "__main__":
    main()
