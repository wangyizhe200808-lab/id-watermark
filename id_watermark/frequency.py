"""DWT-DCT-SVD adapter using the MIT-licensed blind-watermark 0.4.4 core.

LumaCore.embed / extract_raw adapt upstream bwm_core.py to use ONLY luminance.
Copyright (c) 2019 郭飞. See licenses/blind-watermark-MIT.txt.
The packet format, keyed verification and error correction are additions here.
"""

import hashlib
import hmac
import secrets
import struct

import cv2
import numpy as np
from blind_watermark.bwm_core import WaterMarkCore, random_strategy1
from pywt import idwt2
from reedsolo import ReedSolomonError, RSCodec

PROFILES = {"balanced": (36, 20), "strong": (64, 32), "print": (96, 48)}
PARITY = 48
MAGIC = b"IDW1"


class WatermarkError(ValueError):
    pass


class LumaCore(WaterMarkCore):
    """Reuse upstream transforms, quantization, shuffling and repetition.

    Chroma is not marked: a grayscale copy discards it, and white ID backgrounds
    would otherwise acquire unnecessary colored artifacts. No new crypto claim
    is made for upstream's 32-bit NumPy shuffling keys.
    """

    def embed(self):
        self.init_block_index()
        self.idx_shuffle = random_strategy1(self.password_img, self.block_num, 16)
        blocks = self.pool.map(
            self.block_add_wm,
            [
                (self.ca_block[0][self.block_index[i]], self.idx_shuffle[i], i)
                for i in range(self.block_num)
            ],
        )
        for i, block in enumerate(blocks):
            self.ca_block[0][self.block_index[i]] = block
        ca = self.ca[0].copy()
        part = np.concatenate(np.concatenate(self.ca_block[0], 1), 1)
        ca[: self.part_shape[0], : self.part_shape[1]] = part
        yuv = self.img_YUV.copy()
        yuv[:, :, 0] = idwt2((ca, self.hvd[0]), "haar")
        yuv = yuv[: self.img_shape[0], : self.img_shape[1]]
        return np.clip(cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR), 0, 255)

    def extract_raw(self, img):
        self.read_img_arr(img=img)
        self.init_block_index()
        shufflers = random_strategy1(self.password_img, self.block_num, 16)
        values = self.pool.map(
            self.block_get_wm,
            [(self.ca_block[0][self.block_index[i]], shufflers[i]) for i in range(self.block_num)],
        )
        return np.asarray(values, dtype=np.float64)[None, :]


def derive_keys(password: str, salt_hex: str):
    if len(password) < 8:
        raise WatermarkError("频域水印密码至少 8 位；请保存在安全位置。")
    try:
        salt = bytes.fromhex(salt_hex)
    except (TypeError, ValueError) as exc:
        raise WatermarkError("提取凭据的 salt 无效。") from exc
    if len(salt) != 16:
        raise WatermarkError("提取凭据的 salt 长度无效。")
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000, 32)
    seeds = hmac.digest(key, b"id-watermark/seeds/v1", "sha256")
    return key, int.from_bytes(seeds[:4], "big"), int.from_bytes(seeds[4:8], "big")


def pack_message(text: str, trace_id: str, key: bytes) -> bytes:
    raw = text.encode("utf-8")
    if not raw or len(raw) > 1000:
        raise WatermarkError("频域水印文字不能为空，UTF-8 编码后须不超过 1000 字节。")
    body = MAGIC + struct.pack(">H", len(raw)) + bytes.fromhex(trace_id) + raw
    return bytes(RSCodec(PARITY).encode(body + hmac.digest(key, body, "sha256")[:16]))


def unpack_message(encoded: bytes, key: bytes) -> dict:
    try:
        raw, _, positions = RSCodec(PARITY).decode(encoded)
    except (ReedSolomonError, IndexError, ZeroDivisionError) as exc:
        raise WatermarkError("纠错失败：未能恢复可信水印。请核对密码、凭据和图像校正。") from exc
    raw = bytes(raw)
    if len(raw) < 31 or raw[:4] != MAGIC:
        raise WatermarkError("水印格式校验失败，不能据此认定存在水印。")
    body, tag = raw[:-16], raw[-16:]
    if not hmac.compare_digest(tag, hmac.digest(key, body, "sha256")[:16]):
        raise WatermarkError("水印完整性校验失败，不能显示为有效提取结果。")
    n = struct.unpack(">H", body[4:6])[0]
    if len(body) != 14 + n:
        raise WatermarkError("水印长度校验失败。")
    try:
        text = body[14:].decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise WatermarkError("水印文字编码校验失败。") from exc
    return {
        "text": text,
        "trace_id": body[6:14].hex(),
        "corrected_bytes": len(positions),
        "integrity_verified": True,
    }


def new_parameters(password: str, text: str, profile: str = "strong"):
    if profile not in PROFILES:
        raise WatermarkError("未知频域强度。")
    params = {
        "algorithm": "luma-dwt-dct-svd-v1",
        "salt": secrets.token_hex(16),
        "trace_id": secrets.token_hex(8),
        "profile": profile,
        "d1": PROFILES[profile][0],
        "d2": PROFILES[profile][1],
        "parity_bytes": PARITY,
    }
    key, _, _ = derive_keys(password, params["salt"])
    packet = pack_message(text, params["trace_id"], key)
    params["packet_bits"] = len(packet) * 8
    return params, packet


def make_core(password: str, params: dict):
    _, image_seed, wm_seed = derive_keys(password, params["salt"])
    core = LumaCore(password_img=image_seed, mode="common", processes=1)
    core.d1, core.d2 = params["d1"], params["d2"]
    return core, wm_seed


def capacity(size: tuple[int, int]) -> int:
    w, h = size
    return ((w + 1) // 2 // 4) * ((h + 1) // 2 // 4)


def embed_bgr(bgr: np.ndarray, password: str, params: dict, packet: bytes) -> np.ndarray:
    n = params["packet_bits"]
    available = capacity((bgr.shape[1], bgr.shape[0]))
    if available < n * 4:
        raise WatermarkError(
            f"照片容量不足：当前 {available} 个块，水印 {n} 位，至少需要 4 次重复。"
            "请使用更高分辨率原图或缩短频域文字；放大低清图不能恢复细节。"
        )
    core, seed = make_core(password, params)
    bits = np.unpackbits(np.frombuffer(packet, dtype=np.uint8)).copy()
    np.random.RandomState(seed).shuffle(bits)
    core.read_img_arr(bgr)
    core.read_wm(bits)
    # Match the float -> byte quantization that is actually saved to PNG.
    return np.rint(core.embed()).astype(np.uint8)


def extract_bgr(bgr: np.ndarray, password: str, params: dict) -> dict:
    n = params["packet_bits"]
    if capacity((bgr.shape[1], bgr.shape[0])) <= n:
        raise WatermarkError("待提取图像太小，无法容纳凭据记录的水印。")
    core, seed = make_core(password, params)
    # Soft repeated votes; upstream's k-means threshold discards that information.
    votes = core.extract(img=bgr, wm_shape=n)
    index = np.arange(n)
    np.random.RandomState(seed).shuffle(index)
    votes[index] = votes.copy()
    key, _, _ = derive_keys(password, params["salt"])
    last_error = None
    # A small threshold sweep compensates for clipping or grayscale bias.
    for threshold in (0.5, 0.45, 0.55, 0.4, 0.6):
        try:
            packet = np.packbits(votes >= threshold).tobytes()
            result = unpack_message(packet, key)
            if result["trace_id"] != params["trace_id"]:
                raise WatermarkError("提取到的副本编号与凭据不一致。")
            result["threshold"] = threshold
            return result
        except WatermarkError as exc:
            last_error = exc
    raise WatermarkError(str(last_error))
