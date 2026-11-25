#!/usr/bin/env bash
# ==============================================================================
#  KAFKA WALLPAPER CYCLER (AWWW, trước đây là swww)
#  Usage:
#    wallpaper-cycle.sh init            -> Load wallpaper at saved index
#    wallpaper-cycle.sh next|prev       -> Cycle with transition and notification
#    wallpaper-cycle.sh random          -> Show a different random wallpaper
#    wallpaper-cycle.sh auto [SECONDS]  -> Cycle silently until stopped
#    wallpaper-cycle.sh set FILE        -> Show one fixed wallpaper
# ===============================================================================

WALL_DIR="$HOME/.config/hypr/wallpapers"
STATE_FILE="$HOME/.cache/kafka_wallpaper_idx"
DIMS_CACHE="$HOME/.cache/kafka_wallpaper_dims"
CURRENT_LINK="$HOME/.cache/kafka_current_wallpaper"

mkdir -p "$HOME/.cache"
declare -a WALLS
declare -A CACHE_MTIME CACHE_DIMS
if [ -f "$DIMS_CACHE" ]; then
    while IFS=$'\t' read -r cache_mtime cache_width cache_height cache_path; do
        [ -n "$cache_path" ] || continue
        CACHE_MTIME["$cache_path"]="$cache_mtime"
        CACHE_DIMS["$cache_path"]="$cache_width $cache_height"
    done <"$DIMS_CACHE"
fi
mapfile -t CANDIDATES < <(find "$WALL_DIR/" -maxdepth 1 -type f \( -iname 'kafka_*.jpg' -o -iname 'kafka_*.jpeg' -o -iname 'kafka_*.png' \) -print 2>/dev/null | sort -f)

IDENTIFY_CMD=()
if command -v magick >/dev/null 2>&1; then
    IDENTIFY_CMD=(magick identify -format '%w %h')
elif command -v identify >/dev/null 2>&1; then IDENTIFY_CMD=(identify -format '%w %h'); fi
CACHE_TMP=''
if [ "${#IDENTIFY_CMD[@]}" -gt 0 ]; then CACHE_TMP=$(mktemp "$DIMS_CACHE.XXXXXX") || exit 1; fi

for file in "${CANDIDATES[@]}"; do
    mtime=$(stat -c '%Y' -- "$file" 2>/dev/null) || continue
    width='' height=''
    if [ -n "${CACHE_MTIME[$file]+x}" ] && [ "${CACHE_MTIME[$file]}" = "$mtime" ]; then
        read -r width height <<<"${CACHE_DIMS[$file]}"
    elif [ "${#IDENTIFY_CMD[@]}" -gt 0 ]; then
        read -r width height < <("${IDENTIFY_CMD[@]}" "${file}[0]" 2>/dev/null)
    fi

    if [ "${#IDENTIFY_CMD[@]}" -gt 0 ]; then
        printf '%s\t%s\t%s\t%s\n' "$mtime" "$width" "$height" "$file" >>"$CACHE_TMP"
        [[ "$width" =~ ^[0-9]+$ && "$height" =~ ^[0-9]+$ ]] || continue
        [ "$width" -gt "$height" ] || continue
    elif [ "$(basename "$file")" = 'kafka_main.jpg' ]; then
        continue
    fi
    WALLS+=("$file")
done
if [ -n "$CACHE_TMP" ]; then mv -f "$CACHE_TMP" "$DIMS_CACHE"; fi
# Danh sách trống: chỉ lệnh set (ảnh chỉ định sẵn) còn làm được việc
[ "${#WALLS[@]}" -gt 0 ] || [ "${1-}" = set ] || exit 0
IDX=0
if [ -f "$STATE_FILE" ]; then IDX=$(<"$STATE_FILE"); fi
[[ "$IDX" =~ ^[0-9]+$ ]] || IDX=0
[ "${#WALLS[@]}" -gt 0 ] && IDX=$((IDX % ${#WALLS[@]}))
apply_wallpaper() {
    local index="$1" transition="$2" selected="${WALLS[$1]}"
    if [ "$transition" = 'fade' ]; then
        awww img "$selected" --transition-type fade
    else
        awww img "$selected" \
            --transition-type outer \
            --transition-pos 0.85,0.85 \
            --transition-step 90 \
            --transition-fps 60
    fi || return 1

    ln -sfn "$selected" "$CURRENT_LINK"
    printf '%s\n' "$index" >"$STATE_FILE"
    IDX="$index"
}
usage() {
    printf 'Usage: %s {init|next|prev|random|auto [SECONDS]|set FILE}\n' "$0" >&2
}
case "${1-}" in
    init)
        apply_wallpaper "$IDX" fade
        ;;
    set)
        [ -f "${2-}" ] || {
            usage
            exit 1
        }
        target="$(readlink -f "$2")"
        for i in "${!WALLS[@]}"; do
            if [ "$(readlink -f "${WALLS[$i]}")" = "$target" ]; then
                apply_wallpaper "$i" fade
                exit $?
            fi
        done
        # Ảnh không nằm trong danh sách (vd. ảnh dọc): vẫn đặt được
        awww img "$2" --transition-type fade && ln -sfn "$target" "$CURRENT_LINK"
        ;;
    step)
        # Bước của vòng auto: quét lại thư mục, đọc chỉ số mới nhất, đổi êm không thông báo
        apply_wallpaper "$(((IDX + 1) % ${#WALLS[@]}))" fade
        ;;
    next | prev)
        if [ "$1" = 'next' ]; then
            IDX=$(((IDX + 1) % ${#WALLS[@]}))
        else
            IDX=$(((IDX - 1 + ${#WALLS[@]}) % ${#WALLS[@]}))
        fi
        if apply_wallpaper "$IDX" outer; then
            notify-send '🕷 Kafka Wallpaper' "Đã đổi sang: $(basename "${WALLS[$IDX]}")"
        fi
        ;;
    random)
        if [ "${#WALLS[@]}" -gt 1 ]; then
            random_idx=$((RANDOM % ${#WALLS[@]}))
            while [ "$random_idx" -eq "$IDX" ]; do
                random_idx=$((RANDOM % ${#WALLS[@]}))
            done
            IDX="$random_idx"
        fi
        if apply_wallpaper "$IDX" outer; then
            notify-send '🕷 Kafka Wallpaper' "Đã đổi sang: $(basename "${WALLS[$IDX]}")"
        fi
        ;;
    auto)
        delay="${2-600}"
        [[ "$delay" =~ ^[1-9][0-9]*$ ]] || delay=600
        exec 9>"$HOME/.cache/kafka_wallpaper_auto.lock"
        flock -n 9 || exit 0
        self="$(readlink -f "$0")"
        while true; do
            sleep "$delay"
            "$self" step 9>&-
        done
        ;;
    *)
        usage
        exit 1
        ;;
esac
