import mimetypes
from pathlib import Path
from typing import Generator


def touch(file_paths: list[Path | str]) -> None:
    """
    Create files and any missing parent directories.

    Arguments:
        file_paths: List of strings or Path objects representing the files to create.
    """
    for file_path in map(Path, file_paths):
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.touch(exist_ok=True)


def mkdirp(dir_paths: list[Path | str]) -> None:
    """
    Create directories and missing parent directories. Like `mkdir -p` in Linux.

    Args:
        dir_paths: A list of strings or Path objects representing directories to create.
    """

    for dir_path in map(Path, dir_paths):
        dir_path.mkdir(parents=True, exist_ok=True)


def get_media_files(directory: Path) -> Generator[Path, None, None]:
    """
    Get all media files in a directory.

    Arguments:
        directory: Directory to get media files from.
    """
    for file in directory.glob("**/*"):
        if file.is_file():
            mime_type, _ = mimetypes.guess_type(str(file))
            if (
                mime_type
                and mime_type is not None
                and (
                    mime_type.startswith("audio/")
                    or mime_type.startswith("video/")
                    or mime_type == "application/octet-stream"
                )
            ):
                yield file


def next_non_existent_file(filename: Path | str) -> Path:
    """
    Generate name for next non-existant file
    Example:
         if "test.txt" exists then next file will be
        "test_1.txt"

    Arguments:
        filename: Name of file

    Returns:
        Name of next non-existant file
    """
    base_dir = Path(filename).parent.absolute()
    nf = Path(filename)
    root, ext = nf.stem, nf.suffix
    i = 0
    while nf.exists():
        i += 1
        nf = base_dir / f"{root}_{i}{ext}"
    return nf
