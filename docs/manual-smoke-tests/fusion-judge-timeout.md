# Manual Smoke Test: Fusion Judge Timeout Branch
# ============================================================================
# Purpose: Verify that when the judge model times out, partial response is
#          persisted and appropriate messages are sent to the client.
#
# Prerequisites:
#   - Run: cd /home/osmar/nexuslocal && python -m uvicorn backend.main:app --reload
#   - Create a test conversation via frontend or curl
#
# Test Steps:
#   1. Configure a slow judge model (e.g., set provider delay to >180s in test DB)
#      OR manually interrupt the request after 180s using curl kill or browser stop.
#
#   2. Send a fusion request that triggers judge timeout:
#      curl -X POST http://localhost:8000/api/chat/stream \
#           -H "Content-Type: application/json" \
#           -d '{"conversation_id": "test-conv", "message": "Write a long essay about AI"}'
#
#   3. Observe websocket events (use browser DevTools or wscat):
#      - Should receive: {"type": "fusion_start", ...}
#      - Should receive: {"type": "fusion_phase", "phase": "proposers"}
#      - Should receive several {"type": "token", "content": "..."} events
#      - After ~180s, should receive:
#          {"type": "fusion_status", "message": "Juiz interrompido no limite de 180s. Resposta parcial salva."}
#      - NOT receive: {"type": "error", "message": "O juiz do Fusion excedeu o tempo limite (180s). Tente novamente."}
#        (unless full_response is empty/whitespace)
#
#   4. Check database:
#      sqlite3 backend/nexuslocal.db "SELECT content FROM messages WHERE conversation_id='test-conv' ORDER BY rowid DESC LIMIT 1;"
#      Expected: Contains partial judge response (not empty, not full response)
#
#   5. Check logs (backend stdout):
#      Should see: "Fusion: timeout do juiz (180s) conversation=test-conv judge=<model_id>"
#
# Expected Outcomes:
#   ✓ WebSocket sends fusion_status with partial save message
#   ✓ Database contains partial response (not empty, not complete)
#   ✓ Log contains timeout message with correct TIMEOUT_JUIZ value (180s)
#   ✓ No fatal error message sent to client (unless response is empty)
#
# Failure Indicators:
#   ✗ Client receives "error" message with "excedeu o tempo limite" (should be "fusion_status")
#   ✗ Database has empty content for judge response
#   ✗ Log shows fixed "180s" string instead of interpolated value
#   ✗ Application crashes or raises unhandled exception
