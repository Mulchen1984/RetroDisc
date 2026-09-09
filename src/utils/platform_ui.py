"""Native desktop presentation without guessed OS versions."""
import platform


def platform_info():
    system = platform.system()
    if system == 'Darwin':
        version = platform.mac_ver()[0]
        label = 'macOS' + (f' {version}' if version else '')
    elif system == 'Windows':
        # Report kernel/build directly: release() may call Windows 11 "10".
        version = platform.version()
        label = 'Windows' + (f' ({version})' if version else '')
    else:
        label = system or 'Unbekanntes Betriebssystem'
    return {'system': system, 'label': label, 'native_controls': True}


def native_window_options():
    return {'frameless': False, 'resizable': True}
