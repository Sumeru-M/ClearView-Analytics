#!/bin/bash

# Test script for ClearView Analytics API deployment
# Usage: ./test_deployment.sh [base_url]

BASE_URL="${1:-https://clearview-analytics.onrender.com}"
echo "Testing ClearView Analytics API at: $BASE_URL"
echo "=================================================="

# Test 1: Health check
echo -e "\n1. Testing /api/health"
curl -s -X GET "$BASE_URL/api/health" | jq '.' || echo "FAILED"

# Test 2: Auth register
echo -e "\n2. Testing /api/auth/register"
REGISTER_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser_'$(date +%s)'",
    "email": "test_'$(date +%s)'@example.com",
    "password": "testpass123"
  }')
echo "$REGISTER_RESPONSE" | jq '.' || echo "FAILED"

# Test 3: Auth login  
echo -e "\n3. Testing /api/auth/login"
USERNAME="testuser_$(date +%s)"
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "'$USERNAME'",
    "password": "testpass123"
  }')
echo "$LOGIN_RESPONSE" | jq '.' || echo "FAILED"

# Extract token
TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.token' 2>/dev/null || echo "")
if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
  echo "ERROR: Could not get token. Skipping authenticated tests."
  exit 1
fi

echo "Got token: ${TOKEN:0:20}..."

# Test 4: Auth me
echo -e "\n4. Testing /api/auth/me"
curl -s -X GET "$BASE_URL/api/auth/me" \
  -H "Authorization: Bearer $TOKEN" | jq '.' || echo "FAILED"

# Test 5: M3 Portfolio Construction
echo -e "\n5. Testing /api/m3/optimize (M3 - Portfolio Construction)"
curl -s -X POST "$BASE_URL/api/m3/optimize" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tickers": ["RELIANCE.NS", "TCS.NS", "INFY.NS"],
    "period": "2y",
    "risk_free_rate": 0.07
  }' | jq '.' || echo "FAILED"

# Test 6: M4 Scenario Analysis
echo -e "\n6. Testing /api/m4/scenarios (M4 - Scenario Analysis)"
curl -s -X POST "$BASE_URL/api/m4/scenarios" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tickers": ["RELIANCE.NS", "TCS.NS"],
    "portfolio_value": 1000000,
    "risk_free_rate": 0.07,
    "confidence_level": 0.95,
    "scenarios": "ALL"
  }' | jq '.' || echo "FAILED"

# Test 7: M5 Institutional Optimization
echo -e "\n7. Testing /api/m5/institutional (M5 - Institutional Optimization)"
curl -s -X POST "$BASE_URL/api/m5/institutional" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tickers": ["RELIANCE.NS", "TCS.NS"],
    "portfolio_value": 1000000,
    "risk_free_rate": 0.07,
    "methods": "all"
  }' | jq '.' || echo "FAILED"

# Test 8: M6 Virtual Trade Simulation
echo -e "\n8. Testing /api/m6/simulate (M6 - Virtual Trade Simulation)"
curl -s -X POST "$BASE_URL/api/m6/simulate" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "RELIANCE.NS",
    "quantity": 10,
    "price": 2850,
    "holdings": {"RELIANCE.NS": 10},
    "current_prices": {"RELIANCE.NS": 2850},
    "total_value": 28500,
    "risk_free_rate": 0.07,
    "n_mc_paths": 100
  }' | jq '.' || echo "FAILED"

# Test 9: M7 Market Regime Intelligence
echo -e "\n9. Testing /api/m7/regime (M7 - Market Regime Intelligence)"
curl -s -X POST "$BASE_URL/api/m7/regime" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tickers": ["RELIANCE.NS", "TCS.NS"],
    "risk_free_rate": 0.07,
    "horizons": [21, 63],
    "risk_appetite": "balanced"
  }' | jq '.' || echo "FAILED"

echo -e "\n=================================================="
echo "Tests completed!"
