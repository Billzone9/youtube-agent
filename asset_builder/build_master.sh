#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLIPS_DIR="$ROOT/assets/clips"
NORM_DIR="$ROOT/assets/_norm"
CONCAT_FILE="$ROOT/assets/_concat.txt"
VIDEO_TMP="$ROOT/assets/_video.mp4"
OUT_TMP="$ROOT/assets/_master_tmp.mp4"
OUT="$ROOT/assets/master.mp4"
SCENE_SECONDS=60

rm -rf "$NORM_DIR"; mkdir -p "$NORM_DIR"
: > "$CONCAT_FILE"

i=0
for f in "$CLIPS_DIR"/*; do
  case "${f##*.}" in
    mp4|MP4|mov|MOV|webm|WEBM|mkv|MKV|m4v|M4V) : ;;
    *) continue ;;
  esac
  [ -f "$f" ] || continue
  out="$NORM_DIR/norm_$(printf '%03d' "$i").mp4"
  echo "Normalising scene $i: $(basename "$f")"
  ffmpeg -y -stream_loop -1 -t "$SCENE_SECONDS" -i "$f" -an \
    -vf "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,fps=30,format=yuv420p" \
    -c:v libx264 -preset veryfast -crf 23 -maxrate 10M -bufsize 20M -g 60 -keyint_min 60 -sc_threshold 0 "$out"
  echo "file '$out'" >> "$CONCAT_FILE"
  i=$((i+1))
done

if [ "$i" -eq 0 ]; then echo "NO CLIPS FOUND in assets/clips"; exit 1; fi

echo "Joining $i scenes..."
ffmpeg -y -f concat -safe 0 -i "$CONCAT_FILE" -c copy "$VIDEO_TMP"

echo "Applying synthetic claim-free ocean soundscape..."
ffmpeg -y -i "$VIDEO_TMP" \
  -filter_complex "\
anoisesrc=color=brown:amplitude=0.9:duration=99999[brn]; \
anoisesrc=color=pink:amplitude=0.5:duration=99999[pnk]; \
[brn]lowpass=f=500,volume=1.0[brnf]; \
[pnk]highpass=f=400,lowpass=f=2000,volume=0.35[pnkf]; \
[brnf][pnkf]amix=inputs=2:duration=longest:normalize=0[mix]; \
[mix]volume=volume='0.55+0.45*sin(2*PI*t/14)':eval=frame[swell]; \
[swell]aformat=channel_layouts=stereo,loudnorm=I=-18:TP=-1.5[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -shortest "$OUT_TMP"

mv -f "$OUT_TMP" "$OUT"
rm -f "$VIDEO_TMP" "$CONCAT_FILE"
rm -rf "$NORM_DIR"
echo "DONE - master.mp4 rebuilt with claim-free synthetic ocean soundscape."
