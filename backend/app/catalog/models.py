"""View catalog с отдельными metadata; Alembic не считает её таблицей."""

from sqlalchemy import Column, DateTime, MetaData, String, Table, Uuid

catalog_cards = Table(
    "catalog_cards",
    MetaData(),
    Column("id", Uuid, primary_key=True),
    Column("title_generic", String(80)),
    Column("industry", String(32)),
    Column("region_macro", String(32)),
    Column("size_band", String(32)),
    Column("revenue_band", String(32)),
    Column("deal_type", String(32)),
    Column("teaser_text", String(600)),
    Column("published_at", DateTime(timezone=True)),
)
