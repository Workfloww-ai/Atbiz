# Resume Desk: System Safeguards & Guidelines

**Audience:** Operations, Recruitment Leads, HR Managers, and Non-Technical Stakeholders  
**System:** Resume Desk Automated Google Drive Ingestion  
**Last Updated:** November 2026  

---

## Executive Summary

The **Resume Desk** automatically crawls company Google Drive folders every 6 hours (and on-demand when clicking "Sync Now"), reads candidate resumes (PDFs, Word documents), extracts contact details, and presents them in an organized dashboard for recruiters.

To ensure the platform is reliable, fast, and protected against data corruption, multiple **automatic safeguards (guardrails)** have been built into the system. This document outlines:
1. **What protections exist automatically** (what you don't need to worry about).
2. **Where the system can still stop or need human help** (the edge cases).
3. **Simple Do's and Don'ts for recruiters** uploading files to Google Drive.

---

## 1. Automatic Safeguards (How the System Protects Itself)

| Protection Area | What Could Go Wrong | How the System Protects You (Safeguard) |
| :--- | :--- | :--- |
| **Accidental "Double-Clicks"** | Two recruiters click "Sync Now" at the exact same second, or a manual sync runs during the scheduled 6-hour sync. | **Smart Lock:** The system only allows **one sync at a time**. If someone clicks "Sync Now" while a sync is already running, the system safely responds: *"A sync is already in progress. Please wait."* No duplicate candidate profiles are created. |
| **Exact Duplicate Resumes** | A recruiter accidentally uploads the exact same PDF twice, or puts it in two different folders. | **Digital Fingerprinting:** The system checks the file's unique digital fingerprint (content hash). It will not create two candidates; instead, it marks the candidate as *"Duplicate in Drive"* and links both locations so you know where it was found. |
| **Same Person, Multiple Roles** | Candidate "Rahul Sharma" applies for *Supervisor in Bihar* and later applies for *Team Leader in AP*. | **Unified Candidate Profile:** The system recognizes the same phone number/email, keeps a single master profile for Rahul, and creates job applications for **both** locations. You see badges like *"Also in AP, Bihar"*. |
| **File Renames in Google Drive** | A recruiter renames `Resume_Final.pdf` to `Aman_Kumar_Technician.pdf` directly inside Google Drive. | **Rename Tracking:** The system recognizes the Google Drive file ID, updates the candidate's record with the new name, and flags it as *"Renamed in Drive"* without creating a second candidate. |
| **Massive / Heavy Files** | Someone accidentally drops a 50MB–100MB graphic design portfolio or video into the folder. | **Size Limit Cap (15 MB):** The system streams files in small pieces and automatically skips anything over 15MB. This prevents the server from freezing or slowing down for other recruiters. |
| **Folder Typos (e.g., "Odisa" vs "Odisha")** | An HR member creates a new folder with a spelling mistake (e.g. `RIL/Odisa/Supervisor`). | **Unmapped Review Queue:** Instead of creating a junk company or site in your official database, the system safely stores the candidate and creates an alert: *"Review Unmapped Folder: Odisa"*. Once corrected, the system links the candidate automatically on the next sync. |
| **Corrupted / Invalid Files** | Someone uploads an invalid `.docx` (e.g. an Excel file renamed as `.docx`) or a broken PDF. | **File Verification:** The system inspects the actual structure of the file before reading it. Corrupted files are skipped and logged with an explanation, allowing the rest of the 50+ resumes to sync smoothly. |
| **Password-Protected Resumes** | A candidate sends a password-locked PDF (e.g., salary slip or locked CV). | **Safe Flagging:** The system detects the password lock, tags the profile as *"⚠️ Password-Protected (Needs Manual Review)"*, and continues syncing the remaining resumes without crashing. |

---

## 2. Where the System Can Still Fail (And Why)

While the software handles almost all data errors, there are **external factors and human practices** that can interrupt ingestion:

### A. Google Drive Permissions & Account Access
* **The Issue:** The automated system connects to Google Drive using a secure service account.
* **Failure Mode:** If an administrator accidentally deletes the service account or removes its access (`Viewer` / `Editor`) from the main Google Drive folder, the system cannot see any files.
* **Resolution:** Re-share the root Google Drive folder with the authorized system service email.

### B. Deviating from the 3-Folder Structure
* **The Issue:** The robot is programmed to look strictly 3 folders deep:
  $$\text{Root Folder} \longrightarrow \textbf{1. Company} \longrightarrow \textbf{2. Branch / Site} \longrightarrow \textbf{3. Job Role} \longrightarrow \text{Resumes}$$
* **Failure Mode:**
  - If someone drops resumes directly in the **Company** folder, they will be ignored.
  - If someone creates a **4th subfolder** (e.g. `Company / Site / Role / Shortlisted / candidate.pdf`), the robot will stop at Level 3 and miss files inside "Shortlisted".
* **Resolution:** Ensure all resume files are placed directly inside the **Role** folder.

### C. Scanned Photocopies & Phone Photos (No Searchable Text)
* **The Issue:** Some candidates submit photos of paper resumes taken on a phone, or scanned PDFs that contain only an image without embedded text.
* **Failure Mode:** The computer cannot highlight or search text inside an image. The system will create the candidate row using the filename, but contact details (phone, email, education) will be blank.
* **Resolution:** The profile is automatically flagged as *"⚠️ Scanned Resume (Manual Check Required)"*. Recruiters can click **Open** to view the original PDF in Google Drive and enter details manually.

### D. Google Cloud Daily Quotas
* **The Issue:** Google limits how many thousands of requests can be made per day.
* **Failure Mode:** If multiple teams or scripts share the same Google project and exceed Google's daily quota, Google temporarily pauses downloads.
* **Resolution:** The system automatically retries 5 times with pauses. If Google's daily quota is exhausted, the sync will pause and resume during the next 6-hour cycle.

---

## 3. Best Practices for HR & Recruitment Teams

To ensure 100% of resumes sync instantly and accurately, follow these simple guidelines:

### ✅ DO:
1. **Keep the standard 3-tier folder structure**:
   `[Company Name] / [Site or Circle] / [Job Designation] / [Candidate Resumes]`
   *Example:* `RIL / Bihar Circle / Supervisor / Sire Saini.pdf`
2. **Use readable formats**: Standard `.pdf` or `.docx` files exported from Word, Canva, or LinkedIn.
3. **Check the Dashboard Header**: The top bar tells you exactly how many files were scanned, how many unique candidates exist, and how many duplicate copies were blocked.

### ❌ DO NOT:
1. **Do not create extra subfolders** inside the Job Role folder (e.g., do not make subfolders like *"Selected"*, *"Rejected"*, or *"Pending"* inside the Role folder).
2. **Do not upload password-protected PDFs** without removing the password first.
3. **Do not upload massive portfolio ZIP files or video resumes** into the resume folders (keep individual files under 15MB).

---

## 4. Quick Reference: Dashboard Status Indicators

When viewing candidates on the **Resume Desk Dashboard**:

| Badge / Label | What It Means | Recommended Action |
| :--- | :--- | :--- |
| **`Duplicate in Drive`** | The candidate's resume was found in multiple folders or uploaded multiple times. | Safe to review. The system has already merged them into one candidate. |
| **`Also in AP, KK`** | The candidate applied for jobs in more than one city/branch. | Check both circle requirements before assigning. |
| **`⚠️ Password Protected`** | The candidate's PDF is locked with a password. | Open the resume link in Google Drive to request password or view manually. |
| **`⚠️ Scanned Resume`** | The resume is an image/photo with no selectable text. | Open Google Drive preview and verify candidate phone/email. |
| **`⚠️ Unmapped Folder`** | The folder name did not match any official branch name in the system. | Verify spelling in Google Drive or ask the administrator to register the new branch. |

---

*For technical inquiries or system configuration changes, contact the Engineering & ATS Operations Team.*
