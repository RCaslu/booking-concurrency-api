#!/usr/bin/env bash
set -euo pipefail

API="${API:-http://localhost:${API_PORT:-8020}}"
N="${N:-20}"

iso() { date -u -d "+$1 hours" +%Y-%m-%dT%H:00:00Z 2>/dev/null || date -u -v+"$1"H +%Y-%m-%dT%H:00:00Z; }
step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
call() { curl -s -w '\n-> HTTP %{http_code}\n' "$@"; }
json_id() {
  local id
  id=$(sed -nE 's/^\{"id":"([0-9a-f-]{36})".*/\1/p')
  [[ -n "$id" ]] || { echo "falha: a resposta nao trouxe um id (a API esta no ar? veja a resposta acima)" >&2; exit 1; }
  echo "$id"
}

START=$(iso 24)
END=$(iso 25)
LATER=$(iso 27)
LATER_END=$(iso 28)

step "1. API no ar"
call "$API/health" || { echo "falha: a API nao respondeu em $API. Suba com: docker compose up -d --wait api" >&2; exit 1; }

step "2. Cadastrar uma sala"
RESOURCE=$(curl -s -X POST "$API/resources" -H 'Content-Type: application/json' \
  -d '{"name": "Sala Demo", "capacity": 8, "location": "1o andar"}')
echo "$RESOURCE"
RID=$(echo "$RESOURCE" | json_id)

step "3. Reservar $START -> $END"
BOOKING=$(curl -s -X POST "$API/resources/$RID/bookings" -H 'Content-Type: application/json' \
  -d "{\"requester_email\": \"ana@example.com\", \"start_time\": \"$START\", \"end_time\": \"$END\"}")
echo "$BOOKING"
BID=$(echo "$BOOKING" | json_id)

step "4. Outra pessoa tenta o mesmo horario (esperado: 409 OVERLAPPING_BOOKING)"
call -X POST "$API/resources/$RID/bookings" -H 'Content-Type: application/json' \
  -d "{\"requester_email\": \"bruno@example.com\", \"start_time\": \"$START\", \"end_time\": \"$END\"}"

step "5. Disponibilidade do horario (esperado: is_available false)"
call "$API/resources/$RID/availability?start=$START&end=$END"

step "6. O problema central: $N pessoas reservam o MESMO horario AO MESMO TEMPO"
RACE_START=$LATER RACE_END=$LATER_END
CODES=$(seq 1 "$N" | xargs -P "$N" -I{} curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST "$API/resources/$RID/bookings" -H 'Content-Type: application/json' \
  -d "{\"requester_email\": \"pessoa{}@example.com\", \"start_time\": \"$RACE_START\", \"end_time\": \"$RACE_END\"}")
echo "201 (sucesso):  $(grep -c '^201$' <<<"$CODES" || true)"
echo "409 (conflito): $(grep -c '^409$' <<<"$CODES" || true)"
echo "outros:         $(grep -vcE '^(201|409)$' <<<"$CODES" || true)"
ACTIVE=$(curl -s "$API/resources/$RID/availability?start=$RACE_START&end=$RACE_END" | grep -o '"requester_email"' | grep -c . || true)
echo "reservas ativas no horario disputado: $ACTIVE (esperado: exatamente 1)"

step "7. Remarcar a reserva da Ana para depois (PATCH)"
NEW_START=$(iso 48)
NEW_END=$(iso 49)
call -X PATCH "$API/bookings/$BID" -H 'Content-Type: application/json' \
  -d "{\"start_time\": \"$NEW_START\", \"end_time\": \"$NEW_END\"}"

step "8. Cancelar a reserva da Ana, e tentar cancelar de novo (esperado: 200, depois 409)"
call -X DELETE "$API/bookings/$BID"
call -X DELETE "$API/bookings/$BID"
