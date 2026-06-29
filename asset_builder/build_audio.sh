#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VIDEO="$ROOT/assets/_video.mp4"
OUT="$ROOT/assets/master.mp4"

if [ ! -f "$VIDEO" ]; then echo "No _video.mp4 found - run the main build first"; exit 1; fi

DUR=$(ffmpeg -hide_banner -i "$VIDEO" 2>&1 | awk '/Duration/{print $2}' | tr -d , )
echo "Video duration: $DUR"

ffmpeg -y -i "$VIDEO" \
  -filter_complex "\
anoisesrc=color=brown:amplitude=0.9:duration=99999[brn]; \
anoisesrc=color=pink:amplitude=0.5:duration=99999[pnk]; \
[brn]lowpass=f=500,volume=1.0[brnf]; \
[pnk]highpass=f=400,lowpass=f=2000,volume=0.35[pnkf]; \
[brnf][pnkf]amix=inputs=2:duration=longest:normalize=0[mix]; \
[mix]tremolo=f=0.08:d=0.7[swell]; \
[swell]aformat=channel_layouts=stereo,loudnorm=I=-18:TP=-1.5[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -shortest "$OUT" \
  && echo "OK - synthetic claim-free ocean soundscape applied" || echo "FAILED - send me the output"
