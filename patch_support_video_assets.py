"""Replace the MP3 walkthrough entries in _SUPPORT_ASSETS with the new
MP4 video versions. The MP3s are kept on disk (and via git history)
but the support page no longer surfaces them — MP4 = audio + paired
screenshot, which is what the user asked for ("audios need screenshots").

Pattern A byte replace because web_app.py has CRLF + mojibake.
"""
from pathlib import Path

WEB = Path(r"C:\Users\USER\Desktop\solar-pv-designer-lite\web_app.py")
data = WEB.read_bytes()

OLD = (
    b'    # Audio walkthroughs (edge-tts, en-US-AriaNeural / en-US-GuyNeural)\r\n'
    b'    "user-walkthrough": ("SolarPro_User_Walkthrough.mp3", "audio/mpeg"),\r\n'
    b'    "tech-walkthrough": ("SolarPro_Tech_Walkthrough.mp3", "audio/mpeg"),\r\n'
)
NEW = (
    b'    # Video walkthroughs (edge-tts MP3 + paired screenshot composited\r\n'
    b'    # into MP4 via ffmpeg; 2026-06-17 user request "audios need to\r\n'
    b'    # have screenshots"). The MP3-only files are still on disk if\r\n'
    b'    # someone needs audio-only - just not exposed here.\r\n'
    b'    "user-walkthrough": ("SolarPro_User_Walkthrough.mp4", "video/mp4"),\r\n'
    b'    "tech-walkthrough": ("SolarPro_Tech_Walkthrough.mp4", "video/mp4"),\r\n'
)

if OLD not in data:
    raise SystemExit("anchor not found - shape changed (already patched?)")
data = data.replace(OLD, NEW, 1)
WEB.write_bytes(data)
print("patched _SUPPORT_ASSETS to serve MP4 walkthroughs")
