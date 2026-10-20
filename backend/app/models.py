from datetime import datetime, date as DateType, timezone
from decimal import Decimal
from sqlalchemy import String, Integer, Date, DateTime, Numeric, JSON, Text, Boolean, UniqueConstraint, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

Money = Numeric(14, 2)


class Quarter(Base):
    __tablename__ = "quarters"
    __table_args__ = (UniqueConstraint("year", "q"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer)
    q: Mapped[int] = mapped_column(Integer)
    prorata: Mapped[int] = mapped_column(Integer, default=100)
    ras_subie: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    # Ecarts marqués « expliqués » : {"deductible": "commentaire", ...}
    explained: Mapped[dict] = mapped_column(JSON, default=dict)


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    direction: Mapped[str] = mapped_column(String(10))  # vente | achat
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500), default="")
    sha256: Mapped[str] = mapped_column(String(64), default="")
    number: Mapped[str] = mapped_column(String(80), default="")
    date: Mapped[DateType | None] = mapped_column(Date, nullable=True)
    party_name: Mapped[str] = mapped_column(String(200), default="")
    party_ice: Mapped[str] = mapped_column(String(30), default="")
    categorie: Mapped[str] = mapped_column(String(20), default="charge")  # charge | immobilisation | non_deductible
    lines: Mapped[list] = mapped_column(JSON, default=list)  # [{rate, base_ht, tva}]
    total_ht: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    total_tva: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    total_ttc: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    paid_date: Mapped[DateType | None] = mapped_column(Date, nullable=True)
    paid_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    pay_mode: Mapped[str] = mapped_column(String(20), default="")
    status: Mapped[str] = mapped_column(String(20), default="a_verifier")
    # a_verifier | validee | doublon_detecte | doublon_ignore | remplacee
    confidence: Mapped[dict] = mapped_column(JSON, default=dict)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    original_values: Mapped[dict] = mapped_column(JSON, default=dict)
    extraction_source: Mapped[str] = mapped_column(String(20), default="")
    dup_of: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dup_kind: Mapped[str] = mapped_column(String(10), default="")  # certain | probable
    dup_justification: Mapped[str] = mapped_column(Text, default="")
    forced_comment: Mapped[str] = mapped_column(Text, default="")  # inclusion forcée d'une facture non conforme
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class Declaration(Base):
    """Montants de la déclaration déposée par le comptable, pour un trimestre."""
    __tablename__ = "declarations"
    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer)
    q: Mapped[int] = mapped_column(Integer)
    collectee_20: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    collectee_10: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    deductible_charges: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    deductible_immo: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    credit_anterieur: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    tva_due: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    credit_reporte: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    source: Mapped[str] = mapped_column(String(20), default="manuelle")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    action: Mapped[str] = mapped_column(String(40))
    target: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class FileBlob(Base):
    """Copie du fichier source en base (hébergeurs dont le disque est temporaire, ex. Render gratuit)."""
    __tablename__ = "file_blobs"
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
