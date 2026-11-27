import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from app.services.ingestion_service import IngestionService
from app.services.gdrive_service import GoogleDriveService
from app.routers.candidates import get_clients_and_sites_tree

class TestDriveFolderDeletion(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_crawl_local_directory_metadata(self):
        role_dir = os.path.join(self.test_dir, "ClientA", "Site1", "Role1")
        os.makedirs(role_dir, exist_ok=True)

        test_file = os.path.join(role_dir, "test_resume.pdf")
        with open(test_file, "wb") as f:
            f.write(b"%PDF-1.4 dummy resume content")

        items = list(GoogleDriveService.crawl_local_directory(self.test_dir))
        self.assertEqual(len(items), 1)
        meta = GoogleDriveService.last_crawl_metadata
        self.assertTrue(meta["completed"])
        self.assertIn("/ClientA", meta["active_folder_paths"])
        self.assertIn("/ClientA/Site1", meta["active_folder_paths"])
        self.assertIn("/ClientA/Site1/Role1", meta["active_folder_paths"])
        self.assertIn("ClientA", meta["hierarchy"])
        self.assertIn("Site1", meta["hierarchy"]["ClientA"])
        self.assertIn("Role1", meta["hierarchy"]["ClientA"]["Site1"])
        self.assertIn(items[0]["file_id"], meta["active_file_ids"])

    def test_prune_deleted_drive_items_single_location(self):
        mock_sb = MagicMock()
        service = IngestionService(tenant_id="tenant-123")
        service.supabase = mock_sb

        # Candidate files and candidates in DB
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            # candidate_files select
            MagicMock(data=[
                {"id": "cf-1", "candidate_id": "cand-1", "drive_file_id": "fid-1", "folder_path": "/ClientA/Site1/Role1/c1.pdf", "client_id": "c-1", "site_id": "s-1"},
                {"id": "cf-2", "candidate_id": "cand-2", "drive_file_id": "fid-2", "folder_path": "/ClientA/Site1/Role2/c2.pdf", "client_id": "c-1", "site_id": "s-1"},
            ]),
            # candidates select
            MagicMock(data=[
                {"id": "cand-1", "drive_file_id": "fid-1", "drive_folder_path": "/ClientA/Site1/Role1/c1.pdf", "extracted_attributes": {}},
                {"id": "cand-2", "drive_file_id": "fid-2", "drive_folder_path": "/ClientA/Site1/Role2/c2.pdf", "extracted_attributes": {}},
            ]),
            # tenant settings select
            MagicMock(data=[{"settings": {}}])
        ]

        metadata = {
            "active_file_ids": {"fid-2"},
            "active_folder_paths": {"/ClientA", "/ClientA/Site1", "/ClientA/Site1/Role2"},
            "hierarchy": {"ClientA": {"Site1": ["Role2"]}}
        }

        stats = service.prune_deleted_drive_items(metadata)
        self.assertEqual(stats["deleted_from_drive"], 1)
        self.assertEqual(stats["deleted_candidates"], 1)

    def test_prune_multi_location_candidate(self):
        mock_sb = MagicMock()
        service = IngestionService(tenant_id="tenant-123")
        service.supabase = mock_sb

        # Candidate 1 is present in 2 locations:
        # 1. /ClientA/Site1/Role1/c1.pdf (fid-1)
        # 2. /ClientA/Site2/Role2/c1.pdf (fid-2)
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            # candidate_files select
            MagicMock(data=[
                {"id": "cf-1", "candidate_id": "cand-1", "drive_file_id": "fid-1", "folder_path": "/ClientA/Site1/Role1/c1.pdf", "client_id": "c-1", "site_id": "s-1"},
                {"id": "cf-2", "candidate_id": "cand-1", "drive_file_id": "fid-2", "folder_path": "/ClientA/Site2/Role2/c1.pdf", "client_id": "c-1", "site_id": "s-2"},
            ]),
            # candidates select
            MagicMock(data=[
                {"id": "cand-1", "drive_file_id": "fid-1", "drive_folder_path": "/ClientA/Site1/Role1/c1.pdf", "extracted_attributes": {
                    "locations_present": [
                        {"file_id": "fid-1", "path": "/ClientA/Site1/Role1/c1.pdf", "site_id": "s-1"},
                        {"file_id": "fid-2", "path": "/ClientA/Site2/Role2/c1.pdf", "site_id": "s-2"}
                    ]
                }},
            ]),
            # tenant settings select
            MagicMock(data=[{"settings": {}}])
        ]

        # Site1 folder is deleted in Drive, so ONLY fid-2 is active
        metadata = {
            "active_file_ids": {"fid-2"},
            "active_folder_paths": {"/ClientA", "/ClientA/Site2", "/ClientA/Site2/Role2"},
            "hierarchy": {"ClientA": {"Site2": ["Role2"]}}
        }

        stats = service.prune_deleted_drive_items(metadata)
        self.assertEqual(stats["deleted_from_drive"], 1)
        self.assertEqual(stats["deleted_candidates"], 0) # Candidate not deleted because it still exists in Site2

    def test_meta_tree_omits_deleted_folders(self):
        mock_sb = MagicMock()

        with patch("app.routers.candidates.get_supabase", return_value=mock_sb):
            mock_sb.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
                # clients
                MagicMock(data=[
                    {"id": "cid-1", "code": "ClientA", "name": "Client A Corp"},
                    {"id": "cid-2", "code": "ClientB", "name": "Client B Corp"},
                ]),
                # sites
                MagicMock(data=[
                    {"id": "sid-1", "client_id": "cid-1", "state": "Site1", "site_name": "Site 1", "site_code": "S1"},
                    {"id": "sid-2", "client_id": "cid-2", "state": "Site2", "site_name": "Site 2", "site_code": "S2"},
                ]),
                # applications
                MagicMock(data=[
                    {"client_id": "cid-1", "site_id": "sid-1", "candidate_id": "cand-1"}
                ]),
                # candidates
                MagicMock(data=[
                    {"id": "cand-1", "drive_folder_path": "/ClientA/Site1/Role1/c1.pdf", "extracted_attributes": {}}
                ]),
                # tenant settings with drive_tree (ClientB was deleted from Drive)
                MagicMock(data=[
                    {"settings": {
                        "drive_tree": {
                            "ClientA": {
                                "Site1": ["Role1"]
                            }
                        }
                    }}
                ])
            ]

            res = get_clients_and_sites_tree()
            tree = res["tree"]

            # ClientB was deleted from Drive and has 0 candidates -> MUST be omitted!
            client_ids = [c["id"] for c in tree]
            self.assertIn("cid-1", client_ids)
            self.assertNotIn("cid-2", client_ids)

            # ClientA sites
            client_a = next(c for c in tree if c["id"] == "cid-1")
            self.assertEqual(len(client_a["sites"]), 1)
            self.assertEqual(client_a["sites"][0]["id"], "sid-1")
            self.assertEqual(client_a["sites"][0]["roles"][0]["name"], "Role1")

    def test_run_local_sync_end_to_end_prune(self):
        # 1. Create a folder structure on disk
        role1_dir = os.path.join(self.test_dir, "RIL", "Bihar", "Technician")
        role2_dir = os.path.join(self.test_dir, "RIL", "Bihar", "Supervisor")
        os.makedirs(role1_dir, exist_ok=True)
        os.makedirs(role2_dir, exist_ok=True)

        f1 = os.path.join(role1_dir, "Aman.pdf")
        f2 = os.path.join(role2_dir, "Rahul.pdf")
        with open(f1, "wb") as f:
            f.write(b"%PDF-1.4 Aman Kumar technician phone 9876543210")
        with open(f2, "wb") as f:
            f.write(b"%PDF-1.4 Rahul Sharma supervisor phone 9876543211")

        mock_sb = MagicMock()
        service = IngestionService(tenant_id="a0000000-0000-0000-0000-000000000001")
        service.supabase = mock_sb

        # Mock ingest_single_file to return success
        with patch.object(service, "ingest_single_file", return_value={"status": "success", "candidate_id": "c1"}):
            with patch.object(service, "prune_deleted_drive_items", return_value={"deleted_from_drive": 0, "deleted_candidates": 0}) as mock_prune:
                stats1 = service.run_local_sync(self.test_dir)
                self.assertEqual(stats1["total_scanned"], 2)
                mock_prune.assert_called_once()
                meta = mock_prune.call_args[0][0]
                self.assertIn("local_RIL_Bihar_Aman.pdf", meta["active_file_ids"])
                self.assertIn("local_RIL_Bihar_Rahul.pdf", meta["active_file_ids"])
                self.assertIn("Technician", meta["hierarchy"]["RIL"]["Bihar"])
                self.assertIn("Supervisor", meta["hierarchy"]["RIL"]["Bihar"])

        # 2. Now simulate DELETING the 'Supervisor' folder from disk!
        shutil.rmtree(role2_dir)

        with patch.object(service, "ingest_single_file", return_value={"status": "success", "candidate_id": "c1"}):
            with patch.object(service, "prune_deleted_drive_items", return_value={"deleted_from_drive": 1, "deleted_candidates": 1}) as mock_prune:
                stats2 = service.run_local_sync(self.test_dir)
                self.assertEqual(stats2["total_scanned"], 1) # Only Aman.pdf scanned
                self.assertEqual(stats2["deleted_from_drive"], 1)
                self.assertEqual(stats2["deleted_candidates"], 1)
                meta2 = mock_prune.call_args[0][0]
                # Supervisor was deleted -> must NOT be in active files or hierarchy!
                self.assertNotIn("local_RIL_Bihar_Rahul.pdf", meta2["active_file_ids"])
                self.assertNotIn("Supervisor", meta2["hierarchy"]["RIL"]["Bihar"])
                self.assertIn("Technician", meta2["hierarchy"]["RIL"]["Bihar"])

if __name__ == "__main__":
    unittest.main()
