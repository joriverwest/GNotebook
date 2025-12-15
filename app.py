import streamlit as st
from google.oauth2 import service_account
from google.auth.transport.requests import Request
import requests
import json

# ---------------------------------------------------------
# 1. 認証とトークン取得の設定
# ---------------------------------------------------------
SCOPES = ['https://www.googleapis.com/auth/drive']

@st.cache_resource
def get_creds():
    """Secretsから認証情報を読み込む（ServiceオブジェクトではなくCreds自体を返す）"""
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=SCOPES
        )
        return creds
    except Exception as e:
        st.error(f"認証設定エラー: {e}")
        return None

def get_access_token(creds):
    """有効なアクセストークンを取得する"""
    if not creds.valid:
        creds.refresh(Request())
    return creds.token

# ---------------------------------------------------------
# 2. 軽量HTTPリクエストによるファイル操作
# ---------------------------------------------------------

def get_text_files_http(creds):
    """ファイル一覧を取得 (GETリクエスト)"""
    token = get_access_token(creds)
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "q": "mimeType = 'text/plain' and trashed = false",
        "pageSize": 20,
        "fields": "files(id, name)",
        "orderBy": "modifiedTime desc"
    }
    
    response = requests.get(
        "https://www.googleapis.com/drive/v3/files",
        headers=headers,
        params=params
    )
    
    if response.status_code == 200:
        return response.json().get('files', [])
    else:
        st.error(f"一覧取得エラー: {response.text}")
        return []

def read_file_http(creds, file_id):
    """ファイルの中身を読む (GETリクエスト)"""
    if not file_id: return ""
    token = get_access_token(creds)
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(
        f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
        headers=headers
    )
    
    if response.status_code == 200:
        return response.text
    else:
        st.error(f"読み込みエラー: {response.text}")
        return ""

def create_file_http(creds, title, content):
    """
    新規作成 (POSTリクエスト)
    タイムアウト回避のため、メタデータ作成とアップロードを分けずにMultipart送信で一発で行います
    """
    token = get_access_token(creds)
    headers = {"Authorization": f"Bearer {token}"}
    
    # メタデータ
    metadata = {
        "name": title,
        "mimeType": "text/plain"
    }
    
    # マルチパートアップロードの構築
    files = {
        'data': ('metadata', json.dumps(metadata), 'application/json; charset=UTF-8'),
        'file': (title, content, 'text/plain')
    }
    
    # uploadType=multipart を使用
    response = requests.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
        headers=headers,
        files=files,
        timeout=60  # 60秒待機
    )
    
    if response.status_code == 200:
        return response.json().get('id')
    else:
        raise Exception(f"作成エラー({response.status_code}): {response.text}")

def update_file_http(creds, file_id, content):
    """上書き保存 (PATCHリクエスト)"""
    token = get_access_token(creds)
    headers = {"Authorization": f"Bearer {token}"}
    
    # uploadType=media で中身だけガツンと書き換える（最も軽量）
    response = requests.patch(
        f"https://www.googleapis.com/upload/drive/v3/files/{file_id}?uploadType=media",
        headers=headers,
        data=content.encode('utf-8'), # バイナリとして送る
        timeout=60
    )
    
    if response.status_code != 200:
        raise Exception(f"更新エラー({response.status_code}): {response.text}")

# ---------------------------------------------------------
# 3. メインアプリケーション
# ---------------------------------------------------------
def main():
    st.set_page_config(page_title="G-Drive Notepad (Light)", layout="wide")
    st.title("📝 Google Drive ノートブック (軽量版)")

    creds = get_creds()
    if not creds:
        st.stop()

    if "current_file_id" not in st.session_state:
        st.session_state.current_file_id = None
    if "input_title" not in st.session_state:
        st.session_state.input_title = "無題.txt"
    if "input_content" not in st.session_state:
        st.session_state.input_content = ""

    # --- サイドバー ---
    with st.sidebar:
        st.header("ファイル一覧")
        if st.button("＋ 新規作成", use_container_width=True):
            st.session_state.current_file_id = None
            st.session_state.input_title = "無題.txt"
            st.session_state.input_content = ""
            st.rerun()

        st.divider()

        files = get_text_files_http(creds)
        if not files:
            st.write("テキストファイルがありません")
        
        for f in files:
            if st.button(f['name'], key=f['id'], use_container_width=True):
                st.session_state.current_file_id = f['id']
                st.session_state.input_title = f['name']
                st.session_state.input_content = read_file_http(creds, f['id'])
                st.rerun()

    # --- メイン画面 ---
    if st.session_state.current_file_id is None:
        st.info("🆕 新規作成モード (Direct API)")
    else:
        st.caption(f"編集中ID: {st.session_state.current_file_id}")

    title = st.text_input("ファイル名", value=st.session_state.input_title)
    content = st.text_area("内容", value=st.session_state.input_content, height=400)

    if st.button("保存する", type="primary"):
        if not title:
            st.warning("ファイル名を入力してください。")
        else:
            try:
                with st.spinner("保存中..."):
                    if st.session_state.current_file_id is None:
                        # 新規作成
                        new_id = create_file_http(creds, title, content)
                        st.session_state.current_file_id = new_id 
                        st.success(f"作成完了！ ID: {new_id}")
                    else:
                        # 上書き
                        update_file_http(creds, st.session_state.current_file_id, content)
                        st.success("上書き完了！")
                
                st.session_state.input_title = title
                st.session_state.input_content = content
                
                import time
                time.sleep(1)
                st.rerun()
                
            except Exception as e:
                st.error(f"保存失敗: {e}")

if __name__ == "__main__":
    main()
