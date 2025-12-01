#!/bin/bash
# Quick test script for chat-enabled RAG pipeline using curl

# Your Lambda Function URL
RAG_ENDPOINT="https://pym5mhopdyechc5a2pp6eim5mq0otoly.lambda-url.us-east-1.on.aws/"

echo "=========================================="
echo "Testing Chat-Enabled RAG Pipeline"
echo "=========================================="
echo "Endpoint: $RAG_ENDPOINT"
echo ""

# Test 1: First question (creates new session)
echo "Test 1: First question - 'What is Express Entry?'"
echo "------------------------------------------"
response1=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$RAG_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is Express Entry?"
  }')

# Extract HTTP code and response body
http_code=$(echo "$response1" | grep "HTTP_CODE:" | cut -d: -f2)
response_body=$(echo "$response1" | sed '/HTTP_CODE:/d')

echo "HTTP Status: $http_code"
echo ""
echo "Raw Response:"
echo "$response_body"
echo ""

# Check if response is valid JSON
if echo "$response_body" | jq empty 2>/dev/null; then
    echo "✅ Valid JSON response"
    echo "$response_body" | jq '.'
    session_id=$(echo "$response_body" | jq -r '.session_id')
    echo ""
    echo "✅ Session ID: $session_id"
else
    echo "❌ Invalid JSON response - possible Lambda error"
    echo "This might be an error from Lambda. Check CloudWatch logs:"
    echo "  aws logs tail /aws/lambda/rag_pipeline-function-dev --follow"
    exit 1
fi
echo ""
sleep 2

# Test 2: Follow-up question with session_id
if [ -n "$session_id" ] && [ "$session_id" != "null" ]; then
    echo ""
    echo "Test 2: Follow-up question - 'What are the language requirements for it?'"
    echo "Using session_id: $session_id"
    echo "------------------------------------------"
    
    response2=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$RAG_ENDPOINT" \
      -H "Content-Type: application/json" \
      -d "{
        \"query\": \"What are the language requirements for it?\",
        \"session_id\": \"$session_id\"
      }")
    
    http_code2=$(echo "$response2" | grep "HTTP_CODE:" | cut -d: -f2)
    response_body2=$(echo "$response2" | sed '/HTTP_CODE:/d')
    
    echo "HTTP Status: $http_code2"
    echo ""
    
    if echo "$response_body2" | jq empty 2>/dev/null; then
        echo "✅ Answer:"
        echo "$response_body2" | jq -r '.answer' | head -5
        echo "..."
        echo ""
        echo "📊 History length: $(echo "$response_body2" | jq -r '.history_length')"
        echo "⏱️  Response time: $(echo "$response_body2" | jq -r '.timings.total_ms')ms"
        echo ""
        
        # Test 3: Another follow-up
        echo ""
        echo "Test 3: Another follow-up - 'How long does the process take?'"
        echo "Using session_id: $session_id"
        echo "------------------------------------------"
        
        response3=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$RAG_ENDPOINT" \
          -H "Content-Type: application/json" \
          -d "{
            \"query\": \"How long does the process take?\",
            \"session_id\": \"$session_id\"
          }")
        
        http_code3=$(echo "$response3" | grep "HTTP_CODE:" | cut -d: -f2)
        response_body3=$(echo "$response3" | sed '/HTTP_CODE:/d')
        
        echo "HTTP Status: $http_code3"
        echo ""
        
        if echo "$response_body3" | jq empty 2>/dev/null; then
            echo "✅ Answer:"
            echo "$response_body3" | jq -r '.answer' | head -5
            echo "..."
            echo ""
            echo "📊 History length (should be 4): $(echo "$response_body3" | jq -r '.history_length')"
            echo "⏱️  Response time: $(echo "$response_body3" | jq -r '.timings.total_ms')ms"
        else
            echo "❌ Invalid response for test 3"
        fi
    else
        echo "❌ Invalid response for test 2"
    fi
else
    echo "❌ No valid session_id from test 1, skipping follow-up tests"
fi

echo ""
echo "=========================================="
echo "✅ Test complete!"
echo "Session ID: $session_id"
echo "=========================================="

