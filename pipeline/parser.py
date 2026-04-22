import re
from pathlib import Path

from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import ConversionStatus
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class DocMetadata(BaseModel):
    doc_name: str
    manufacturer: str | None = None
    model: str | None = None
    equipment_type: str | None = None
    document_type: str | None = None  # "service_manual", "user_guide", etc.


_EQUIPMENT_KEYWORDS = {
    "x_ray": ["x-ray", "xray", "radiograph", "fluoroscopy", "fdr", "digital radiography", "dr system"],
    "ultrasound": ["ultrasound", "sonography", "echography", "ultrasonic"],
    "mri": ["mri", "magnetic resonance", "nmr"],
    "ct_scanner": ["ct scanner", "computed tomography", "cat scan"],
    "ventilator": ["ventilator", "respirator", "breathing machine", "ventilation"],
    "infusion_pump": ["infusion pump", "syringe pump", "iv pump", "peristaltic"],
    "patient_monitor": ["patient monitor", "vital signs", "multiparameter", "cardiac monitor"],
    "defibrillator": ["defibrillator", "aed", "cardioverter", "defibrillation"],
    "anesthesia": ["anesthesia", "anaesthesia", "anesthetic machine", "anesthetic"],
    "dialysis": ["dialysis", "hemodialysis", "nephology"],
    "incubator": ["incubator", "neonatal", "nicu"],
    "sterilizer": ["sterilizer", "autoclave", "steam sterilizer"],
    "centrifuge": ["centrifuge", "microcentrifuge"],
    "blood_gas": ["blood gas", "gas analyzer", "electrolyte analyzer"],
    "hemoglobin": ["hemoglobin", "hemocue", "hematology"],
    "surgical_light": ["surgical light", "operation light", "operating lamp"],
    "dehumidifier": ["dehumidifier", "humidification system"],
}

_DOC_TYPE_KEYWORDS = {
    "service_manual": ["service manual", "service guide", "technical manual", "maintenance manual", "field service"],
    "user_guide": ["user guide", "user manual", "operator manual", "operator guide", "instructions for use", "ifu"],
    "installation_manual": ["installation manual", "installation guide", "setup guide"],
    "parts_catalog": ["parts catalog", "parts list", "spare parts"],
    "quick_reference": ["quick reference", "quick guide", "quick start"],
}


def _extract_metadata(text_sample: str, filename: str) -> DocMetadata:
    """Heuristically extract metadata from the first ~3 pages of text."""
    doc_name = Path(filename).stem
    sample_lower = text_sample.lower()

    # Manufacturer: common medical device brands
    manufacturer = None
    brand_pattern = r"FUJIFILM|SIEMENS|GE|PHILIPS|CANON|RICOH|KONICA|MINOLTA|AGFA|CARESTREAM|KODAK|VARIAN|TOSHIBA|HITACHI|OLYMPUS|PENTAX|ZEISS|CARL ZEISS"
    mfr_match = re.search(brand_pattern, text_sample, re.IGNORECASE)
    if mfr_match:
        manufacturer = mfr_match.group().strip()

    # Model: look for common patterns like FDR-1000, Model X, etc.
    model = None
    # Try equipment-specific patterns first (e.g., FDR-1000, FSX-100)
    model_match = re.search(r"(?:FDR|FSX|DRX|AXIOM)-[\d/\-A-Z]+", text_sample, re.IGNORECASE)
    if not model_match:
        # Fall back to generic Model/Ref patterns
        model_match = re.search(
            r"(?:model\s*(?:no\.?|number)?|part\s*(?:no\.?|number)?|ref\.?)[:\s#]+([A-Z0-9][A-Za-z0-9\-_/. ]{1,30})",
            text_sample,
            re.IGNORECASE,
        )
    if model_match:
        model = model_match.group(1) if model_match.lastindex else model_match.group()
        model = model.strip()

    # Equipment type: scan for keyword matches
    equipment_type = None
    for eq_type, keywords in _EQUIPMENT_KEYWORDS.items():
        if any(kw in sample_lower for kw in keywords):
            equipment_type = eq_type
            break

    # Document type: scan for keyword matches
    document_type = None
    for doc_type, keywords in _DOC_TYPE_KEYWORDS.items():
        if any(kw in sample_lower for kw in keywords):
            document_type = doc_type
            break

    return DocMetadata(
        doc_name=doc_name,
        manufacturer=manufacturer,
        model=model,
        equipment_type=equipment_type,
        document_type=document_type,
    )


class ParsedDocument:
    """Container for parsed PDF output."""

    def __init__(self, metadata: DocMetadata, markdown: str, docling_doc):
        self.metadata = metadata
        self.markdown = markdown
        self.docling_doc = docling_doc  # raw docling Document, needed by chunker


def parse_pdf(file_path: str | Path) -> ParsedDocument:
    """Convert a PDF to Markdown and extract document-level metadata."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    converter = DocumentConverter()
    result = converter.convert(str(file_path))

    if result.status not in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS):
        raise RuntimeError(f"docling conversion failed with status: {result.status}")

    doc = result.document
    markdown = doc.export_to_markdown()

    # Use first ~4000 chars as the sample for metadata extraction
    text_sample = markdown[:4000]
    metadata = _extract_metadata(text_sample, file_path.name)

    return ParsedDocument(metadata=metadata, markdown=markdown, docling_doc=doc)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.parser <path/to/file.pdf>")
        sys.exit(1)

    parsed = parse_pdf(sys.argv[1])
    print("=== Metadata ===")
    print(parsed.metadata.model_dump_json(indent=2))
    print(f"\n=== Markdown preview (first 500 chars) ===\n{parsed.markdown[:500]}")
