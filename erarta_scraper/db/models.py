from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from erarta_scraper.domain.status import ArtworkStatus


class Base(DeclarativeBase):
    pass


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    artworks: Mapped[List["Artwork"]] = relationship(back_populates="artist")


class Artwork(Base):
    __tablename__ = "artworks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    artist_id: Mapped[Optional[int]] = mapped_column(ForeignKey("artists.id", ondelete="SET NULL"))
    artist: Mapped[Optional["Artist"]] = relationship(back_populates="artworks")

    price: Mapped[Optional[float]] = mapped_column(Float)
    size: Mapped[Optional[str]] = mapped_column(String(100))
    year: Mapped[Optional[int]] = mapped_column(Integer)
    art_type: Mapped[Optional[str]] = mapped_column(String(100))
    genre: Mapped[Optional[str]] = mapped_column(String(100))
    technique: Mapped[Optional[str]] = mapped_column(String(200))
    baguette: Mapped[Optional[str]] = mapped_column(String(50))

    status: Mapped[str] = mapped_column(
        String(20),
        default=ArtworkStatus.PENDING.value,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
