# Keep system and Kage command directories available in login and desktop shells.
PATH=${PATH:-/usr/local/bin:/usr/bin:/bin}
for kage_path in /usr/local/bin /usr/local/sbin /usr/sbin /sbin; do
    case ":$PATH:" in
        *":$kage_path:"*) ;;
        *) PATH="$PATH:$kage_path" ;;
    esac
done
export PATH
unset kage_path
