import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import time

# --- 認証機能（ここを追加しました） ---
def check_password():
    """パスワードが合っているか確認する関数"""
    
    # すでに認証済みならTrueを返す
    if st.session_state.get("password_correct", False):
        return True

    # パスワード入力フォームを表示
    st.set_page_config(page_title="Login Required")
    st.header("🔒 ログインが必要です")
    password_input = st.text_input("パスワードを入力してください", type="password")

    if st.button("ログイン"):
        # Secretsに設定したパスワードと照合
        if password_input == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            st.success("ログイン成功！")
            time.sleep(1) # 少し待ってからリロード
            st.rerun()
        else:
            st.error("パスワードが違います")
            
    return False

# --- 以下、前回のGoogle Drive操作ロジック ---

def get_drive_service():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"認証エラー: Secrets設定を確認してください。 {e}")
        return None

def list_files(service):
    results = service.files().list(
        q="mimeType = 'text/plain' and trashed = false",
        pageSize=20,
        fields="nextPageToken, files(id, name)"
    ).execute()
    return results.get('files', [])

def create_file(service, name, content):
    file_metadata = {'name': name, 'mimeType': 'text/plain'}
    media = MediaIoBaseUpload(io.BytesIO(content.encode('utf-8')), mimetype='text/plain')
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return file.get('id')

def update_file(service, file_id, content):
    media = MediaIoBaseUpload(io.BytesIO(content.encode('utf-8')), mimetype='text/plain')
    service.files().update(fileId=file_id, media_body=media).execute()

def delete_file(service, file_id):
    service.files().delete(fileId=file_id).execute()

# --- メイン画面 ---
def main_app():
    # ページ設定を再適用（ログイン画面で設定済みだが上書き用）
    # st.set_page_configは一度しか呼べないため、check_password内で呼んでいればエラーになる可能性があります。
    # そのため、page_titleの変更などはここでは行わず、レイアウトのみ記述します。
    
    st.title("☁️ Google Drive Text Editor")
    
    # ログアウトボタン
    if st.sidebar.button("ログアウト"):
        st.session_state["password_correct"] = False
        st.rerun()

    service = get_drive_service()
    if not service:
        st.stop()

    st.sidebar.header("Files")
    
    if st.sidebar.button("＋ 新規ファイル作成"):
        st.session_state.current_file_id = None
        st.session_state.current_file_name = ""
        st.session_state.file_content = ""
        st.rerun()

    files = list_files(service)
    
    for f in files:
        if st.sidebar.button(f"📄 {f['name']}", key=f['id']):
            st.session_state.current_file_id = f['id']
            st.session_state.current_file_name = f['name']
            try:
                content = service.files().get_media(fileId=f['id']).execute().decode('utf-8')
                st.session_state.file_content = content
            except Exception:
                st.session_state.file_content = "（読み込み不可）"
            st.rerun()

    if 'current_file_id' not in st.session_state:
        st.info("サイドバーからファイルを選択するか、新規作成してください。")
    else:
        is_new = st.session_state.current_file_id is None
        mode_text = "新規作成" if is_new else "編集"
        
        st.subheader(f"{mode_text}: {st.session_state.current_file_name or '名称未設定'}")

        new_name = st.text_input("ファイル名 (.txt)", value=st.session_state.current_file_name)
        if new_name and not new_name.endswith(".txt"):
            new_name += ".txt"

        new_content = st.text_area("内容", value=st.session_state.get('file_content', ""), height=400)

        col1, col2 = st.columns([1, 5])
        
        with col1:
            if st.button("保存する", type="primary"):
                if is_new:
                    create_file(service, new_name, new_content)
                    st.success(f"{new_name} を作成しました！")
                else:
                    update_file(service, st.session_state.current_file_id, new_content)
                    st.success("更新しました！")
                st.rerun()

        with col2:
            if not is_new:
                if st.button("削除する", type="secondary"):
                    delete_file(service, st.session_state.current_file_id)
                    st.warning("削除しました。")
                    del st.session_state.current_file_id
                    st.rerun()

# --- 実行のエントリーポイント ---
if __name__ == "__main__":
    # パスワードチェックが通った場合のみ、メインアプリを表示
    if check_password():
        main_app()
