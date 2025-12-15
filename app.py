import streamlit as st
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

# ページ設定（ブラウザのタブ名など）
st.set_page_config(page_title="Cloud Notebook", layout="wide", page_icon="📝")

# --- 1. Google Drive 認証設定 ---
# Streamlit Cloudの "Secrets" 機能から認証情報を読み込みます
@st.cache_resource
def get_drive_service():
    # st.secrets["gcp_service_account"] にJSONの中身が辞書として入っている前提
    if "gcp_service_account" not in st.secrets:
        st.error("Secretsに 'gcp_service_account' が設定されていません。")
        return None

    # 辞書データから認証情報を作成
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)

# フォルダIDもSecretsから取得
FOLDER_ID = st.secrets["drive_folder_id"]

# --- 2. ファイル操作関数 ---

def get_files():
    """指定フォルダ内のテキストファイル一覧を取得"""
    service = get_drive_service()
    if not service: return []
    
    query = f"'{FOLDER_ID}' in parents and trashed = false"
    results = service.files().list(
        q=query,
        pageSize=50,
        fields="files(id, name, modifiedTime)",
        orderBy="name desc"
    ).execute()
    return results.get('files', [])

def read_file(file_id):
    """ファイルの中身を読み込む"""
    service = get_drive_service()
    content = service.files().get_media(fileId=file_id).execute()
    return content.decode('utf-8')

def save_file(file_id, name, text):
    """新規保存(file_id=None) または 上書き保存"""
    service = get_drive_service()
    
    # テキストをアップロード可能な形式に変換
    fh = io.BytesIO(text.encode('utf-8'))
    media = MediaIoBaseUpload(fh, mimetype='text/plain', resumable=False)
    
    if file_id:
        # 上書き保存 (Update)
        service.files().update(
            fileId=file_id,
            media_body=media
        ).execute()
        return file_id, name
    else:
        # 新規保存 (Create)
        file_metadata = {
            'name': name,
            'parents': [FOLDER_ID],
            'mimeType': 'text/plain'
        }
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        return file.get('id'), name

def delete_file(file_id):
    """ファイルをゴミ箱へ"""
    service = get_drive_service()
    service.files().delete(fileId=file_id).execute()

# --- 3. UI構築 ---

st.title("📝 Cloud Notebook")

# サイドバー：ファイル操作と一覧
with st.sidebar:
    st.header("Files")
    
    # 「新規作成」ボタン
    if st.button("＋ 新規作成", use_container_width=True):
        st.session_state.current_file_id = None
        st.session_state.editor_content = ""
        st.rerun()

    st.divider()

    # ファイル一覧取得
    files = get_files()
    
    # ラジオボタンやセレクトボックスでファイルを選択
    # (名前と更新日時を表示用に整形)
    file_options = {f['name']: f['id'] for f in files}
    
    # 選択中のファイルがあれば、それをデフォルトにする
    current_index = 0
    if "current_file_id" in st.session_state and st.session_state.current_file_id:
        # IDから名前を探す
        for i, f in enumerate(files):
            if f['id'] == st.session_state.current_file_id:
                current_index = i
                break
    
    # 選択ボックス（スマホでも使いやすい）
    selected_name = st.selectbox(
        "保存済みファイル",
        options=list(file_options.keys()) if files else [],
        index=current_index if files else None,
        key="file_selector"
    )

    # 選択が変わったら中身をロードするロジック
    if selected_name:
        selected_id = file_options[selected_name]
        # まだロードしていない、または別のファイルを選んだ場合
        if "current_file_id" not in st.session_state or st.session_state.current_file_id != selected_id:
            st.session_state.current_file_id = selected_id
            st.session_state.editor_content = read_file(selected_id)
            st.rerun()

# メインエリア
file_id = st.session_state.get("current_file_id", None)
content = st.session_state.get("editor_content", "")

# 新規作成用のファイル名自動生成
if file_id is None:
    now = datetime.datetime.now()
    default_filename = now.strftime("%Y%m%d_%H%M%S.txt")
    st.subheader("新規作成モード")
else:
    default_filename = [k for k, v in file_options.items() if v == file_id][0]
    st.subheader(f"編集: {default_filename}")

# エディタエリア
# key="editor_text" を指定して入力を受け取る
input_text = st.text_area("内容", value=content, height=400)

col1, col2 = st.columns([1, 4])

with col1:
    if st.button("保存する", type="primary", use_container_width=True):
        if not input_text:
            st.warning("空のファイルは保存できません。")
        else:
            with st.spinner("Google Driveに保存中..."):
                try:
                    # 新規ならファイル名を決定、既存ならそのまま
                    fname = default_filename
                    new_id, new_name = save_file(file_id, fname, input_text)
                    
                    st.success(f"保存しました: {new_name}")
                    # 状態を更新してリロード
                    st.session_state.current_file_id = new_id
                    st.session_state.editor_content = input_text
                    st.rerun()
                except Exception as e:
                    st.error(f"保存エラー: {e}")

with col2:
    if file_id is not None:
        if st.button("このファイルを削除", type="secondary"):
            if st.session_state.get("confirm_delete") != True:
                st.session_state.confirm_delete = True
                st.warning("本当に削除しますか？ もう一度押すと削除されます。")
            else:
                with st.spinner("削除中..."):
                    delete_file(file_id)
                    st.session_state.current_file_id = None
                    st.session_state.editor_content = ""
                    st.session_state.confirm_delete = False
                    st.success("削除しました")
                    st.rerun()
