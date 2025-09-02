"""
End-to-end workflow tests demonstrating complete user journeys.

These tests simulate realistic user scenarios from content creation
through the complete learning loop.
"""

from httpx import AsyncClient


class TestEndToEndWorkflows:
    """Test complete user workflows from start to finish."""

    # Sample learning content for realistic scenarios
    BIOLOGY_CONTENT = """
Cellular respiration is the process by which cells break down glucose to produce ATP (adenosine triphosphate), 
the universal energy currency of cells. This process occurs in three main stages: glycolysis, the Krebs cycle, 
and the electron transport chain.

Glycolysis takes place in the cytoplasm and converts one glucose molecule (C6H12O6) into two pyruvate molecules, 
producing 2 ATP and 2 NADH in the process. This process does not require oxygen and is therefore anaerobic.

The Krebs cycle, also known as the citric acid cycle, occurs in the mitochondrial matrix. Each pyruvate is 
converted to acetyl-CoA, which enters the cycle. For each glucose molecule, the cycle produces 6 NADH, 
2 FADH2, and 2 ATP molecules.

The electron transport chain is located in the inner mitochondrial membrane. Here, NADH and FADH2 are oxidized, 
and their electrons are passed through a series of protein complexes. This process produces approximately 
32-34 ATP molecules through oxidative phosphorylation. Oxygen serves as the final electron acceptor, 
forming water as a byproduct.

The overall equation for cellular respiration is: C6H12O6 + 6O2 → 6CO2 + 6H2O + ~36-38 ATP molecules.
The efficiency of cellular respiration is approximately 38%, much higher than glycolysis alone at 2%.
"""

    PHYSICS_CONTENT = """
Newton's laws of motion form the foundation of classical mechanics. The first law, known as the law of inertia, 
states that an object at rest stays at rest and an object in motion stays in motion at constant velocity unless 
acted upon by an unbalanced force.

The second law establishes the relationship between force, mass, and acceleration: F = ma. This means that the 
acceleration of an object is directly proportional to the net force acting on it and inversely proportional to 
its mass. A force of 10 Newtons applied to a 2 kilogram object will produce an acceleration of 5 m/s².

The third law states that for every action, there is an equal and opposite reaction. When you push against a wall 
with 100 Newtons of force, the wall pushes back on you with exactly 100 Newtons of force.

These laws apply to objects moving at speeds much less than the speed of light (3 × 10⁸ m/s) and in gravitational 
fields that are not extremely strong. At very high speeds or in strong gravitational fields, Einstein's theory 
of relativity becomes necessary.

Common applications include calculating projectile motion, where the horizontal velocity remains constant at 
9.8 m/s² while vertical acceleration due to gravity is -9.8 m/s², and analyzing collision dynamics using 
conservation of momentum principles.
"""

    async def test_complete_learning_workflow_biology(self, async_client: AsyncClient):
        """
        Test complete learning workflow: content generation → import → review → quiz → progress.

        This simulates a student learning biology content through the complete system.
        """

        # Step 1: Generate educational content from text
        print("\n=== Step 1: Content Generation ===")
        generation_request = {
            "text": self.BIOLOGY_CONTENT,
            "types": ["flashcard", "mcq", "cloze", "short_answer"],
            "count": 12,
            "difficulty": "core",
        }

        response = await async_client.post(
            "/v1/items/generate", json=generation_request
        )
        assert response.status_code == 200

        generation_result = response.json()["data"]
        print(f"Generated {len(generation_result['generated'])} items")
        print(f"Rejected {len(generation_result['rejected'])} items")
        print(
            f"Processing time: {generation_result['diagnostics']['processing_time_ms']}ms"
        )

        # Verify generation quality
        assert (
            len(generation_result["generated"]) >= 8
        ), "Should generate at least 8 quality items"

        generated_items = generation_result["generated"]
        generated_types = {item["type"] for item in generated_items}
        assert len(generated_types) >= 3, "Should generate diverse item types"

        # Step 2: Import additional content via markdown
        print("\n=== Step 2: Markdown Import ===")
        markdown_content = """
:::flashcard
Q: What is the primary function of mitochondria?
A: To produce ATP through cellular respiration
HINT: Often called the powerhouse of the cell
:::

:::mcq
STEM: How many ATP molecules are produced in glycolysis?
A) 1
*B) 2
C) 4
D) 36
:::

:::cloze
TEXT: The Krebs cycle occurs in the [[mitochondrial matrix]] and produces [[NADH]] and [[FADH2]].
:::
"""

        import_data = {"format": "markdown", "data": markdown_content}

        response = await async_client.post("/v1/items/import", json=import_data)
        assert response.status_code == 200

        import_result = response.json()["data"]
        staged_ids = import_result["staged_ids"]
        print(f"Imported {len(staged_ids)} items to staging")

        # Step 3: Review and approve staged content
        print("\n=== Step 3: Content Approval ===")

        # Check staged items
        response = await async_client.get("/v1/items/staged")
        assert response.status_code == 200
        staged_items = response.json()["data"]["items"]

        # Approve all staged items
        approval_data = {"ids": staged_ids}
        response = await async_client.post("/v1/items/approve", json=approval_data)
        assert response.status_code == 200

        approval_result = response.json()["data"]
        print(f"Approved {len(approval_result['approved'])} items")

        # Step 4: Search and filter available content
        print("\n=== Step 4: Content Discovery ===")

        # Search for ATP-related content
        response = await async_client.get("/v1/items?q=ATP&status=published")
        assert response.status_code == 200
        search_results = response.json()["data"]["items"]
        print(f"Found {len(search_results)} ATP-related items")

        # Filter by type
        response = await async_client.get("/v1/items?type=mcq&status=published")
        assert response.status_code == 200
        mcq_items = response.json()["data"]["items"]
        print(f"Found {len(mcq_items)} MCQ items")

        # Step 5: Start learning with review queue
        print("\n=== Step 5: Review Session ===")

        response = await async_client.get("/v1/queue?limit=10")
        assert response.status_code == 200

        queue_data = response.json()["data"]
        new_items = queue_data.get("new", [])
        due_items = queue_data.get("due", [])

        print(f"Review queue: {len(new_items)} new items, {len(due_items)} due items")
        assert len(new_items) >= 3, "Should have new items to review"

        # Review some new items
        reviews_completed = 0
        for item in new_items[:5]:  # Review first 5 items
            review_data = {
                "item_id": item["id"],
                "rating": (
                    3 if reviews_completed % 2 == 0 else 4
                ),  # Alternate between Good/Easy
                "correct": True,
                "latency_ms": 2000
                + (reviews_completed * 500),  # Varying response times
                "mode": "review",
            }

            response = await async_client.post("/v1/record", json=review_data)
            assert response.status_code == 200

            result = response.json()["data"]
            assert "updated_state" in result
            reviews_completed += 1

        print(f"Completed {reviews_completed} reviews")

        # Step 6: Practice with targeted quiz
        print("\n=== Step 6: Quiz Practice ===")

        # Start a biology-focused quiz
        quiz_request = {
            "mode": "drill",
            "params": {"length": 5, "tags": ["biology"], "time_limit_s": 300},
        }

        response = await async_client.post("/v1/quiz/start", json=quiz_request)
        assert response.status_code == 200

        quiz_data = response.json()["data"]
        quiz_id = quiz_data["quiz_id"]
        quiz_items = quiz_data["items"]

        print(f"Started quiz with {len(quiz_items)} items")

        # Complete the quiz
        correct_answers = 0
        for i, item in enumerate(quiz_items):
            # Simulate varied performance
            is_correct = i < 3  # Get first 3 right, miss last 2

            if item["type"] == "mcq":
                # For MCQ, find the correct option
                correct_option = None
                for option in item["render_payload"]["options"]:
                    if option.get("is_correct"):
                        correct_option = option["id"]
                        break

                selected = (
                    correct_option if is_correct else "a"
                )  # Wrong answer if supposed to be incorrect
                submit_data = {
                    "quiz_id": quiz_id,
                    "item_id": item["id"],
                    "response": {"selected_options": [selected]},
                }
            elif item["type"] == "flashcard":
                rating = 4 if is_correct else 2
                submit_data = {
                    "quiz_id": quiz_id,
                    "item_id": item["id"],
                    "response": {"rating": rating},
                }
            elif item["type"] == "cloze":
                # Provide correct or incorrect answers based on is_correct
                if is_correct:
                    submit_data = {
                        "quiz_id": quiz_id,
                        "item_id": item["id"],
                        "response": {
                            "answers": {
                                "1": "mitochondrial matrix",
                                "2": "NADH",
                                "3": "FADH2",
                            }
                        },
                    }
                else:
                    submit_data = {
                        "quiz_id": quiz_id,
                        "item_id": item["id"],
                        "response": {
                            "answers": {"1": "cytoplasm", "2": "ATP", "3": "glucose"}
                        },
                    }
            else:  # short_answer
                correct_answer = "38" if is_correct else "100"
                submit_data = {
                    "quiz_id": quiz_id,
                    "item_id": item["id"],
                    "response": {"answer": correct_answer},
                }

            response = await async_client.post("/v1/quiz/submit", json=submit_data)
            assert response.status_code == 200

            if is_correct:
                correct_answers += 1

        # Finish the quiz
        response = await async_client.post("/v1/quiz/finish", json={"quiz_id": quiz_id})
        assert response.status_code == 200

        quiz_result = response.json()["data"]
        print(f"Quiz completed - Score: {quiz_result['score']:.1%}")

        # Step 7: Check progress and analytics
        print("\n=== Step 7: Progress Analytics ===")

        # Get overview
        response = await async_client.get("/v1/progress/overview")
        assert response.status_code == 200

        overview = response.json()["data"]
        print("Learning progress:")
        print(f"  - Total items: {overview['total_items']}")
        print(f"  - Items reviewed: {overview['reviewed_items']}")
        print(f"  - 7-day accuracy: {overview['accuracy_7d']:.1%}")
        print(f"  - Avg response time: {overview['avg_latency_ms_7d']:.0f}ms")

        # Check weak areas
        response = await async_client.get("/v1/progress/weak_areas?top=3")
        assert response.status_code == 200

        weak_areas = response.json()["data"]
        print("Areas needing attention:")
        for tag_info in weak_areas["tags"][:3]:
            print(f"  - {tag_info['tag']}: {tag_info['accuracy']:.1%} accuracy")

        # Get forecast
        response = await async_client.get("/v1/progress/forecast?days=7")
        assert response.status_code == 200

        forecast = response.json()["data"]
        total_due = sum(day["due_count"] for day in forecast["by_day"])
        print(f"Next 7 days: {total_due} items due for review")

        # Verify learning progress metrics
        assert overview["total_items"] >= 10
        assert overview["reviewed_items"] >= 5
        assert overview["attempts_7d"] >= 5

        print("\n✅ Complete learning workflow successful!")
        return {
            "items_generated": len(generated_items),
            "items_imported": len(staged_ids),
            "reviews_completed": reviews_completed,
            "quiz_score": quiz_result["score"],
            "total_items": overview["total_items"],
        }

    async def test_content_creator_to_learner_workflow(self, async_client: AsyncClient):
        """
        Test workflow from content creator perspective: generate → refine → publish → track usage.
        """

        print("\n=== Content Creator Workflow ===")

        # Step 1: Generate initial content
        generation_request = {
            "text": self.PHYSICS_CONTENT,
            "types": ["mcq", "short_answer"],
            "count": 8,
            "difficulty": "intro",
        }

        response = await async_client.post(
            "/v1/items/generate", json=generation_request
        )
        assert response.status_code == 200

        result = response.json()["data"]
        generated_items = result["generated"]
        print(f"Generated {len(generated_items)} physics items")

        # Step 2: Review and edit generated content
        # (In reality, creator would review and edit, here we simulate approval)
        item_ids_to_approve = []

        # Get all draft items
        response = await async_client.get("/v1/items?status=draft")
        assert response.status_code == 200

        draft_items = response.json()["data"]["items"]
        for item in draft_items[:6]:  # Approve first 6
            item_ids_to_approve.append(item["id"])

        # Bulk approve items (simulating editorial approval)
        if item_ids_to_approve:
            approval_data = {"ids": item_ids_to_approve}
            response = await async_client.post("/v1/items/approve", json=approval_data)
            assert response.status_code == 200
            print(f"Approved {len(item_ids_to_approve)} items for publication")

        # Step 3: Test content discovery by learners
        response = await async_client.get("/v1/items?tags=physics&status=published")
        assert response.status_code == 200

        physics_items = response.json()["data"]["items"]
        print(f"Published physics items available: {len(physics_items)}")

        # Step 4: Simulate learner usage
        # Get some items into the learning system
        response = await async_client.get("/v1/queue?mix_new=0.8&limit=4")
        assert response.status_code == 200

        queue = response.json()["data"]
        items_to_study = queue.get("new", [])

        # Simulate study sessions
        if items_to_study:
            for item in items_to_study[:3]:
                review_data = {
                    "item_id": item["id"],
                    "rating": 3,
                    "correct": True,
                    "latency_ms": 3000,
                    "mode": "review",
                }

                response = await async_client.post("/v1/record", json=review_data)
                assert response.status_code == 200

        # Step 5: Content creator checks analytics
        response = await async_client.get("/v1/progress/overview")
        assert response.status_code == 200

        overview = response.json()["data"]
        print("Content usage analytics:")
        print(f"  - Items being studied: {overview['reviewed_items']}")
        print(f"  - Recent activity: {overview['attempts_7d']} attempts")

        print("✅ Content creator workflow complete!")

    async def test_spaced_repetition_learning_cycle(self, async_client: AsyncClient):
        """
        Test the spaced repetition learning cycle over multiple sessions.
        """

        print("\n=== Spaced Repetition Cycle Test ===")

        # Set up initial content
        markdown_content = """
:::flashcard
Q: What is the formula for kinetic energy?
A: KE = ½mv²
HINT: Involves mass and velocity squared
:::

:::flashcard  
Q: What is Newton's second law?
A: F = ma (Force equals mass times acceleration)
:::

:::mcq
STEM: What is the acceleration due to gravity on Earth?
A) 9.8 m/s
*B) 9.8 m/s²
C) 9.8 m/s³
D) 98 m/s²
:::
"""

        # Import and approve content
        import_data = {"format": "markdown", "data": markdown_content}
        response = await async_client.post("/v1/items/import", json=import_data)
        assert response.status_code == 200

        staged_ids = response.json()["data"]["staged_ids"]

        approval_data = {"ids": staged_ids}
        response = await async_client.post("/v1/items/approve", json=approval_data)
        assert response.status_code == 200

        print(f"Set up {len(staged_ids)} items for spaced repetition")

        # Session 1: Initial learning (all items are new)
        print("\n--- Session 1: Initial Learning ---")
        response = await async_client.get("/v1/queue")
        assert response.status_code == 200

        queue = response.json()["data"]
        new_items = queue["new"][:3]  # Study 3 new items

        session_1_results = []
        for item in new_items:
            # Simulate different performance levels
            rating = (
                3 if "formula" in str(item) else 4
            )  # Harder on formula, easier on others

            review_data = {
                "item_id": item["id"],
                "rating": rating,
                "correct": rating >= 3,
                "latency_ms": 2500,
                "mode": "review",
            }

            response = await async_client.post("/v1/record", json=review_data)
            assert response.status_code == 200

            result = response.json()["data"]
            session_1_results.append(result["updated_state"])

        print(f"Session 1: Reviewed {len(session_1_results)} new items")

        # Session 2: Mixed review (some items may be due, some still new)
        print("\n--- Session 2: Mixed Review ---")
        response = await async_client.get("/v1/queue")
        assert response.status_code == 200

        queue = response.json()["data"]
        due_items = queue.get("due", [])
        new_items = queue.get("new", [])

        print(f"Session 2: {len(due_items)} due items, {len(new_items)} new items")

        # Review due items with better performance
        for item in due_items[:2]:
            review_data = {
                "item_id": item["id"],
                "rating": 4,  # Better performance in second session
                "correct": True,
                "latency_ms": 1800,
                "mode": "review",
            }

            response = await async_client.post("/v1/record", json=review_data)
            assert response.status_code == 200

        # Session 3: Check learning progress and intervals
        print("\n--- Session 3: Progress Check ---")
        response = await async_client.get("/v1/progress/overview")
        assert response.status_code == 200

        overview = response.json()["data"]
        print("Learning progress after multiple sessions:")
        print(f"  - Total reviews: {overview['attempts_7d']}")
        print(f"  - Accuracy: {overview['accuracy_7d']:.1%}")
        print(f"  - Items in system: {overview['total_items']}")
        print(f"  - Items reviewed: {overview['reviewed_items']}")

        # Verify spaced repetition is working
        assert overview["attempts_7d"] >= 5
        assert overview["reviewed_items"] >= 3
        assert overview["total_items"] >= 3

        print("✅ Spaced repetition cycle working correctly!")

    async def test_multi_modal_learning_session(self, async_client: AsyncClient):
        """
        Test a comprehensive learning session using all item types and modes.
        """

        print("\n=== Multi-Modal Learning Session ===")

        # Create diverse content
        diverse_items = [
            {
                "type": "flashcard",
                "payload": {
                    "front": "What is photosynthesis?",
                    "back": "Process of converting light to energy",
                },
                "tags": ["biology", "plants"],
                "difficulty": "intro",
            },
            {
                "type": "mcq",
                "payload": {
                    "stem": "Which organelle performs photosynthesis?",
                    "options": [
                        {"id": "a", "text": "Nucleus", "is_correct": False},
                        {"id": "b", "text": "Chloroplast", "is_correct": True},
                        {"id": "c", "text": "Mitochondria", "is_correct": False},
                    ],
                },
                "tags": ["biology", "cells"],
                "difficulty": "core",
            },
            {
                "type": "cloze",
                "payload": {
                    "text": "The equation for photosynthesis is [[6CO2]] + [[6H2O]] → [[C6H12O6]] + [[6O2]]",
                    "blanks": [
                        {"id": "1", "answers": ["6CO2"], "case_sensitive": False},
                        {"id": "2", "answers": ["6H2O"], "case_sensitive": False},
                        {
                            "id": "3",
                            "answers": ["C6H12O6", "glucose"],
                            "case_sensitive": False,
                        },
                        {"id": "4", "answers": ["6O2"], "case_sensitive": False},
                    ],
                },
                "tags": ["biology", "chemistry"],
                "difficulty": "stretch",
            },
        ]

        # Create all items
        created_items = []
        for item_data in diverse_items:
            response = await async_client.post("/v1/items", json=item_data)
            assert response.status_code == 201
            created_items.append(response.json()["data"])

        # Approve all items
        item_ids = [item["id"] for item in created_items]
        approval_data = {"ids": item_ids}
        response = await async_client.post("/v1/items/approve", json=approval_data)
        assert response.status_code == 200

        print(f"Created {len(created_items)} diverse learning items")

        # Learning Mode 1: Individual review
        print("\n--- Individual Review Mode ---")
        response = await async_client.get("/v1/queue?limit=5")
        assert response.status_code == 200

        queue = response.json()["data"]
        items_to_review = queue.get("new", [])

        individual_scores = []
        for item in items_to_review:
            # Review each item individually
            review_data = {
                "item_id": item["id"],
                "rating": 3,
                "correct": True,
                "latency_ms": 2000,
                "mode": "review",
            }

            response = await async_client.post("/v1/record", json=review_data)
            assert response.status_code == 200
            individual_scores.append(3)

        # Learning Mode 2: Quiz-based practice
        print("\n--- Quiz Practice Mode ---")
        quiz_request = {
            "mode": "drill",
            "params": {"length": 3, "tags": ["biology"], "time_limit_s": 180},
        }

        response = await async_client.post("/v1/quiz/start", json=quiz_request)
        assert response.status_code == 200

        quiz_data = response.json()["data"]
        quiz_id = quiz_data["quiz_id"]

        # Complete quiz with realistic responses
        for item in quiz_data["items"]:
            if item["type"] == "mcq":
                submit_data = {
                    "quiz_id": quiz_id,
                    "item_id": item["id"],
                    "response": {"selected_options": ["b"]},  # Chloroplast
                }
            elif item["type"] == "cloze":
                submit_data = {
                    "quiz_id": quiz_id,
                    "item_id": item["id"],
                    "response": {
                        "answers": {
                            "1": "6CO2",
                            "2": "6H2O",
                            "3": "glucose",
                            "4": "6O2",
                        }
                    },
                }
            else:  # flashcard
                submit_data = {
                    "quiz_id": quiz_id,
                    "item_id": item["id"],
                    "response": {"rating": 4},
                }

            response = await async_client.post("/v1/quiz/submit", json=submit_data)
            assert response.status_code == 200

        response = await async_client.post("/v1/quiz/finish", json={"quiz_id": quiz_id})
        assert response.status_code == 200

        quiz_result = response.json()["data"]
        print(f"Quiz completed with score: {quiz_result['score']:.1%}")

        # Learning Mode 3: Targeted weak area practice
        print("\n--- Weak Area Focus ---")
        response = await async_client.get("/v1/progress/weak_areas?top=2")
        assert response.status_code == 200

        weak_areas = response.json()["data"]
        if weak_areas["tags"]:
            weak_tag = weak_areas["tags"][0]["tag"]
            print(f"Focusing on weak area: {weak_tag}")

            # Practice items in weak area
            response = await async_client.get(
                f"/v1/items?tags={weak_tag}&status=published"
            )
            assert response.status_code == 200

        # Final assessment
        response = await async_client.get("/v1/progress/overview")
        assert response.status_code == 200

        final_overview = response.json()["data"]
        print("\nMulti-modal session results:")
        print(f"  - Total attempts: {final_overview['attempts_7d']}")
        print(f"  - Overall accuracy: {final_overview['accuracy_7d']:.1%}")
        print(f"  - Avg response time: {final_overview['avg_latency_ms_7d']:.0f}ms")

        # Verify comprehensive learning occurred
        assert final_overview["attempts_7d"] >= 6
        assert final_overview["reviewed_items"] >= 3
        assert quiz_result["score"] >= 0.5

        print("✅ Multi-modal learning session successful!")

        return {
            "individual_reviews": len(individual_scores),
            "quiz_score": quiz_result["score"],
            "final_accuracy": final_overview["accuracy_7d"],
            "total_attempts": final_overview["attempts_7d"],
        }
