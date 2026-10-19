"""Exercise downloaded ciphertext integrity and the isolated-restore safety gate."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/verify_external_backup.sh'


class ExternalBackupVerificationTests(unittest.TestCase):
    def test_roundtrip_and_corruption_and_remote_database_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'scripts').mkdir()
            plain = root / 'original.dump'
            plain.write_bytes(b'isolated database fixture')
            archive = root / 'original.enc'
            env = dict(os.environ, BACKUP_ENCRYPTION_KEY='test-key',
                       BACKUP_SHA256=hashlib.sha256(plain.read_bytes()).hexdigest(),
                       RESTORE_DATABASE_URL='postgresql://test@localhost/era_restore_check',
                       EXTERNAL_REFERENCE='s3://test-only/backup.enc',
                       TEST_ARCHIVE=str(archive), TEST_MARKER=str(root / 'restored'))
            subprocess.run(['openssl', 'enc', '-aes-256-cbc', '-salt', '-pbkdf2', '-iter', '200000',
                            '-in', str(plain), '-out', str(archive), '-pass', 'env:BACKUP_ENCRYPTION_KEY'],
                           env=env, check=True, capture_output=True)
            env['ARCHIVE_SHA256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
            aws = root / 'aws'
            aws.write_text('#!/usr/bin/env bash\nset -e\ncp "$TEST_ARCHIVE" "$4"\n')
            aws.chmod(0o700)
            env['PATH'] = str(root) + os.pathsep + env['PATH']
            # The real restore tool owns schema verification. Verify that this
            # wrapper passes the downloaded, decrypted original into that tool.
            (root / 'scripts/verify_database_restore.sh').write_text(
                '#!/usr/bin/env bash\nset -e\n'
                'test "$(sha256sum "$BACKUP_FILE" | cut -d " " -f1)" = "$BACKUP_SHA256"\n'
                'touch "$TEST_MARKER"\n')
            result = subprocess.run(['bash', str(SCRIPT)], cwd=root, env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / 'restored').exists())
            (root / 'restored').unlink()
            archive.write_bytes(b'corrupt provider copy')
            result = subprocess.run(['bash', str(SCRIPT)], cwd=root, env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'checksum mismatch', result.stderr)
            self.assertFalse((root / 'restored').exists())
            env['RESTORE_DATABASE_URL'] = 'postgresql://test@production.example/era_restore_check'
            result = subprocess.run(['bash', str(SCRIPT)], cwd=root, env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'isolated CI database', result.stderr)
