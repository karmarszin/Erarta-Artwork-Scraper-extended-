from enum import Enum


class ArtworkStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    ERROR = "error"
