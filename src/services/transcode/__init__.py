"""RetroDisc transcoding backend: hardware detection, profiles, encoder
selection, ffprobe, command building, jobs, progress, verification.

Pure backend layer (no UI). Everything that talks to FFmpeg goes through an
injectable process runner so the whole package is unit-testable without FFmpeg.
"""
