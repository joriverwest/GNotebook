import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

# --- 設定と認証 ---
# Streamlit Secretsから認証情報を取得
def get_drive_service():
    try:
        # st.secrets["gcp_service_account"] は .toml の内容を辞書として返す
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"認証エラー: Secretsが正しく設定されていません。 {e}")
        return None

# --- Drive操作関数 ---
def list_files(service):
    # テキストファイルのみ、ゴミ箱以外を検索
    results = service.files().list(
        q="mimeType = 'text/plain' and trashed = false",
        pageSize=20,
        fields="nextPageToken, files(id, name)"
    ).execute()
    return results.get('files', [])

def read_file(service, file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = request.execute()
    return downloader.decode('utf-8')

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

# --- GUI ---
def main():
    st.set_page_config(page_title="Cloud Text Editor", layout="wide")
    st.title("☁️ Google Drive Text Editor")

    service = get_drive_service()
    if not service:
        st.stop()

    # サイドバー：ファイル一覧と新規作成
    st.sidebar.header("Files")
    
    # 新規作成モードへの切り替え
    if st.sidebar.button("＋ 新規ファイル作成"):
        st.session_state.current_file_id = None
        st.session_state.current_file_name = ""
        st.session_state.file_content = ""
        st.rerun()

    files = list_files(service)
    
    # ファイル選択リスト
    for f in files:
        if st.sidebar.button(f"📄 {f['name']}", key=f['id']):
            st.session_state.current_file_id = f['id']
            st.session_state.current_file_name = f['name']
            # 内容を読み込む
            try:
                content = service.files().get_media(fileId=f['id']).execute().decode('utf-8')
                st.session_state.file_content = content
            except Exception:
                st.session_state.file_content = "（読み込み不可またはバイナリファイル）"
            st.rerun()

    # メインエリア
    if 'current_file_id' not in st.session_state:
        st.info("サイドバーからファイルを選択するか、新規作成してください。")
    else:
        is_new = st.session_state.current_file_id is None
        mode_text = "新規作成" if is_new else "編集"
        
        st.subheader(f"{mode_text}: {st.session_state.current_file_name or '名称未設定'}")

        # ファイル名入力
        new_name = st.text_input("ファイル名 (.txt)", value=st.session_state.current_file_name)
        if not new_name.endswith(".txt"):
            new_name += ".txt"

        # エディタエリア
        new_content = st.text_area("内容", value=st.session_state.get('file_content', ""), height=400)

        col1, col2 = st.columns([1, 5])
        
        with col1:
            if st.button("保存する", type="primary"):
                if is_new:
                    create_file(service, new_name, new_content)
                    st.success(f"{new_name} を作成しました！")
                else:
                    update_file(service, st.session_state.current_file_id, new_content)
                    # 名前が変わっていたらリネーム処理も必要ですが今回は簡易化のため内容更新のみ
                    st.success("更新しました！")
                st.rerun()

        with col2:
            if not is_new:
                if st.button("削除する", type="secondary"):
                    delete_file(service, st.session_state.current_file_id)
                    st.warning("ファイルを削除しました。")
                    del st.session_state.current_file_id
                    st.rerun()

if __name__ == "__main__":
    main()