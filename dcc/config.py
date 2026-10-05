"""Static configuration: paths + the two (and only two) in-scope municipalities."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SOURCES_DIR = ROOT / "sources"
DB_PATH = ROOT / "db" / "dcc.sqlite3"
DAY1_NORMALIZED = DATA_DIR / "normalized.json"
SOURCES_MANIFEST = DATA_DIR / "sources_manifest.json"

# Scope is STRICTLY Surrey + Victoria. Slug -> source registry.
# Values here mirror data/sources_manifest.json and add pipeline metadata.
# Surrey local_path is where an operator may place a privately fetched PDF.
# That PDF is not in the public repository.
MUNICIPALITIES: dict[str, dict] = {
    "surrey": {
        "municipality": "Surrey",
        "province": "BC",
        "source_id": "surrey-bylaw-21174",
        "bylaw_id": "21174",
        "title": "Surrey Development Cost Charge Bylaw, 2024, No. 21174",
        "source_document": "surrey_BYL_reg_21174.pdf",
        "local_path": "sources/surrey_BYL_reg_21174.pdf",
        "source_url": "https://www.surrey.ca/sites/default/files/bylaws/BYL_reg_21174.pdf",
        "source_retrieval_method": "official_https",
        "provisional": False,
        "provisional_reason": None,
        "wayback_url": None,
        "wayback_timestamp": None,
        # pdfinfo CreationDate of the official scanned PDF (RICOH scan, 2024-05-13 PDT)
        "source_version_date": "2024-05-13",
        "source_version_basis": "PDF CreationDate (pdfinfo) of official surrey.ca file",
        "effective_date": "2024-05-15",
        "effective_date_basis": "Bylaw-defined effective date May 15, 2024",
        "status": "current_operative",
        "caveats": [
            "A proposed 2026 Surrey DCC bylaw was Council-approved for provincial submission (May 2026) "
            "but is NOT adopted; its rates are not served.",
            "Area applicability: City Centre = Schedule B + C; West Clayton = Schedule B + G; "
            "Anniedale-Tynehead / Redwood Heights / Darts Hill = Schedule D / E / F only (replace B).",
        ],
    },
    "victoria": {
        "municipality": "Victoria",
        "province": "BC",
        "source_id": "victoria-bylaw-24-053",
        "bylaw_id": "24-053",
        "title": "City of Victoria Development Cost Charges Bylaw No. 24-053 (2024)",
        "source_document": "victoria_dcc_bylaw_24-053.pdf",
        "local_path": "sources/victoria_dcc_bylaw_24-053.pdf",
        "text_path": "sources/victoria_dcc_bylaw_24-053.txt",
        "source_url": "https://www.victoria.ca/media/file/development-cost-charges-bylaw-24-053",
        "source_retrieval_method": "wayback_provisional",
        "provisional": True,
        "provisional_reason": (
            "PROVISIONAL: PDF retrieved from Internet Archive Wayback snapshot 20250829015529 of the "
            "official victoria.ca URL because the live download is bot-gated. This is NOT a fresh live "
            "retrieval from victoria.ca. Re-fetch live and re-hash before treating as confirmed."
        ),
        "wayback_url": "http://web.archive.org/web/20250829015529id_/https://www.victoria.ca/media/file/development-cost-charges-bylaw-24-053",
        "wayback_timestamp": "20250829015529",
        # pdfinfo CreationDate of the archived PDF (Acrobat PDFMaker from 00153616.DOCX;4)
        "source_version_date": "2024-11-15",
        "source_version_basis": "PDF CreationDate (pdfinfo) of Wayback-archived official file; Wayback capture 2025-08-29",
        "effective_date": "2024-11-14",
        "effective_date_basis": "s.8 'comes into force on adoption'; adopted 2024-11-14",
        "status": "current_operative",
        "caveats": [
            "City 'Guide to Building Permit Fees' shows ~2.3% higher amounts (possible CPI indexing); "
            "no adopted amendment bylaw located. Schedule A values served; fee-guide values omitted.",
        ],
    },
}


def resolve_slug(name: str) -> str | None:
    s = name.strip().lower()
    return s if s in MUNICIPALITIES else None
