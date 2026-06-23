#!/usr/bin/env bash
#
# Agnes Video V2.0 极限参数测试
# 使用 curl 快速测试：各 FPS 的最大 num_frames & 最大分辨率

KEY="sk-KNdtRXxslHMgqX3BEEyk6lYunvfvawvkyiehgT8gHS4JkWth"
BASE="https://apihub.agnes-ai.com/v1"
MODEL="agnes-video-v2.0"
PROMPT="A calm lake at sunrise, gentle ripples, soft golden light, cinematic wide shot, no people, peaceful nature"

echo "==== 阶段 1：测试各 FPS 的最大 num_frames（分辨率 1152×768）===="
echo ""

for FPS in 24 30 60; do
  for NF in 81 121 161 241 441; do
    DUR=$(python3 -c "print(f'{${NF}/${FPS}:.2f}')" 2>/dev/null || echo "?")
    RESP=$(curl -s -X POST "${BASE}/videos" \
      -H "Authorization: Bearer ${KEY}" \
      -H "Content-Type: application/json" \
      --connect-timeout 10 --max-time 30 \
      -d "{\"model\":\"${MODEL}\",\"prompt\":\"${PROMPT}\",\"num_frames\":${NF},\"frame_rate\":${FPS},\"width\":1152,\"height\":768}" 2>&1)
    STATUS=$(echo "$RESP" | python3 -c "import sys,json; d=sys.stdin.read(); print(json.loads(d).get('code','') or '202')" 2>/dev/null || echo "202")
    # 如果 response 里含 error/失败，标红
    if echo "$RESP" | grep -qi "error\|无效\|fail\|401\|400\|422"; then
      MARK="❌"
    else
      MARK="✅"
    fi
    echo "  FPS=${FPS} | frames=${NF} | ${DUR}s | ${MARK}  ${RESP:0:120}"
  done
  echo ""
done

echo "==== 阶段 2：测试 num_frames=441 × 各 FPS × 各分辨率 ===="
echo ""

for FPS in 24 30 60; do
  for RES in "768,512" "1152,768" "1280,720" "1920,1080" "2048,2048" "3840,2160" "4096,4096"; do
    W=$(echo "$RES" | cut -d, -f1)
    H=$(echo "$RES" | cut -d, -f2)
    RESP=$(curl -s -X POST "${BASE}/videos" \
      -H "Authorization: Bearer ${KEY}" \
      -H "Content-Type: application/json" \
      --connect-timeout 10 --max-time 30 \
      -d "{\"model\":\"${MODEL}\",\"prompt\":\"${PROMPT}\",\"num_frames\":441,\"frame_rate\":${FPS},\"width\":${W},\"height\":${H}}" 2>&1)
    if echo "$RESP" | grep -qi "error\|无效\|fail\|401\|400\|422\|rate limit"; then
      MARK="❌"
    else
      MARK="✅"
    fi
    echo "  FPS=${FPS} | frames=441 | ${W}x${H} | ${MARK}  ${RESP:0:120}"
  done
  echo ""
done
