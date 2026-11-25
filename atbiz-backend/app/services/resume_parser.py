import re
import io
import zipfile
from typing import Optional, Dict, Any, Tuple
from pydantic import BaseModel
from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError
from docx import Document

class ParsedResume(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: str
    dob: Optional[str] = None
    location: Optional[str] = None
    last_qualification: Optional[str] = None
    experience_years: Optional[float] = 0.0
    raw_text: str
    extracted_attributes: Dict[str, Any] = {}
    is_password_protected: bool = False
    is_corrupt: bool = False
    confidence: str = "high"

class ResumeParser:
    @staticmethod
    def validate_file_type(file_bytes: bytes, file_name: str) -> Tuple[bool, str]:
        """
        Validate file authenticity using magic bytes and archive structure.
        Returns (is_valid, detected_type).
        """
        fname = file_name.lower()
        if fname.endswith(".pdf"):
            if file_bytes.startswith(b"%PDF-"):
                return True, "application/pdf"
            return False, "invalid_pdf_magic_bytes"

        if fname.endswith(".docx"):
            if not file_bytes.startswith(b"PK\x03\x04"):
                return False, "invalid_zip_header"
            try:
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                    names = zf.namelist()
                    if "word/document.xml" in names:
                        return True, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    return False, "zip_not_a_valid_docx"
            except Exception:
                return False, "corrupted_docx_archive"

        if fname.endswith(".doc"):
            if file_bytes.startswith(b"\xd0\xcf\x11\xe0"):
                return True, "application/msword"
            return False, "invalid_doc_header"

        return False, "unsupported_extension"

    @staticmethod
    def extract_text_from_pdf(file_bytes: bytes) -> Tuple[str, bool]:
        """Extract plain text from PDF bytes. Returns (text, is_password_protected)."""
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            if reader.is_encrypted:
                try:
                    # Attempt empty password decryption
                    reader.decrypt("")
                except Exception:
                    return "", True
            text_parts = []
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text_parts.append(extracted)
            return "\n".join(text_parts).strip(), False
        except (FileNotDecryptedError, PdfReadError):
            return "", True
        except Exception:
            try:
                return file_bytes.decode('utf-8', errors='ignore').strip(), False
            except Exception:
                return "", False

    @staticmethod
    def extract_text_from_docx(file_bytes: bytes) -> str:
        """Extract plain text from DOCX bytes using python-docx."""
        try:
            doc = Document(io.BytesIO(file_bytes))
            return "\n".join([p.text for p in doc.paragraphs if p.text]).strip()
        except Exception:
            try:
                return file_bytes.decode('utf-8', errors='ignore').strip()
            except Exception:
                return ""

    @staticmethod
    def extract_phone(text: str) -> Optional[str]:
        """Match standard Indian and international phone numbers with flexible spacing/dashes."""
        pattern = r'(?:(?:\+?91|0)[\s\-]?)?([6789](?:[\s\-]?\d){9})'
        match = re.search(pattern, text)
        if match:
            digits = re.sub(r'\D', '', match.group(0))
            if len(digits) >= 10:
                return '+91' + digits[-10:]
        return None

    @staticmethod
    def extract_email(text: str) -> Optional[str]:
        """Match standard email addresses."""
        pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
        match = re.search(pattern, text)
        return match.group(0).lower() if match else None

    @staticmethod
    def extract_dob(text: str) -> Optional[str]:
        """Match Date of Birth patterns."""
        dob_patterns = [
            r'(?:DOB|Date\s+of\s+Birth|Birth\s*Date)[\s:]+([0-3]?\d[\/\-\.][0-1]?\d[\/\-\.]\d{2,4})',
            r'(?:DOB|Date\s+of\s+Birth|Birth\s*Date)[\s:]+([0-3]?\d\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,]+\d{2,4})'
        ]
        for pattern in dob_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def extract_qualification(text: str) -> Optional[str]:
        """Detect highest academic qualification from standard terms."""
        qualifications = [
            'B.Tech', 'B.E.', 'M.Tech', 'M.E.', 'BCA', 'MCA', 'B.Sc', 'M.Sc',
            'B.Com', 'M.Com', 'BBA', 'MBA', 'Diploma', 'ITI', '12th', '10th',
            'Higher Secondary', 'Senior Secondary', 'Graduation', 'Post Graduation'
        ]
        for q in qualifications:
            # Case insensitive whole-word match
            pattern = r'\b' + re.escape(q) + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                return q
        return None

    @staticmethod
    def extract_location(text: str, fallback_site: Optional[str] = None) -> Optional[str]:
        """Match common Indian cities/states or use the site folder name."""
        common_locations = [
            'Delhi', 'New Delhi', 'Gurgaon', 'Gurugram', 'Noida', 'Ghaziabad',
            'Chandigarh', 'Punjab', 'Haryana', 'Uttar Pradesh', 'Bihar', 'Patna',
            'Jharkhand', 'Ranchi', 'Orissa', 'Odisha', 'Bhubaneswar', 'West Bengal', 'Kolkata',
            'Mumbai', 'Pune', 'Bangalore', 'Bengaluru', 'Hyderabad', 'Chennai', 'Jaipur', 'Rewari'
        ]
        for loc in common_locations:
            if re.search(r'\b' + re.escape(loc) + r'\b', text, re.IGNORECASE):
                return loc
        return fallback_site

    @staticmethod
    def extract_name(text: str, file_name: str) -> tuple[str, Optional[str]]:
        """Extract candidate's first and last name from top lines or file name."""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        candidate_name = None

        # Look at the first 5 non-empty lines
        for line in lines[:5]:
            # Ignore common headers
            if re.search(r'resume|curriculum|vitae|cv|page|profile', line, re.IGNORECASE):
                continue
            # Remove labels like "Name: "
            cleaned = re.sub(r'^(?:Name|Full\s*Name)[\s:]+', '', line, flags=re.IGNORECASE).strip()
            # If line is 2-4 words of letters only, likely a name
            words = cleaned.split()
            if 1 <= len(words) <= 4 and all(w.isalpha() for w in words):
                candidate_name = cleaned
                break

        # Fallback to file name if header didn't give a clear name (e.g. "Rahul_Sharma_Resume.pdf")
        if not candidate_name:
            clean_filename = re.sub(r'(_|\-|\.pdf|\.docx|resume|cv)', ' ', file_name, flags=re.IGNORECASE).strip()
            words = [w for w in clean_filename.split() if w.isalpha()]
            if words:
                candidate_name = " ".join(words[:2])

        if not candidate_name:
            candidate_name = "Candidate"

        parts = candidate_name.split()
        first_name = parts[0]
        last_name = " ".join(parts[1:]) if len(parts) > 1 else None
        return first_name, last_name

    @classmethod
    def parse(cls, file_bytes: bytes, file_name: str, fallback_site: Optional[str] = None) -> ParsedResume:
        """Complete resume parsing pipeline with integrity and scanned image handling."""
        is_valid, detected_mime = cls.validate_file_type(file_bytes, file_name)
        if not is_valid:
            return ParsedResume(
                first_name="Candidate",
                phone="+91-0000000000",
                raw_text="",
                is_corrupt=True,
                confidence="low",
                extracted_attributes={
                    "parsed_from": file_name,
                    "validation_error": detected_mime,
                    "flags": ["corrupt_or_unsupported_file"]
                }
            )

        is_pw_protected = False
        if file_name.lower().endswith(".pdf"):
            raw_text, is_pw_protected = cls.extract_text_from_pdf(file_bytes)
        elif file_name.lower().endswith((".docx", ".doc")):
            raw_text = cls.extract_text_from_docx(file_bytes)
        else:
            raw_text = ""

        if is_pw_protected:
            return ParsedResume(
                first_name="Candidate",
                phone="+91-0000000000",
                raw_text="",
                is_password_protected=True,
                confidence="low",
                extracted_attributes={
                    "parsed_from": file_name,
                    "flags": ["password_protected_pdf", "needs_manual_action"]
                }
            )

        is_scanned = len(raw_text.strip()) < 30
        first_name, last_name = cls.extract_name(raw_text, file_name)
        phone = cls.extract_phone(raw_text) or "+91-0000000000"
        email = cls.extract_email(raw_text)
        dob = cls.extract_dob(raw_text)
        location = cls.extract_location(raw_text, fallback_site)
        qualification = cls.extract_qualification(raw_text)

        flags = []
        if is_scanned:
            flags.append("scanned_resume_needs_ocr")

        return ParsedResume(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            dob=dob,
            location=location,
            last_qualification=qualification,
            raw_text=raw_text,
            confidence="low" if is_scanned else "high",
            extracted_attributes={
                "parsed_from": file_name,
                "mime_type": detected_mime,
                "detected_qualification": qualification,
                "detected_location": location,
                "flags": flags,
                "is_scanned_image": is_scanned
            }
        )
