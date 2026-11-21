#!/bin/sh
# Fail if a recorded fixture still contains an unredacted identifier field.
# Redacted fixtures use the fake IDs 1234/5678/9012 and "**REDACTED**".
set -eu
status=0
for f in tests/fixtures/real/*.json; do
  [ -e "$f" ] || continue
  if grep -qE '"(GatewayUsername|SerialNumber|Email|UserName)": *"[^*]' "$f"; then
    echo "unredacted identifier in $f"; status=1
  fi
  # System name: SystemName anywhere; Name only on the top level or in a top-level list
  # (indent 2 or 4 of the recorder's output), deeper Name keys are descriptor texts.
  if grep -qE '"SystemName": *"[^*]|^ {2}( {2})?"Name": *"[^*]' "$f"; then
    echo "unredacted system name in $f"; status=1
  fi
  if grep -qE '"(Id|SystemId|GatewayId|SystemShareId)": *[0-9]+' "$f" \
     && grep -E '"(Id|SystemId|GatewayId|SystemShareId)": *[0-9]+' "$f" | grep -vqE ': *(1234|5678|9012)[,}]?$'; then
    echo "real system or gateway ID in $f"; status=1
  fi
  if grep -qE '"[0-9]{2}:[0-9]{2}-[0-9]{2}:[0-9]{2};' "$f"; then
    echo "time program schedule in $f"; status=1
  fi
done
exit $status
