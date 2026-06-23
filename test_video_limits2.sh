#!/usr/bin/env bash
#
# 补充测试：用 720p 分辨率（1280×720）测各 FPS 的最大 num_frames
# 同时测试 16:9 常见比例下的最高可用分辨率

KEY="sk-KNdtRXxslHMgqX3BEEyk6lYunvfvawvkyiehgT8gHS4JkWth"
BASE="https://apihub.agnes-ai.com/v1"
MODEL="agnes-video-v2.0"
PROMPT="A calm lake at sunrise, gentle ripples, soft golden light, cinematic wide shot, no people, peaceful nature"

echo "==== 补充测试 A：1280×720 × 各 FPS × 更大 num_frames ===="
echo ""

for FPS in 24 30 60; do
  for NF in 241 321 401 441; do
    DUR=$(python3 -c "print(f'{${NF}/${FPS}:.2f}')" 2>/dev/null || echo "?")
    RESP=$(curl -s -X POST "${BASE}/videos" \
      -H "Authorization: Bearer ${KEY}" \
      -H "Content-Type: application/json" \
      --connect-timeout 10 --max-time 30 \
      -d "{\"model\":\"${MODEL}\",\"prompt\":\"${PROMPT}\",\"num_frames\":${NF},\"frame_rate\":${FPS},\"width\":1280,\"height\":720}" 2>&1)
    if echo "$RESP" | grep -qi "error\|无效\|fail\|401\|400\|422\|rate limit"; then
      MARK="❌"
    else
      MARK="✅"
    fi
    echo "  FPS=${FPS} | frames=${NF} | ${DUR}s | 1280x720 | ${MARK}  ${RESP:0:80}"
  done
  echo ""
done

echo "==== 补充测试 B：24 FPS × frames=241 × 各常见分辨率 ===="
echo ""

NF=241
FPS=24
for RES in "854,480" "1280,720" "1920,1080" "1024,768" "1024,1024" "1152,768" "1216,688" "1280,720" "1344,768" "1365,768" "1536,864" "1920,1080" "2048,1080" "2560,1440"; do
  W=$(echo "$RES" | cut -d, -f1)
  H=$(echo "$RES" | cut -d, -f2)
  DUR=$(python3 -c "print(f'${NF}/${FPS:.2f}')" 2>/dev/null || echo "?")
  RESP=$(curl -s -X POST "${BASE}/videos" \
    -H "Authorization: Bearer ${KEY}" \
    -H "Content-Type: application/json" \
    --connect-timeout 10 --max-time 30 \
    -d "{\"model\":\"${MODEL}\",\"prompt\":\"${PROMPT}\",\"num_frames\":${NF},\"frame_rate\":${FPS},\"width\":${W},\"height\":${H}}" 2>&1)
  if echo "$RESP" | grep -qi "error\|无效\|fail\|401\|400\|422\|rate limit"; then
    MARK="❌"
  else
    MARK="✅"
  fi
  PIXELS=$(( W * H ))
  echo "  ${W}x${H} (${PIXELS}px) | ${MARK}  ${RESP:0:80}"
done
