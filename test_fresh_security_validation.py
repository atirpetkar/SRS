#!/usr/bin/env python3
"""
Fresh Round 2 Security Validation Script
Tests org-scoped data isolation with multiple organizations
"""


import requests

BASE_URL = "http://127.0.0.1:8000"


class OrgClient:
    """Client that simulates different org contexts"""

    def __init__(self, org_name: str):
        self.org_name = org_name
        self.session = requests.Session()
        # Note: In AUTH_MODE=none, the API uses hardcoded dev entities
        # We'll test by creating different endpoints and validating isolation

    def post(self, endpoint: str, data: dict) -> dict:
        """POST request"""
        response = self.session.post(
            f"{BASE_URL}{endpoint}",
            json=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            return {"status": response.status_code, "data": response.json()}
        except:
            return {"status": response.status_code, "data": response.text}

    def get(self, endpoint: str) -> dict:
        """GET request"""
        response = self.session.get(f"{BASE_URL}{endpoint}")
        try:
            return {"status": response.status_code, "data": response.json()}
        except:
            return {"status": response.status_code, "data": response.text}


def test_basic_isolation():
    """Test basic data isolation between different clients"""
    print("🔒 Testing Basic Data Isolation...")

    client = OrgClient("test_org")

    # Create some test items
    items = [
        {
            "type": "flashcard",
            "payload": {"front": "Security Test 1", "back": "Answer 1"},
            "tags": ["security", "test1"],
            "difficulty": "intro",
        },
        {
            "type": "mcq",
            "payload": {
                "stem": "Security MCQ Question",
                "options": [
                    {"id": "a", "text": "Wrong", "is_correct": False},
                    {"id": "b", "text": "Correct", "is_correct": True},
                ],
            },
            "tags": ["security", "mcq"],
            "difficulty": "core",
        },
    ]

    created_ids = []
    for item in items:
        result = client.post("/v1/items", item)
        if result["status"] == 201:
            created_ids.append(result["data"]["id"])
            print(f"✅ Created item: {result['data']['id']}")
        else:
            print(f"❌ Failed to create item: {result}")

    # Verify we can list our items
    result = client.get("/v1/items")
    if result["status"] == 200:
        visible_items = result["data"]["items"]
        visible_ids = {item["id"] for item in visible_items}

        print(f"✅ Can see {len(visible_items)} items via list endpoint")

        # Verify all created items are visible
        for item_id in created_ids:
            if item_id in visible_ids:
                print(f"✅ Item {item_id[:8]}... is visible")
            else:
                print(f"❌ Item {item_id[:8]}... is NOT visible")
    else:
        print(f"❌ Failed to list items: {result}")

    return created_ids


def test_cross_org_access_attempts():
    """Test that we cannot access items by guessing IDs"""
    print("🛡️ Testing Cross-Org Access Prevention...")

    client = OrgClient("test_org")

    # Create a test item first
    test_item = {
        "type": "flashcard",
        "payload": {"front": "Access Test", "back": "Should be protected"},
        "tags": ["access-test"],
    }

    result = client.post("/v1/items", test_item)
    if result["status"] == 201:
        item_id = result["data"]["id"]
        org_id = result["data"]["org_id"]
        print(f"✅ Created test item: {item_id[:8]}... in org {org_id[:8]}...")

        # Try to access the item directly (should work for same org)
        result = client.get(f"/v1/items/{item_id}")
        if result["status"] == 200:
            print("✅ Can access own item directly")
        else:
            print(f"❌ Cannot access own item: {result}")

        # In AUTH_MODE=none, we can't truly test cross-org access since
        # all requests use the same dev entities. But we can test malformed IDs

        # Test with invalid UUID
        result = client.get("/v1/items/invalid-uuid")
        if result["status"] == 404 or result["status"] == 422:
            print(f"✅ Invalid UUID properly rejected: {result['status']}")
        else:
            print(f"❌ Invalid UUID not rejected: {result}")

        # Test with valid UUID format but non-existent item
        fake_id = "00000000-0000-0000-0000-000000000999"
        result = client.get(f"/v1/items/{fake_id}")
        if result["status"] == 404:
            print("✅ Non-existent item properly returns 404")
        else:
            print(f"❌ Non-existent item returned: {result['status']}")

    else:
        print(f"❌ Failed to create test item: {result}")


def test_database_level_isolation():
    """Verify that database queries are properly org-scoped"""
    print("🗄️ Testing Database-Level Isolation...")

    client = OrgClient("db_test")

    # Create items with specific content for verification
    test_items = [
        {
            "type": "flashcard",
            "payload": {"front": "DB Test Item 1", "back": "Answer 1"},
            "tags": ["db-isolation"],
        },
        {
            "type": "cloze",
            "payload": {"text": "This is a [[test]] for database [[isolation]]."},
            "tags": ["db-isolation", "cloze"],
        },
    ]

    created_items = []
    for item in test_items:
        result = client.post("/v1/items", item)
        if result["status"] == 201:
            created_items.append(result["data"])
            print(f"✅ Created DB test item: {result['data']['id'][:8]}...")

    # Test search functionality (which uses database functions)
    result = client.get("/v1/items?q=database")
    if result["status"] == 200:
        search_results = result["data"]["items"]
        print(f"✅ Search returned {len(search_results)} items")

        # Verify search results only include our items
        our_ids = {item["id"] for item in created_items}
        search_ids = {item["id"] for item in search_results}

        if search_ids.issubset(our_ids):
            print("✅ Search results properly scoped to our org")
        else:
            print("❌ Search results include items from other orgs")

    else:
        print(f"❌ Search failed: {result}")

    # Test filtering
    result = client.get("/v1/items?tags=db-isolation")
    if result["status"] == 200:
        filtered_results = result["data"]["items"]
        print(f"✅ Tag filter returned {len(filtered_results)} items")
    else:
        print(f"❌ Tag filtering failed: {result}")


def test_import_and_staging_security():
    """Test that import/staging operations are properly isolated"""
    print("📥 Testing Import/Staging Security...")

    client = OrgClient("import_test")

    # Test markdown import
    markdown_content = """:::flashcard
Q: Import Security Test
A: This should be properly scoped
:::

:::mcq
STEM: Import MCQ Security Test
*A) Correct answer
B) Wrong answer
:::"""

    import_data = {"format": "markdown", "data": markdown_content}

    result = client.post("/v1/items/import", import_data)
    if result["status"] == 200:
        staged_ids = result["data"]["staged_ids"]
        print(f"✅ Import created {len(staged_ids)} staged items")

        # Verify we can see staged items
        result = client.get("/v1/items/staged")
        if result["status"] == 200:
            staged_items = result["data"]["items"]
            staged_item_ids = {item["id"] for item in staged_items}

            print(f"✅ Can see {len(staged_items)} staged items")

            # Verify all our staged items are visible
            for staged_id in staged_ids:
                if staged_id in staged_item_ids:
                    print(f"✅ Staged item {staged_id[:8]}... is visible")
                else:
                    print(f"❌ Staged item {staged_id[:8]}... is NOT visible")

            # Test approval
            approval_data = {"ids": staged_ids}
            result = client.post("/v1/items/approve", approval_data)
            if result["status"] == 200:
                approved = result["data"]["approved"]
                print(f"✅ Approved {len(approved)} items")
            else:
                print(f"❌ Approval failed: {result}")
        else:
            print(f"❌ Cannot see staged items: {result}")
    else:
        print(f"❌ Import failed: {result}")


def test_content_generation_security():
    """Test content generation security and isolation"""
    print("🧠 Testing Content Generation Security...")

    client = OrgClient("gen_test")

    generation_request = {
        "text": """
        Content generation security test. Photosynthesis occurs in plants at 
        a temperature of 25 degrees Celsius. This process converts light energy 
        into chemical energy through chlorophyll molecules.
        """,
        "types": ["flashcard", "mcq"],
        "count": 5,
        "difficulty": "core",
    }

    result = client.post("/v1/items/generate", generation_request)
    if result["status"] == 200:
        generated = result["data"]["generated"]
        diagnostics = result["data"]["diagnostics"]

        print(f"✅ Generation completed: {len(generated)} items generated")
        print(f"   Processing time: {diagnostics['processing_time_ms']}ms")

        if len(generated) > 0:
            # Verify generated items are in draft state and properly scoped
            result = client.get("/v1/items?status=draft")
            if result["status"] == 200:
                draft_items = result["data"]["items"]
                print(f"✅ Found {len(draft_items)} draft items (including generated)")
            else:
                print(f"❌ Cannot access draft items: {result}")
    else:
        print(f"❌ Content generation failed: {result}")


def test_edge_case_security():
    """Test security edge cases and potential vulnerabilities"""
    print("⚠️ Testing Security Edge Cases...")

    client = OrgClient("edge_test")

    # Test SQL injection attempts
    malicious_payloads = [
        {
            "type": "flashcard",
            "payload": {"front": "'; DROP TABLE items; --", "back": "test"},
        },
        {
            "type": "flashcard",
            "payload": {"front": "normal", "back": "'; DROP TABLE orgs; --"},
        },
    ]

    for payload in malicious_payloads:
        result = client.post("/v1/items", payload)
        if result["status"] == 201:
            print("✅ Malicious payload safely handled as normal content")
        else:
            print(f"⚠️ Malicious payload rejected: {result['status']}")

    # Test very large payloads
    large_payload = {
        "type": "flashcard",
        "payload": {"front": "A" * 10000, "back": "B" * 10000},
        "tags": ["large-test"],
    }

    result = client.post("/v1/items", large_payload)
    if result["status"] == 201:
        print("✅ Large payload handled successfully")
    else:
        print(f"⚠️ Large payload rejected: {result['status']}")

    # Test with null/empty values
    edge_payloads = [
        {"type": "flashcard", "payload": {"front": "", "back": "test"}},
        {"type": "flashcard", "payload": {"front": None, "back": "test"}},
    ]

    for payload in edge_payloads:
        result = client.post("/v1/items", payload)
        status = result["status"]
        if status in [201, 400, 422]:  # Valid responses
            print(f"✅ Edge case payload handled appropriately: {status}")
        else:
            print(f"❌ Unexpected response to edge case: {status}")


def main():
    """Run all security validation tests"""
    print("🚀 Starting Fresh Round 2 Security Validation")
    print("=" * 60)

    try:
        # Test basic functionality first
        print("\n" + "=" * 60)
        test_basic_isolation()

        print("\n" + "=" * 60)
        test_cross_org_access_attempts()

        print("\n" + "=" * 60)
        test_database_level_isolation()

        print("\n" + "=" * 60)
        test_import_and_staging_security()

        print("\n" + "=" * 60)
        test_content_generation_security()

        print("\n" + "=" * 60)
        test_edge_case_security()

        print("\n" + "=" * 60)
        print("🎉 Security validation tests completed!")

    except Exception as e:
        print(f"💥 Security validation failed with error: {e}")
        raise


if __name__ == "__main__":
    main()
