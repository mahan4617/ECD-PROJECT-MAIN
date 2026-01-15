from django.conf import settings
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from PIL import Image
import io
import os

def derive_key(user_id: int) -> bytes:
    salt = str(user_id).encode()
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=b'securecloud')
    return hkdf.derive(settings.SECRET_KEY.encode())

def aes_encrypt(user_id: int, data: bytes) -> tuple[bytes, bytes]:
    key = derive_key(user_id)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, data, None)
    return ct, nonce

def aes_decrypt(user_id: int, nonce: bytes, ciphertext: bytes) -> bytes:
    key = derive_key(user_id)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)

def hide_data_in_image(cover_image_path: str, data: bytes) -> Image.Image:
    img = Image.open(cover_image_path).convert('RGB')
    pixels = img.load()
    bitstream = []
    length = len(data)
    header = length.to_bytes(4, 'big')
    payload = header + data
    for byte in payload:
        for i in range(8):
            bitstream.append((byte >> (7 - i)) & 1)
    width, height = img.size
    capacity = width * height * 3
    if len(bitstream) > capacity:
        raise ValueError('Data too large for cover image')
    idx = 0
    for y in range(height):
        for x in range(width):
            if idx >= len(bitstream):
                return img
            r, g, b = pixels[x, y]
            if idx < len(bitstream):
                r = (r & ~1) | bitstream[idx]; idx += 1
            if idx < len(bitstream):
                g = (g & ~1) | bitstream[idx]; idx += 1
            if idx < len(bitstream):
                b = (b & ~1) | bitstream[idx]; idx += 1
            pixels[x, y] = (r, g, b)
    return img

def extract_data_from_image(stego_image_path: str) -> bytes:
    img = Image.open(stego_image_path).convert('RGB')
    pixels = img.load()
    width, height = img.size
    bits = []
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            bits.append(r & 1)
            bits.append(g & 1)
            bits.append(b & 1)
    def bits_to_bytes(bits_list):
        out = bytearray()
        for i in range(0, len(bits_list), 8):
            byte_bits = bits_list[i:i+8]
            if len(byte_bits) < 8:
                break
            val = 0
            for j, bit in enumerate(byte_bits):
                val |= (bit << (7 - j))
            out.append(val)
        return bytes(out)
    raw = bits_to_bytes(bits)
    if len(raw) < 4:
        return b''
    length = int.from_bytes(raw[:4], 'big')
    return raw[4:4+length]
