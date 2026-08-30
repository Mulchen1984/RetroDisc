"""RetroDisc Setup."""

from setuptools import setup, find_packages

setup(
    name="retrodisc",
    version="0.1.0",
    description="All-in-One Media Suite — Konvertieren, Brennen, Downloaden, AI-Enhanced",
    author="Marco",
    packages=find_packages(),
    python_requires=">=3.11",
    entry_points={
        "console_scripts": [
            "retrodisc=src.__main__:cli",
        ],
    },
    install_requires=[
        "pymediainfo>=6.1.0",
        "structlog>=24.1.0",
        "pydantic>=2.5.0",
        "rich>=13.7.0",
        "click>=8.1.0",
        "yt-dlp>=2024.1.0",
        "httpx>=0.27.0",
        "sounddevice>=0.4.6",
        "soundfile>=0.12.1",
    ],
    extras_require={
        "ai": [
            "openai-whisper>=20231117",
            "scenedetect[opencv]>=0.6",
            "librosa>=0.10.0",
            "mediapipe>=0.10.0",
            "numpy>=1.26.0",
            "opencv-python>=4.9.0",
        ],
        "dev": [
            "pytest>=8.0.0",
            "pytest-asyncio>=0.23.0",
            "pytest-mock>=3.12.0",
        ],
    },
)
