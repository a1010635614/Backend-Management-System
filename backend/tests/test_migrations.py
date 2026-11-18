import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class MigrationTests(unittest.TestCase):
    def test_fresh_upgrade_and_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            env={**os.environ,"DATABASE_URL":"sqlite:///"+directory+"/migration.db"}
            for _ in range(2):
                result=subprocess.run([sys.executable,"-m","alembic","upgrade","head"],env=env,cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
            import sqlite3
            with sqlite3.connect(directory+"/migration.db") as db:
                self.assertEqual(db.execute('select version_num from alembic_version').fetchone()[0],'0001')
                columns={row[1] for row in db.execute('pragma table_info(email_codes)')}
                self.assertIn('attempts',columns)
            db.close()
