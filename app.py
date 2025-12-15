import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

# ---------------------------------------------------------
# 1. Google Drive API 接続設定
# ---------------------------------------------------------
SCOPES = ['https://www.googleapis.com/auth/drive']

@st.cache_resource
def get_drive_service():
    """
    Secretsから認証情報を読み込み、Drive APIのサービスオブジェクトを返す関数
    """
    try:
        # Streamlit CloudのSecretsから認証情報を取得
        creds_dict = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=SCOPES
        )
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        st.error(f"認証エラー: Secretsの設定を確認してください。\n{e}")
        return None

# ---------------------------------------------------------
# 2. ファイル操作用の関数群
# ---------------------------------------------------------
def get_text_files(service):
    """Google Drive上のテキストファイル(.txt)一覧を取得"""
    results = service.files().list(
        q="mimeType = 'text/plain' and trashed = false",
        pageSize=20,
        fields="files(id, name)",
        orderBy="modifiedTime desc"
    ).execute()
    return results.get('files', [])

def read_file(service, file_id):
    """ファイルの中身を読み込む"""
    if not file_id:
        return ""
    try:
        request = service.files().get_media(fileId=file_id)
        file_content = request.execute()
        return file_content.decode('utf-8')
    except Exception as e:
        st.error(f"読み込みエラー: {e}")
        return ""

def create_file(service, title, content):
    """新規ファイルを作成して保存"""
    file_metadata = {'name': title, 'mimeType': 'text/plain'}
    media = MediaIoBaseUpload(io.BytesIO(content.encode('utf-8')), mimetype='text/plain')
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return file.get('id')

def update_file(service, file_id, content):
    """既存のファイルを上書き保存"""
    media = MediaIoBaseUpload(io.BytesIO(content.encode('utf-8')), mimetype='text/plain')
    service.files().update(fileId=file_id, media_body=media).execute()

# ---------------------------------------------------------
# 3. メインアプリケーション
# ---------------------------------------------------------
def main():
    st.set_page_config(page_title="G-Drive Notepad", layout="wide")
    st.title("📝 Google Drive ノートブック")

    # APIサービスの取得
    service = get_drive_service()
    if not service:
        st.stop() # 認証失敗時はここで止める

    # --- セッションステートの初期化 ---
    # 選択中のファイルID (Noneなら新規作成モード)
    if "current_file_id" not in st.session_state:
        st.session_state.current_file_id = None
    # エディタのタイトル
    if "input_title" not in st.session_state:
        st.session_state.input_title = "無題.txt"
    # エディタの本文
    if "input_content" not in st.session_state:
        st.session_state.input_content = ""

    # ==========================================
    # サイドバー：ファイル一覧と新規作成ボタン
    # ==========================================
    with st.sidebar:
        st.header("ファイル一覧")
        
        # [新規作成ボタン]
        if st.button("＋ 新規作成", use_container_width=True):
            st.session_state.current_file_id = None
            st.session_state.input_title = "無題.txt"
            st.session_state.input_content = ""
            st.rerun() # 画面リロードしてリセット

        st.divider()

        # ファイルリストの表示
        files = get_text_files(service)
        for f in files:
            # 各ファイルのボタンを表示
            if st.button(f['name'], key=f['id'], use_container_width=True):
                # ボタンを押したらそのファイルを読み込んでステートにセット
                st.session_state.current_file_id = f['id']
                st.session_state.input_title = f['name']
                st.session_state.input_content = read_file(service, f['id'])
                st.rerun()

    # ==========================================
    # メインエリア：編集画面
    # ==========================================
    
    # 現在のモードを表示
    if st.session_state.current_file_id is None:
        st.info("🆕 新規作成モード")
    else:
        st.caption(f"編集中ID: {st.session_state.current_file_id}")

    # タイトル入力欄
    title = st.text_input("ファイル名", value=st.session_state.input_title)
    
    # 本文入力欄 (heightで高さを調整)
    content = st.text_area("内容", value=st.session_state.input_content, height=400)

    # 保存ボタン
    if st.button("保存する", type="primary"):
        if not title:
            st.warning("ファイル名を入力してください。")
        else:
            try:
                if st.session_state.current_file_id is None:
                    # --- 新規作成処理 ---
                    new_id = create_file(service, title, content)
                    st.session_state.current_file_id = new_id # 作成したIDをセットして編集モードへ移行
                    st.success(f"新規ファイル「{title}」を作成しました！")
                else:
                    # --- 上書き保存処理 ---
                    # ※ファイル名の変更APIは今回は省略し、中身の更新を行います
                    update_file(service, st.session_state.current_file_id, content)
                    st.success("上書き保存しました！")
                
                # 保存した内容をステートにも反映しておく
                st.session_state.input_title = title
                st.session_state.input_content = content
                
                # リスト更新のために少し待ってリロード（即時だとDrive側の反映が遅れることがあるため）
                import time
                time.sleep(1)
                st.rerun()
                
            except Exception as e:
                st.error(f"保存中にエラーが発生しました: {e}")

if __name__ == "__main__":
    main()
