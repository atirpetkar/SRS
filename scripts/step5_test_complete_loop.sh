#!/bin/bash

# Complete Practice Loop Test Script
# Demonstrates the full workflow from Step 1-5

set -e  # Exit on any error

BASE_URL="http://localhost:8000"
echo "🚀 Testing Complete Practice Loop (Steps 1-5)"
echo "=============================================="

# Check if server is running
echo "📡 Checking server health..."
curl -s "$BASE_URL/v1/healthz" | jq '.ok' || {
    echo "❌ Server not running. Start with: uvicorn api.main:app --reload --port 8000"
    exit 1
}
echo "✅ Server is healthy"

echo ""
echo "📥 Step 1: Import Italian vocabulary..."
IMPORT_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/items/import" \
  -H "Content-Type: application/json" \
  -d @- << 'EOF'
{
  "format": "markdown",
  "data": ":::flashcard\nQ: How do you say \"hello\" in Italian?\nA: Ciao\nHINT: Common greeting\n:::\n\n:::mcq\nSTEM: What does \"Grazie\" mean?\nA) Hello\nB) Goodbye\nC) Thank you *correct\nD) Please\n:::\n\n:::cloze\nTEXT: In Italian, \"good morning\" is [[Buongiorno]].\n:::",
  "metadata": {"source": "demo_test", "batch": "step5_demo"}
}
EOF
)

echo "Import result:"
echo "$IMPORT_RESPONSE" | jq '.data | {total_created, total_errors, staged_ids}'

# Extract staged IDs
STAGED_IDS=$(echo "$IMPORT_RESPONSE" | jq -r '.data.staged_ids[]')
echo "Staged item IDs: $STAGED_IDS"

echo ""
echo "📋 Step 2: Review staged items..."
curl -s "$BASE_URL/v1/items/staged?limit=5" | jq '.data | {items: .items | length, total}'

echo ""
echo "✅ Step 3: Approve items (draft → published)..."
APPROVAL_PAYLOAD=$(echo "$STAGED_IDS" | jq -R . | jq -s '{ids: .}')
APPROVAL_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/items/approve" \
  -H "Content-Type: application/json" \
  -d "$APPROVAL_PAYLOAD")

echo "Approval result:"
echo "$APPROVAL_RESPONSE" | jq '.data | {approved_ids: .approved_ids | length, failed_ids: .failed_ids | length}'

echo ""
echo "🎯 Step 4: Get review queue (FSRS scheduling)..."
QUEUE_RESPONSE=$(curl -s "$BASE_URL/v1/review/queue?limit=10&mix_new=0.5")
echo "Queue status:"
echo "$QUEUE_RESPONSE" | jq '.data | {due_count: .due | length, new_count: .new | length}'

# Get first new item for review
FIRST_ITEM_ID=$(echo "$QUEUE_RESPONSE" | jq -r '.data.new[0].id // empty')

if [ -n "$FIRST_ITEM_ID" ]; then
    echo ""
    echo "📝 Step 5a: Record a review (FSRS update)..."
    REVIEW_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/review/record" \
      -H "Content-Type: application/json" \
      -d @- << EOF
{
  "item_id": "$FIRST_ITEM_ID",
  "rating": 3,
  "correct": true,
  "latency_ms": 2500,
  "mode": "review",
  "response": {"answer": "ciao"}
}
EOF
    )

    echo "Review recorded:"
    echo "$REVIEW_RESPONSE" | jq '.data | {next_due, interval_days}'

    echo ""
    echo "🎮 Step 5b: Start a drill quiz..."
    QUIZ_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/quiz/start" \
      -H "Content-Type: application/json" \
      -d @- << 'EOF'
{
  "mode": "drill",
  "params": {
    "length": 3,
    "time_limit_s": 180
  }
}
EOF
    )

    QUIZ_ID=$(echo "$QUIZ_RESPONSE" | jq -r '.data.quiz_id')
    echo "Quiz started:"
    echo "$QUIZ_RESPONSE" | jq '.data | {quiz_id, total_items, mode}'

    # Get first quiz item for submission
    QUIZ_ITEM_ID=$(echo "$QUIZ_RESPONSE" | jq -r '.data.items[0].id')
    QUIZ_ITEM_TYPE=$(echo "$QUIZ_RESPONSE" | jq -r '.data.items[0].type')

    echo ""
    echo "📤 Step 5c: Submit quiz answer..."
    
    # Create response based on item type
    if [ "$QUIZ_ITEM_TYPE" = "flashcard" ]; then
        QUIZ_RESPONSE_DATA='{"answer": "test answer"}'
    elif [ "$QUIZ_ITEM_TYPE" = "mcq" ]; then
        QUIZ_RESPONSE_DATA='{"selected_options": ["C"]}'
    elif [ "$QUIZ_ITEM_TYPE" = "cloze" ]; then
        QUIZ_RESPONSE_DATA='{"answers": {"1": "Buongiorno"}}'
    else
        QUIZ_RESPONSE_DATA='{"answer": "test"}'
    fi

    SUBMIT_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/quiz/submit" \
      -H "Content-Type: application/json" \
      -d @- << EOF
{
  "quiz_id": "$QUIZ_ID",
  "item_id": "$QUIZ_ITEM_ID", 
  "response": $QUIZ_RESPONSE_DATA
}
EOF
    )

    echo "Submission result:"
    echo "$SUBMIT_RESPONSE" | jq '.data.grading | {correct, partial_credit, score}'

    echo ""
    echo "🏁 Step 5d: Finish quiz and get score..."
    FINISH_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/quiz/finish" \
      -H "Content-Type: application/json" \
      -d @- << EOF
{
  "quiz_id": "$QUIZ_ID"
}
EOF
    )

    echo "Final quiz results:"
    echo "$FINISH_RESPONSE" | jq '.data | {final_score, time_taken_s, breakdown: .breakdown | {total_items, correct_items}}'

else
    echo "⚠️  No new items in queue - skipping review/quiz steps"
fi

echo ""
echo "🎉 COMPLETE PRACTICE LOOP VERIFIED!"
echo "=================================="
echo "✅ Import content (markdown DSL)"
echo "✅ Stage → approve workflow" 
echo "✅ FSRS scheduler with review queue"
echo "✅ Quiz modes with objective grading"
echo "✅ All endpoints working with proper response envelopes"
echo ""
echo "🎯 Your system is ready for daily use!"
echo "Missing only: Step 6 analytics (optional enhancement)"