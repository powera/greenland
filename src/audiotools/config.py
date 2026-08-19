#!/usr/bin/env python3
"""
Configuration settings for the audio checker library.
"""

# OpenAI API Configuration
DEFAULT_MODEL = "gpt-4o-mini-audio-preview-2024-12-17"  # Model for audio analysis
API_KEY_FILE = "keys/openai.key"  # Default location for API key
REQUEST_TIMEOUT = 60  # Timeout for API requests in seconds
MAX_RETRIES = 3  # Number of retries for failed requests

# Audio Processing Configuration
SUPPORTED_FORMATS = [".mp3", ".wav", ".m4a", ".ogg"]  # Supported audio formats
MAX_AUDIO_SIZE_MB = 25  # Maximum audio file size in MB
DEFAULT_LANGUAGE = "Lithuanian"  # Default language for analysis

# Analysis Configuration
DEFAULT_TEMPERATURE = 0.1  # Low temperature for consistent results
CONFIDENCE_THRESHOLD = 0.7  # Minimum confidence for reliable results
BATCH_SIZE = 10  # Number of files to process in each batch

# Quality Issue Detection Sensitivity
ISSUE_DETECTION_SETTINGS = {
    "breath_sensitivity": "medium",  # low, medium, high
    "noise_sensitivity": "medium",
    "pronunciation_strictness": "medium",
    "clarity_threshold": 0.8
}

# Output Configuration
DETAILED_LOGGING = True  # Enable detailed logging
SAVE_TRANSCRIPTS = False  # Save transcripts to files
TRANSCRIPT_DIR = "transcripts"  # Directory for saved transcripts

# Language-Specific Settings
LANGUAGE_CONFIGS = {
    "Lithuanian": {
        "pronunciation_guide": "Standard Lithuanian pronunciation",
        "common_issues": ["palatalization", "vowel_length", "stress_patterns"],
        "special_characters": "ąčęėįšųūž"
    },
    "English": {
        "pronunciation_guide": "Standard American English pronunciation", 
        "common_issues": ["th_sounds", "r_sounds", "vowel_reduction"],
        "special_characters": ""
    }
}

# Error Handling
CONTINUE_ON_ERROR = True  # Continue batch processing if individual files fail
LOG_ERRORS = True  # Log errors to file
ERROR_LOG_FILE = "audio_checker_errors.log"