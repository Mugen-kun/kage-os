# Keep a shell or user-provided handler when one is already defined.
if [ -n "${BASH_VERSION-}" ] && ! command -v command_not_found_handle >/dev/null 2>&1; then
    command_not_found_handle() {
        /usr/bin/python3 /usr/share/kage/terminal.py --oner="$1"
        return 127
    }
elif [ -n "${ZSH_VERSION-}" ] && ! command -v command_not_found_handler >/dev/null 2>&1; then
    command_not_found_handler() {
        /usr/bin/python3 /usr/share/kage/terminal.py --oner="$1"
        return 127
    }
fi
