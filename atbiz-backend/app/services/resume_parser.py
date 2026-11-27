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
        """Extract plain text from DOCX bytes including paragraphs and tables."""
        try:
            doc = Document(io.BytesIO(file_bytes))
            parts = []
            for p in doc.paragraphs:
                if p.text and p.text.strip():
                    parts.append(p.text.strip())
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        txt = cell.text.strip()
                        if txt and txt not in parts:
                            parts.append(txt)
            return "\n".join(parts).strip()
        except Exception:
            try:
                return file_bytes.decode('utf-8', errors='ignore').strip()
            except Exception:
                return ""

    @staticmethod
    def extract_phone(text: str) -> Optional[str]:
        """
        Match valid 10-digit Indian phone numbers with optional +91/0 prefix.
        Avoid matching across date ranges like 2019-2021 or 01/09/2021.
        Handles labels with spacing/dashes/periods like 'MOBILE NO. +91 9646--948970'.
        """
        # First priority: labelled phone numbers
        labelled = r'(?:phone|mob(?:ile)?|cell|contact|call)[^\d\n]*?(?:(?:\+?91|0)[^\d\n]*)?([6-9](?:[^\d\n]*\d){9})\b'
        m = re.search(labelled, text, re.IGNORECASE)
        if m:
            digits = re.sub(r'\D', '', m.group(1))
            if len(digits) == 10:
                return '+91' + digits

        # Second priority: explicit +91 prefixed phone numbers
        explicit = r'(?:\+91)[^\d\n]*([6-9](?:[^\d\n]*\d){9})\b'
        m = re.search(explicit, text)
        if m:
            digits = re.sub(r'\D', '', m.group(1))
            if len(digits) == 10:
                return '+91' + digits

        # Third priority: standalone 10-digit mobile number not surrounded by slashes/dashes
        standalone = r'(?<![\d\/\.\-])([6-9]\d{4}[\s\-]*\d{5}|[6-9]\d{9})(?![\d\/\.\-])'
        for match in re.finditer(standalone, text):
            digits = re.sub(r'\D', '', match.group(1))
            if len(digits) == 10:
                return '+91' + digits

        return None

    @staticmethod
    def extract_email(text: str) -> Optional[str]:
        """Match standard email addresses, stripping leading/trailing punctuation and labels."""
        pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
        match = re.search(pattern, text)
        if match:
            email = match.group(0).lower()
            # Strip leading/trailing hyphens, dots, colons
            email = re.sub(r'^[_\-+.:]+|[_\-+.:]+$', '', email)
            # Strip prefixes like 'emailid-', 'id-', 'gmail:'
            email = re.sub(r'^(?:email|emailid|id|gmail)[_\-+.:]+', '', email)
            if '@' in email and len(email.split('@')[0]) > 0:
                return email
        return None

    @staticmethod
    def extract_dob(text: str) -> Optional[str]:
        """Match Date of Birth patterns and normalize to ISO YYYY-MM-DD."""
        dob_patterns = [
            r'(?:DOB|Date\s+of\s+Birth|Birth\s*Date)[\s:]+([0-3]?\d)[\/\-\.]([0-1]?\d)[\/\-\.](\d{2,4})',
        ]
        for pattern in dob_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                d, m, y = match.group(1), match.group(2), match.group(3)
                if len(y) == 2:
                    y = ('19' if int(y) > 30 else '20') + y
                try:
                    day, month, year = int(d), int(m), int(y)
                    if 1 <= month <= 12 and 1 <= day <= 31 and 1950 <= year <= 2015:
                        return f"{year:04d}-{month:02d}-{day:02d}"
                except Exception:
                    pass

        text_month_pat = r'(?:DOB|Date\s+of\s+Birth|Birth\s*Date)[\s:]+([0-3]?\d)\s+([A-Za-z]{3,9})[\s,]+(\d{4})'
        match = re.search(text_month_pat, text, re.IGNORECASE)
        if match:
            d, m_str, y = match.group(1), match.group(2)[:3].capitalize(), match.group(3)
            months = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                      'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
            if m_str in months:
                try:
                    day, month, year = int(d), months[m_str], int(y)
                    if 1 <= month <= 12 and 1 <= day <= 31 and 1950 <= year <= 2015:
                        return f"{year:04d}-{month:02d}-{day:02d}"
                except Exception:
                    pass
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
    def extract_name_from_filename(file_name: str) -> Optional[str]:
        """Extract clean person name from file name (e.g. Naukri_KaranVeer[2y_5m].pdf -> Karan Veer)."""
        fname = re.sub(r'\.(pdf|docx?|doc)$', '', file_name, flags=re.IGNORECASE)
        fname = re.sub(r'\[.*?\]|\(.*?\)|（.*?）', ' ', fname)
        fname = re.sub(r'[_\-]+', ' ', fname).strip()
        fname = re.sub(r'\b(naukri|resume|cv|updated|full|photo|no\s*years?)\b', ' ', fname, flags=re.IGNORECASE)
        fname = re.sub(r'([a-z])([A-Z])', r'\1 \2', fname)
        words = [w for w in fname.split() if w.isalpha() and w.lower() not in ('resume', 'cv', 'naukri', 'pdf', 'docx', 'updated')]
        if words:
            return " ".join(words[:3])
        return None

    @staticmethod
    def extract_name(text: str, file_name: str) -> tuple[str, Optional[str]]:
        """
        Extract candidate's first and last name from top lines or file name.
        Handles tabs, headers, labels, and file naming patterns.
        """
        SKIP_HEADERS = {
            'resume', 'curriculum', 'vitae', 'cv', 'profile', 'objective', 'career objective',
            'summary', 'professional summary', 'personal profile', 'personal details',
            'skills', 'technical skills', 'key skills', 'education', 'educational qualification',
            'qualification', 'experience', 'work experience', 'employment history',
            'projects', 'declaration', 'hobbies', 'strengths', 'accomplishments',
            'academic qualification', 'contact', 'contact info', 'details'
        }

        candidate_name = None
        raw_lines = [l.strip() for l in re.split(r'[\r\n]+', text) if l.strip()]

        for raw_line in raw_lines[:10]:
            # Inspect segments separated by tabs, pipes, or bullets
            segments = [s.strip() for s in re.split(r'[\t\|•]+', raw_line) if s.strip()]
            for seg in segments:
                cleaned = re.sub(r'^(?:Name|Full\s*Name|Candidate\s*Name|Applicant\s*Name)[\s:]+', '', seg, flags=re.IGNORECASE).strip()
                clean_lower = cleaned.lower()
                if clean_lower in SKIP_HEADERS:
                    continue
                if any(clean_lower.startswith(h) for h in ('resume', 'curriculum', 'career objective', 'objective', 'technical skills')):
                    continue
                cleaned = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '', cleaned)
                cleaned = re.sub(r'(?:(?:\+?91|0)[\s\-]?)?[6-9]\d{9}', '', cleaned)
                cleaned = re.sub(r'https?://\S+', '', cleaned).strip()
                words = cleaned.split()
                if 1 <= len(words) <= 4 and all(w.replace('.', '').isalpha() for w in words):
                    if not any(w.lower() in SKIP_HEADERS for w in words):
                        if not any(w.lower() in ('phone', 'mobile', 'email', 'address', 'male', 'female', 'married', 'single') for w in words):
                            candidate_name = " ".join(words)
                            break
            if candidate_name:
                break

        if not candidate_name:
            candidate_name = ResumeParser.extract_name_from_filename(file_name)

        if not candidate_name:
            candidate_name = "Candidate"

        parts = candidate_name.split()
        first_name = parts[0].capitalize() if parts[0].islower() else parts[0]
        last_name = " ".join(p.capitalize() if p.islower() else p for p in parts[1:]) if len(parts) > 1 else None
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
