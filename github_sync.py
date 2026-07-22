"""將 Streamlit 產生的 snapshot_ai.json 同步回 GitHub 儲存庫。"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any
from urllib.parse import quote

import requests
import streamlit as st

DEFAULT_REPOSITORY = "adam1984smasher-design/crypto-monitor"
DEFAULT_BRANCH = "main"
DEFAULT_PATH = "snapshot_ai.json"
GITHUB_API_VERSION = "2022-11-28"
SNAPSHOT_JSON_FORMAT = "pretty-indent-2-v2"


def _read_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets[name]
    except Exception:
        return default
    return str(value).strip()


def serialize_snapshot_json(snapshot: dict[str, Any]) -> str:
    """輸出適合 GitHub 與 ChatGPT 按行讀取的多行 JSON。"""
    batch = snapshot.setdefault("batch", {})
    batch["json_format"] = SNAPSHOT_JSON_FORMAT

    text = json.dumps(
        snapshot,
        ensure_ascii=False,
        indent=2,
    )

    # 在四個頂層區塊之間再加一個空白行，GitHub 頁面更容易辨識。
    for key in ("breadth", "groups", "records"):
        text = text.replace(
            f'\n  "{key}":',
            f'\n\n  "{key}":',
            1,
        )

    return text + "\n"


def _stable_snapshot_digest(snapshot: dict[str, Any]) -> str:
    """忽略產生時間與畫面排序，只比較實際掃描資料與格式版本。"""
    batch = snapshot.get("batch") or {}
    stable_payload = {
        "schema_version": batch.get("schema_version"),
        "json_format": batch.get("json_format"),
        "selection": batch.get("selection"),
        "count": batch.get("count"),
        "breadth": snapshot.get("breadth"),
        "groups": snapshot.get("groups"),
        "records": snapshot.get("records"),
    }
    raw = json.dumps(
        stable_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _decode_existing_snapshot(
    response_json: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    try:
        encoded = str(response_json.get("content", "")).replace("\n", "")
        decoded = base64.b64decode(encoded).decode("utf-8")
        parsed = json.loads(decoded)
        if isinstance(parsed, dict):
            return parsed, decoded
    except Exception:
        pass
    return None, ""


def _is_readable_multiline_snapshot(text: str) -> bool:
    """確認舊檔不是整份擠在單一行，且頂層區塊順序正確。"""
    if text.count("\n") < 20:
        return False
    if not text.lstrip().startswith("{\n"):
        return False

    required_markers = (
        '\n  "batch":',
        '\n  "breadth":',
        '\n  "groups":',
        '\n  "records":',
    )
    if not all(marker in text for marker in required_markers):
        return False

    positions = [text.find(marker) for marker in required_markers]
    return positions == sorted(positions)


def sync_snapshot_to_github(snapshot: dict[str, Any]) -> tuple[str, str]:
    """
    建立或覆蓋 snapshot_ai.json。

    回傳：
    - ("updated", message)：已建立或更新
    - ("unchanged", message)：資料與多行格式均相同，未產生新 commit
    - ("disabled", message)：尚未設定 Token
    - ("error", message)：同步失敗
    """
    token = _read_secret("GITHUB_TOKEN")
    if not token:
        message = "GitHub 自動同步尚未啟用：請在 Streamlit Secrets 設定 GITHUB_TOKEN。"
        st.warning(message)
        return "disabled", message

    repository = _read_secret("GITHUB_REPOSITORY", DEFAULT_REPOSITORY)
    branch = _read_secret("GITHUB_BRANCH", DEFAULT_BRANCH)
    path = _read_secret("GITHUB_AI_SNAPSHOT_PATH", DEFAULT_PATH).lstrip("/")

    if "/" not in repository:
        message = "GITHUB_REPOSITORY 格式錯誤，必須是 owner/repository。"
        st.warning(message)
        return "error", message

    url = f"https://api.github.com/repos/{repository}/contents/{quote(path, safe='/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "crypto-monitor-streamlit",
    }

    snapshot_text = serialize_snapshot_json(snapshot)
    local_digest = _stable_snapshot_digest(snapshot)
    generated_at = (snapshot.get("batch") or {}).get(
        "generated_at_taiwan",
        "Streamlit",
    )

    try:
        for attempt in range(2):
            current_sha: str | None = None
            current = requests.get(
                url,
                headers=headers,
                params={"ref": branch},
                timeout=(5, 20),
            )

            if current.status_code == 200:
                current_json = current.json()
                current_sha = current_json.get("sha")
                existing_snapshot, existing_text = _decode_existing_snapshot(
                    current_json
                )

                same_data = (
                    existing_snapshot is not None
                    and _stable_snapshot_digest(existing_snapshot) == local_digest
                )
                readable_format = _is_readable_multiline_snapshot(existing_text)

                # 只有資料相同且已經是新版多行格式時才略過。
                # 舊的一行式 JSON 即使資料相同，也會被強制重寫一次。
                if same_data and readable_format:
                    return (
                        "unchanged",
                        "snapshot_ai.json 資料與多行格式均未變更，未建立新 commit。",
                    )
            elif current.status_code != 404:
                current.raise_for_status()

            payload: dict[str, Any] = {
                "message": f"Update readable snapshot_ai.json ({generated_at})",
                "content": base64.b64encode(
                    snapshot_text.encode("utf-8")
                ).decode("ascii"),
                "branch": branch,
            }
            if current_sha:
                payload["sha"] = current_sha

            updated = requests.put(
                url,
                headers=headers,
                json=payload,
                timeout=(5, 30),
            )

            if updated.status_code in (200, 201):
                action = "建立" if updated.status_code == 201 else "更新"
                message = f"snapshot_ai.json 已{action}為多行易讀格式並同步至 GitHub。"
                st.toast(message, icon="✅")
                return "updated", message

            if updated.status_code == 409 and attempt == 0:
                continue

            updated.raise_for_status()

    except requests.RequestException as exc:
        message = f"GitHub 同步失敗：{type(exc).__name__} - {exc}"
        st.warning(message)
        return "error", message
    except Exception as exc:
        message = f"GitHub 同步失敗：{type(exc).__name__} - {exc}"
        st.warning(message)
        return "error", message

    message = "GitHub 同步失敗：未知錯誤。"
    st.warning(message)
    return "error", message
