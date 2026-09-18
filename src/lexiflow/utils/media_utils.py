from pathlib import Path

from audioread import audio_open  # type: ignore


def round_up(number: float) -> float:
    if number % 0.5 == 0:
        return number
    else:
        return number + 0.5 - (number % 0.5)


def seconds_to_minutes(seconds: float) -> float:
    minutes = (seconds // 60) + ((seconds % 60) / 60)
    return round_up(minutes)


def get_media_duration(media_file: Path) -> float:
    with audio_open(media_file) as mf:
        duration = mf.duration
    return seconds_to_minutes(duration)
