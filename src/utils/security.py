import os
import sys
import json
from cryptography.fernet import Fernet
import logging

class EncryptionManager:
    """데이터 암호화 및 복호화를 담당하는 클래스"""
    
    def __init__(self, key_path: str = '.secrets/master.key'):
        self.logger = logging.getLogger(__name__)
        # Ensure directory exists
        if os.path.dirname(key_path):
             os.makedirs(os.path.dirname(key_path), exist_ok=True)
             
        self.key_path = key_path
        self.key = self._load_or_create_key()
        self.cipher_suite = Fernet(self.key)

    def _load_or_create_key(self) -> bytes:
        """암호화 키를 로드하거나 새로 생성합니다."""
        if os.path.exists(self.key_path):
            with open(self.key_path, 'rb') as f:
                return f.read()
        else:
            self.logger.info(f"Generating new encryption key at {self.key_path}")
            key = Fernet.generate_key()
            with open(self.key_path, 'wb') as f:
                f.write(key)
            # Windows는 ACL 방식으로 관리되므로 Unix 계열에서만 권한 설정
            if sys.platform != 'win32':
                os.chmod(self.key_path, 0o600)
            return key

    def encrypt_data(self, data: str) -> str:
        """문자열 데이터를 암호화합니다."""
        if not data: return ""
        try:
            encrypted_bytes = self.cipher_suite.encrypt(data.encode('utf-8'))
            return encrypted_bytes.decode('utf-8')
        except Exception as e:
            self.logger.error(f"Encryption failed: {e}")
            return ""

    def decrypt_data(self, encrypted_data: str) -> str:
        """암호화된 문자열을 복호화합니다."""
        if not encrypted_data: return ""
        try:
            encrypted_bytes = encrypted_data.encode('utf-8')
            decrypted_bytes = self.cipher_suite.decrypt(encrypted_bytes)
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            self.logger.error(f"Decryption failed: {e}")
            return ""

    def save_encrypted_json(self, data: dict, filepath: str):
        """딕셔너리를 JSON 문자열로 변환 후 암호화하여 저장합니다."""
        try:
            json_str = json.dumps(data)
            encrypted_str = self.encrypt_data(json_str)
            
            if os.path.dirname(filepath):
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(encrypted_str)
            self.logger.info(f"Encrypted data saved to {filepath}")
        except Exception as e:
            self.logger.error(f"Failed to save encrypted JSON: {e}")

    def load_encrypted_json(self, filepath: str) -> dict:
        """암호화된 파일에서 JSON 데이터를 읽어옵니다."""
        if not os.path.exists(filepath):
            return {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                encrypted_str = f.read()
            json_str = self.decrypt_data(encrypted_str)
            return json.loads(json_str)
        except Exception as e:
            self.logger.error(f"Failed to load encrypted JSON from {filepath}: {e}")
            return {}
