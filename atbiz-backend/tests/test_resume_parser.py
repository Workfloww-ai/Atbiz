import unittest
from app.services.resume_parser import ResumeParser

class TestResumeParserEnhancements(unittest.TestCase):
    def test_extract_name_from_filename_brackets_and_metadata(self):
        name = ResumeParser.extract_name_from_filename("Naukri_KaranVeer[2y_5m].pdf")
        self.assertEqual(name, "Karan Veer")

        name2 = ResumeParser.extract_name_from_filename("RESUME   ANKIT PALIWAL.pdf")
        self.assertEqual(name2, "ANKIT PALIWAL")

        name3 = ResumeParser.extract_name_from_filename("Ganesh Resume（3）.docx")
        self.assertEqual(name3, "Ganesh")

        name4 = ResumeParser.extract_name_from_filename("Rahul_Dhiman_Updated_Resume_NoYears.pdf")
        self.assertEqual(name4, "Rahul Dhiman")

    def test_extract_name_with_tabs_and_contact_info(self):
        text = "RESUME\t\nPAILA GANESH\tGmail Id:-ganeshpaila452@gmail.com\nPhone No: - 8688529345"
        first, last = ResumeParser.extract_name(text, "Ganesh Resume（3）.docx")
        self.assertEqual(first, "PAILA")
        self.assertEqual(last, "GANESH")

    def test_extract_name_skips_skills_header(self):
        text = "RESUME\nObjective: Work hard\nTechnical Skills\nJava, Python\nEducation: B.Com"
        first, last = ResumeParser.extract_name(text, "RESUME   ANKIT PALIWAL.pdf")
        self.assertEqual(first, "ANKIT")
        self.assertEqual(last, "PALIWAL")

    def test_extract_email_cleans_prefixes(self):
        self.assertEqual(ResumeParser.extract_email("Gmail Id:-ganeshpaila452@gmail.com"), "ganeshpaila452@gmail.com")
        self.assertEqual(ResumeParser.extract_email("Emailid-Pawankgupta92@gmail.com"), "pawankgupta92@gmail.com")
        self.assertEqual(ResumeParser.extract_email("sourabh.tyagi.07@gmail.com"), "sourabh.tyagi.07@gmail.com")

    def test_extract_phone_avoids_date_ranges(self):
        text = "01/09/2021 - 30/05/2023\n2019-2021\nDIKSHIT GAUTAM\n+918894333123 | dikshit@gmail.com"
        phone = ResumeParser.extract_phone(text)
        self.assertEqual(phone, "+918894333123")

    def test_extract_phone_with_double_dashes_and_labels(self):
        text = "CURRICULUM VITAE\nKARANVEER SINGH\nMOBILE NO. +91 9646--948970\nEmail: karanveer8323@gmail.com"
        phone = ResumeParser.extract_phone(text)
        self.assertEqual(phone, "+919646948970")

if __name__ == '__main__':
    unittest.main()
