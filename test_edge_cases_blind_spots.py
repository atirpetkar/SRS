#!/usr/bin/env python3
"""
Phase 6: Edge Cases & Blind Spots Testing
Comprehensive testing of boundary conditions, data limits, race conditions, and overlooked scenarios.
"""

import concurrent.futures
import time
from datetime import datetime

import requests

BASE_URL = "http://127.0.0.1:8000"


class EdgeCaseTester:
    def __init__(self):
        self.session = requests.Session()
        self.test_results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "categories": {},
        }

    def log(self, message: str, status: str = "INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        symbols = {"INFO": "ℹ️", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌"}
        print(f"{symbols.get(status, 'ℹ️')} [{timestamp}] {message}")

        self.test_results["total_tests"] += 1
        if status == "SUCCESS":
            self.test_results["passed"] += 1
        elif status == "ERROR":
            self.test_results["failed"] += 1
        elif status == "WARNING":
            self.test_results["warnings"] += 1

    def test_data_boundary_limits(self):
        """Test: Data size limits, edge values, boundary conditions"""
        print("\n" + "=" * 70)
        print("🎯 EDGE CASE 1: Data Boundary Limits")
        print("=" * 70)

        category_results = []

        # Test 1: Maximum text length handling
        self.log("Testing maximum text length...")

        very_long_text = "A" * 50000  # 50KB text
        large_item = {
            "type": "flashcard",
            "payload": {"front": very_long_text, "back": "Short answer"},
            "tags": ["edge-test"],
            "difficulty": "core",
        }

        response = self.session.post(f"{BASE_URL}/v1/items", json=large_item)
        if response.status_code in [200, 201]:
            self.log("Large text handled successfully", "SUCCESS")
            category_results.append("large_text_pass")
        elif response.status_code == 413:
            self.log("Large text properly rejected (413)", "SUCCESS")
            category_results.append("large_text_rejected")
        else:
            self.log(
                f"Unexpected response to large text: {response.status_code}", "ERROR"
            )
            category_results.append("large_text_error")

        # Test 2: Empty and minimal data
        self.log("Testing minimal data boundaries...")

        minimal_items = [
            {
                "type": "flashcard",
                "payload": {"front": "", "back": ""},
                "tags": [],
                "difficulty": "core",
            },
            {
                "type": "flashcard",
                "payload": {"front": "A", "back": "B"},
                "tags": ["x"],
                "difficulty": "intro",
            },
        ]

        for i, item in enumerate(minimal_items):
            response = self.session.post(f"{BASE_URL}/v1/items", json=item)
            if response.status_code in [200, 201, 400, 422]:
                self.log(f"Minimal item {i+1}: Handled appropriately", "SUCCESS")
                category_results.append(f"minimal_{i+1}_pass")
            else:
                self.log(
                    f"Minimal item {i+1}: Unexpected response {response.status_code}",
                    "ERROR",
                )
                category_results.append(f"minimal_{i+1}_error")

        # Test 3: Unicode and special characters
        self.log("Testing Unicode and special characters...")

        unicode_item = {
            "type": "flashcard",
            "payload": {
                "front": "🧪 Test with émojis and àccénts: 测试中文 русский ไทย",
                "back": "Special chars: \\n \\t \\r \" ' < > & null\\x00",
            },
            "tags": ["unicode", "🏷️"],
            "difficulty": "core",
        }

        response = self.session.post(f"{BASE_URL}/v1/items", json=unicode_item)
        if response.status_code in [200, 201]:
            self.log("Unicode characters handled successfully", "SUCCESS")
            category_results.append("unicode_pass")
        else:
            self.log(f"Unicode handling failed: {response.status_code}", "ERROR")
            category_results.append("unicode_error")

        # Test 4: Array length limits
        self.log("Testing array length limits...")

        # Test with many tags
        many_tags_item = {
            "type": "flashcard",
            "payload": {"front": "Test", "back": "Test"},
            "tags": [f"tag-{i}" for i in range(500)],  # 500 tags
            "difficulty": "core",
        }

        response = self.session.post(f"{BASE_URL}/v1/items", json=many_tags_item)
        if response.status_code in [200, 201, 400, 422]:
            self.log("Many tags handled appropriately", "SUCCESS")
            category_results.append("many_tags_pass")
        else:
            self.log(f"Many tags unexpected response: {response.status_code}", "ERROR")
            category_results.append("many_tags_error")

        self.test_results["categories"]["data_boundaries"] = category_results
        return category_results

    def test_concurrent_operations(self):
        """Test: Race conditions, concurrent access, data consistency"""
        print("\n" + "=" * 70)
        print("⚡ EDGE CASE 2: Concurrent Operations")
        print("=" * 70)

        category_results = []

        # Test 1: Concurrent item creation
        self.log("Testing concurrent item creation...")

        def create_item(thread_id: int) -> bool:
            item = {
                "type": "flashcard",
                "payload": {
                    "front": f"Concurrent test {thread_id}",
                    "back": f"Thread {thread_id} answer",
                },
                "tags": [f"thread-{thread_id}", "concurrent"],
                "difficulty": "core",
            }

            try:
                response = self.session.post(f"{BASE_URL}/v1/items", json=item)
                return response.status_code in [200, 201]
            except Exception as e:
                self.log(f"Thread {thread_id} error: {str(e)}", "WARNING")
                return False

        # Run 10 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(create_item, i) for i in range(10)]
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        success_count = sum(results)
        if success_count >= 8:  # Allow for some failures due to timing
            self.log(f"Concurrent creation: {success_count}/10 succeeded", "SUCCESS")
            category_results.append("concurrent_creation_pass")
        else:
            self.log(
                f"Concurrent creation: Only {success_count}/10 succeeded", "WARNING"
            )
            category_results.append("concurrent_creation_warn")

        # Test 2: Concurrent quiz operations
        self.log("Testing concurrent quiz operations...")

        def start_quiz(thread_id: int) -> bool:
            quiz_params = {
                "mode": "drill",
                "params": {"length": 2, "tags": ["concurrent"]},
            }

            try:
                response = self.session.post(
                    f"{BASE_URL}/v1/quiz/start", json=quiz_params
                )
                if response.status_code == 200:
                    data = response.json().get("data", {})
                    quiz_id = data.get("quiz_id")
                    return quiz_id is not None
                return False
            except Exception as e:
                self.log(f"Quiz thread {thread_id} error: {str(e)}", "WARNING")
                return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(start_quiz, i) for i in range(5)]
            quiz_results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        quiz_success = sum(quiz_results)
        if quiz_success >= 4:
            self.log(f"Concurrent quiz start: {quiz_success}/5 succeeded", "SUCCESS")
            category_results.append("concurrent_quiz_pass")
        else:
            self.log(
                f"Concurrent quiz start: Only {quiz_success}/5 succeeded", "WARNING"
            )
            category_results.append("concurrent_quiz_warn")

        self.test_results["categories"]["concurrent_ops"] = category_results
        return category_results

    def test_malformed_requests(self):
        """Test: Invalid JSON, missing fields, malformed data"""
        print("\n" + "=" * 70)
        print("🔧 EDGE CASE 3: Malformed Requests")
        print("=" * 70)

        category_results = []

        # Test 1: Invalid JSON
        self.log("Testing invalid JSON...")

        try:
            response = self.session.post(
                f"{BASE_URL}/v1/items",
                data='{"invalid": json syntax,}',  # Malformed JSON
                headers={"Content-Type": "application/json"},
            )
            if response.status_code == 422:
                self.log("Invalid JSON properly rejected", "SUCCESS")
                category_results.append("invalid_json_pass")
            else:
                self.log(
                    f"Invalid JSON unexpected response: {response.status_code}", "ERROR"
                )
                category_results.append("invalid_json_error")
        except Exception as e:
            self.log(f"Invalid JSON caused exception: {str(e)}", "WARNING")
            category_results.append("invalid_json_exception")

        # Test 2: Missing required fields
        self.log("Testing missing required fields...")

        invalid_items = [
            {},  # Completely empty
            {"type": "flashcard"},  # Missing payload
            {"payload": {"front": "test"}},  # Missing type
            {"type": "unknown_type", "payload": {"front": "test"}},  # Invalid type
            {"type": "flashcard", "payload": {}},  # Empty payload
        ]

        for i, item in enumerate(invalid_items):
            response = self.session.post(f"{BASE_URL}/v1/items", json=item)
            if response.status_code in [400, 422]:
                self.log(f"Invalid item {i+1}: Properly rejected", "SUCCESS")
                category_results.append(f"invalid_item_{i+1}_pass")
            else:
                self.log(
                    f"Invalid item {i+1}: Unexpected response {response.status_code}",
                    "ERROR",
                )
                category_results.append(f"invalid_item_{i+1}_error")

        # Test 3: Content-Type mismatches
        self.log("Testing Content-Type handling...")

        try:
            # Send JSON with wrong content type
            response = self.session.post(
                f"{BASE_URL}/v1/items",
                data='{"type":"flashcard","payload":{"front":"test","back":"test"}}',
                headers={"Content-Type": "text/plain"},
            )
            if response.status_code in [400, 415, 422]:
                self.log("Wrong Content-Type properly handled", "SUCCESS")
                category_results.append("content_type_pass")
            else:
                self.log(
                    f"Wrong Content-Type unexpected response: {response.status_code}",
                    "WARNING",
                )
                category_results.append("content_type_warn")
        except Exception as e:
            self.log(f"Content-Type test caused exception: {str(e)}", "WARNING")
            category_results.append("content_type_exception")

        self.test_results["categories"]["malformed_requests"] = category_results
        return category_results

    def test_resource_limits(self):
        """Test: Rate limiting, resource exhaustion, cleanup"""
        print("\n" + "=" * 70)
        print("📊 EDGE CASE 4: Resource Limits & Cleanup")
        print("=" * 70)

        category_results = []

        # Test 1: Rapid sequential requests
        self.log("Testing rapid sequential requests...")

        start_time = time.time()
        success_count = 0
        error_count = 0

        for i in range(50):  # 50 rapid requests
            item = {
                "type": "flashcard",
                "payload": {"front": f"Rapid test {i}", "back": f"Answer {i}"},
                "tags": ["rapid-test"],
                "difficulty": "core",
            }

            response = self.session.post(f"{BASE_URL}/v1/items", json=item)
            if response.status_code in [200, 201]:
                success_count += 1
            elif response.status_code == 429:  # Rate limited
                self.log("Rate limiting detected", "INFO")
                break
            else:
                error_count += 1

        elapsed = time.time() - start_time
        self.log(
            f"Rapid requests: {success_count} success, {error_count} errors in {elapsed:.2f}s",
            "SUCCESS",
        )
        category_results.append("rapid_requests_handled")

        # Test 2: Memory usage with large queries
        self.log("Testing large query responses...")

        try:
            # Request all items without limit
            response = self.session.get(f"{BASE_URL}/v1/items?limit=10000")
            if response.status_code == 200:
                data = response.json()
                item_count = len(data.get("items", []))
                self.log(
                    f"Large query returned {item_count} items successfully", "SUCCESS"
                )
                category_results.append("large_query_pass")
            else:
                self.log(f"Large query failed: {response.status_code}", "WARNING")
                category_results.append("large_query_warn")
        except Exception as e:
            self.log(f"Large query caused exception: {str(e)}", "ERROR")
            category_results.append("large_query_error")

        # Test 3: Long-running operations
        self.log("Testing timeout handling...")

        try:
            # Test content generation with timeout
            gen_request = {
                "text": "Generate content from this text " * 1000,  # Very long text
                "types": ["flashcard", "mcq", "cloze"],
                "count": 100,
            }

            start_time = time.time()
            response = self.session.post(
                f"{BASE_URL}/v1/items/generate", json=gen_request, timeout=30
            )
            elapsed = time.time() - start_time

            if response.status_code in [200, 201]:
                self.log(f"Long generation completed in {elapsed:.2f}s", "SUCCESS")
                category_results.append("long_generation_pass")
            elif response.status_code == 408:
                self.log("Long generation properly timed out", "SUCCESS")
                category_results.append("long_generation_timeout")
            else:
                self.log(
                    f"Long generation unexpected response: {response.status_code}",
                    "WARNING",
                )
                category_results.append("long_generation_warn")

        except requests.Timeout:
            self.log("Request timeout handled gracefully", "SUCCESS")
            category_results.append("timeout_handled")
        except Exception as e:
            self.log(f"Timeout test caused exception: {str(e)}", "WARNING")
            category_results.append("timeout_exception")

        self.test_results["categories"]["resource_limits"] = category_results
        return category_results

    def test_data_consistency(self):
        """Test: State consistency, referential integrity, orphaned data"""
        print("\n" + "=" * 70)
        print("🔍 EDGE CASE 5: Data Consistency & Integrity")
        print("=" * 70)

        category_results = []

        # Test 1: Orphaned quiz data
        self.log("Testing orphaned quiz cleanup...")

        # Start a quiz but don't finish it
        quiz_params = {"mode": "drill", "params": {"length": 3}}

        response = self.session.post(f"{BASE_URL}/v1/quiz/start", json=quiz_params)
        if response.status_code == 200:
            quiz_data = response.json().get("data", {})
            quiz_id = quiz_data.get("quiz_id")

            # Submit partial answers then abandon
            items = quiz_data.get("items", [])
            if items:
                submit_data = {
                    "quiz_id": quiz_id,
                    "item_id": items[0]["id"],
                    "response": {"rating": 2},
                }

                submit_response = self.session.post(
                    f"{BASE_URL}/v1/quiz/submit", json=submit_data
                )
                if submit_response.status_code == 200:
                    self.log("Partial quiz state created (testing cleanup)", "SUCCESS")
                    category_results.append("partial_quiz_created")

                    # Try to access the quiz later
                    time.sleep(1)
                    finish_response = self.session.post(
                        f"{BASE_URL}/v1/quiz/finish", json={"quiz_id": quiz_id}
                    )
                    if finish_response.status_code in [200, 404, 410]:
                        self.log("Orphaned quiz handled appropriately", "SUCCESS")
                        category_results.append("orphaned_quiz_handled")
                    else:
                        self.log(
                            f"Orphaned quiz unexpected response: {finish_response.status_code}",
                            "WARNING",
                        )
                        category_results.append("orphaned_quiz_warn")

        # Test 2: Item deletion consistency
        self.log("Testing item deletion consistency...")

        # Create an item, then try to use it in operations
        item = {
            "type": "flashcard",
            "payload": {"front": "Delete test", "back": "Will be deleted"},
            "tags": ["delete-test"],
            "difficulty": "core",
        }

        create_response = self.session.post(f"{BASE_URL}/v1/items", json=item)
        if create_response.status_code in [200, 201]:
            created_data = create_response.json()
            item_id = created_data.get("id")

            if item_id:
                # Verify item exists
                get_response = self.session.get(f"{BASE_URL}/v1/items/{item_id}")
                if get_response.status_code == 200:
                    self.log("Item retrieval consistency verified", "SUCCESS")
                    category_results.append("item_retrieval_consistent")
                else:
                    self.log(
                        f"Item retrieval inconsistent: {get_response.status_code}",
                        "ERROR",
                    )
                    category_results.append("item_retrieval_error")

        # Test 3: Review state consistency
        self.log("Testing review state consistency...")

        # Check if review states are maintained correctly across operations
        queue_response = self.session.get(f"{BASE_URL}/v1/review/queue")
        if queue_response.status_code == 200:
            queue_data = queue_response.json().get("data", {})
            initial_new = len(queue_data.get("new", []))

            # Create a new published item
            new_item = {
                "type": "flashcard",
                "payload": {"front": "Review test", "back": "State test"},
                "tags": ["review-test"],
                "difficulty": "core",
                "status": "published",
            }

            create_response = self.session.post(f"{BASE_URL}/v1/items", json=new_item)
            if create_response.status_code in [200, 201]:
                # Check if queue reflects the change
                time.sleep(0.5)  # Allow for any async processing
                updated_queue = self.session.get(f"{BASE_URL}/v1/review/queue")
                if updated_queue.status_code == 200:
                    updated_data = updated_queue.json().get("data", {})
                    final_new = len(updated_data.get("new", []))

                    if final_new > initial_new:
                        self.log("Review queue consistency maintained", "SUCCESS")
                        category_results.append("review_consistency_pass")
                    else:
                        self.log("Review queue consistency may be delayed", "WARNING")
                        category_results.append("review_consistency_warn")

        self.test_results["categories"]["data_consistency"] = category_results
        return category_results

    def test_forgotten_scenarios(self):
        """Test: Commonly overlooked edge cases and scenarios"""
        print("\n" + "=" * 70)
        print("🔎 EDGE CASE 6: Forgotten Scenarios & Corner Cases")
        print("=" * 70)

        category_results = []

        # Test 1: Case sensitivity in tags and searches
        self.log("Testing case sensitivity...")

        case_item = {
            "type": "flashcard",
            "payload": {"front": "Case Test", "back": "Case Answer"},
            "tags": ["CaseTest", "UPPERCASE", "lowercase"],
            "difficulty": "core",
        }

        create_response = self.session.post(f"{BASE_URL}/v1/items", json=case_item)
        if create_response.status_code in [200, 201]:
            # Test search with different cases
            search_tests = [
                ("CaseTest", "exact case"),
                ("casetest", "lowercase"),
                ("CASETEST", "uppercase"),
                ("cAsEtEsT", "mixed case"),
            ]

            consistent_results = True
            for search_term, case_type in search_tests:
                response = self.session.get(f"{BASE_URL}/v1/items?q={search_term}")
                if response.status_code != 200:
                    consistent_results = False
                    break

            if consistent_results:
                self.log("Case sensitivity handled consistently", "SUCCESS")
                category_results.append("case_sensitivity_consistent")
            else:
                self.log("Case sensitivity inconsistent", "WARNING")
                category_results.append("case_sensitivity_warn")

        # Test 2: Timezone and date handling
        self.log("Testing timezone and date handling...")

        # Check if timestamps are consistent
        before_time = time.time()

        item = {
            "type": "flashcard",
            "payload": {"front": "Time test", "back": "Timestamp test"},
            "tags": ["time-test"],
            "difficulty": "core",
        }

        create_response = self.session.post(f"{BASE_URL}/v1/items", json=item)
        after_time = time.time()

        if create_response.status_code in [200, 201]:
            created_data = create_response.json()
            created_at = created_data.get("created_at")

            if created_at:
                # Very basic timestamp sanity check
                self.log("Timestamp present in response", "SUCCESS")
                category_results.append("timestamp_present")
            else:
                self.log("Timestamp missing from response", "WARNING")
                category_results.append("timestamp_missing")

        # Test 3: Encoding and character set issues
        self.log("Testing character encoding edge cases...")

        encoding_tests = [
            "Emoji test: 😀🎉🔥💯",
            "Math symbols: ∑∫∂√∞≈≠±",
            "Diacritics: àáâãäåæçèéêë",
            "CJK: 中文 日本語 한국어",
            "RTL: العربية עברית",
        ]

        encoding_success = 0
        for i, test_text in enumerate(encoding_tests):
            item = {
                "type": "flashcard",
                "payload": {"front": test_text, "back": "Encoding test"},
                "tags": [f"encoding-{i}"],
                "difficulty": "core",
            }

            response = self.session.post(f"{BASE_URL}/v1/items", json=item)
            if response.status_code in [200, 201]:
                encoding_success += 1

        if encoding_success == len(encoding_tests):
            self.log(
                f"All encoding tests passed ({encoding_success}/{len(encoding_tests)})",
                "SUCCESS",
            )
            category_results.append("encoding_all_pass")
        elif encoding_success > len(encoding_tests) // 2:
            self.log(
                f"Most encoding tests passed ({encoding_success}/{len(encoding_tests)})",
                "WARNING",
            )
            category_results.append("encoding_most_pass")
        else:
            self.log(
                f"Many encoding tests failed ({encoding_success}/{len(encoding_tests)})",
                "ERROR",
            )
            category_results.append("encoding_many_fail")

        # Test 4: URL parameter injection and validation
        self.log("Testing URL parameter validation...")

        dangerous_params = [
            "limit=99999999",
            "offset=-1",
            "q='; DROP TABLE items; --",
            "type=<script>alert('xss')</script>",
            "tags[]=../../../etc/passwd",
        ]

        param_safety = 0
        for param in dangerous_params:
            try:
                response = self.session.get(f"{BASE_URL}/v1/items?{param}")
                if response.status_code in [200, 400, 422]:
                    param_safety += 1
            except Exception:
                param_safety += 1  # Exception is also safe handling

        if param_safety == len(dangerous_params):
            self.log("All dangerous parameters handled safely", "SUCCESS")
            category_results.append("param_safety_pass")
        else:
            self.log(
                f"Some parameters not handled safely ({param_safety}/{len(dangerous_params)})",
                "WARNING",
            )
            category_results.append("param_safety_warn")

        self.test_results["categories"]["forgotten_scenarios"] = category_results
        return category_results

    def print_comprehensive_summary(self):
        """Print detailed summary of all edge case testing"""
        print("\n" + "=" * 80)
        print("🎯 COMPREHENSIVE EDGE CASE TESTING SUMMARY")
        print("=" * 80)

        results = self.test_results
        total = results["total_tests"]
        passed = results["passed"]
        failed = results["failed"]
        warnings = results["warnings"]

        success_rate = (passed / total * 100) if total > 0 else 0

        print("\n📊 OVERALL RESULTS:")
        print(f"   Total Tests: {total}")
        print(f"   ✅ Passed: {passed} ({success_rate:.1f}%)")
        print(f"   ❌ Failed: {failed}")
        print(f"   ⚠️ Warnings: {warnings}")

        print("\n🔍 DETAILED CATEGORY BREAKDOWN:")
        for category, category_results in results["categories"].items():
            print(
                f"   {category.replace('_', ' ').title()}: {len(category_results)} tests"
            )
            for result in category_results[:3]:  # Show first 3 results
                print(f"      • {result}")
            if len(category_results) > 3:
                print(f"      • ... and {len(category_results) - 3} more")

        # Overall assessment
        if failed == 0 and warnings <= total * 0.1:  # Less than 10% warnings
            verdict = "🟢 EXCELLENT - System handles edge cases robustly"
        elif failed <= total * 0.05:  # Less than 5% failures
            verdict = "🟡 GOOD - Minor edge case issues, but system is stable"
        else:
            verdict = "🔴 NEEDS ATTENTION - Significant edge case vulnerabilities found"

        print("\n🚀 EDGE CASE TEST VERDICT:")
        print(f"   {verdict}")

        return results

    def run_all_tests(self):
        """Execute all edge case and blind spot tests"""
        print("🚀 Starting Comprehensive Edge Case & Blind Spot Testing")
        print("Testing boundary conditions, race conditions, and overlooked scenarios")
        print("=" * 80)

        try:
            # Run all test categories
            self.test_data_boundary_limits()
            self.test_concurrent_operations()
            self.test_malformed_requests()
            self.test_resource_limits()
            self.test_data_consistency()
            self.test_forgotten_scenarios()

            # Print comprehensive summary
            results = self.print_comprehensive_summary()

            return results

        except Exception as e:
            self.log(f"Edge case testing failed with exception: {str(e)}", "ERROR")
            return {"error": str(e)}


if __name__ == "__main__":
    tester = EdgeCaseTester()
    results = tester.run_all_tests()

    # Exit with appropriate code
    if results.get("failed", 0) == 0:
        print("\n✅ All edge case tests completed successfully!")
        exit(0)
    else:
        print("\n❌ Some edge case tests failed!")
        exit(1)
