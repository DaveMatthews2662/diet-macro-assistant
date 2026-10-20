import base64
import os
import requests

REPO = "DaveMatthews2662/diet-macro-assistant"
BRANCH = "main"


def get_github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    try:
        import streamlit as st
        if "GITHUB_TOKEN" in st.secrets:
            return str(st.secrets["GITHUB_TOKEN"]).strip()
    except Exception:
        pass
    return ""


def sync_file_to_github(filepath: str, commit_message: str = "Update from phone dashboard") -> bool:
    """
    If running on Streamlit Cloud with GITHUB_TOKEN configured in Secrets,
    automatically commit the updated file back to the GitHub repository so nothing is ever lost.
    """
    token = get_github_token()
    if not token or not os.path.exists(filepath):
        return False

    try:
        with open(filepath, "rb") as f:
            content_b64 = base64.b64encode(f.read()).decode("utf-8")

        url = f"https://api.github.com/repos/{REPO}/contents/{filepath}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
        get_resp = requests.get(url, headers=headers, params={"ref": BRANCH}, timeout=8)
        sha = get_resp.json().get("sha") if get_resp.status_code == 200 else None

        payload = {
            "message": commit_message,
            "content": content_b64,
            "branch": BRANCH,
        }
        if sha:
            payload["sha"] = sha

        put_resp = requests.put(url, headers=headers, json=payload, timeout=10)
        return put_resp.status_code in (200, 201)
    except Exception:
        return False
