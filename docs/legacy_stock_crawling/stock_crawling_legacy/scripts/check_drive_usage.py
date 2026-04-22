"""
서비스 계정의 Google Drive 파일 목록 및 용량 확인 스크립트.

사용법:
    python scripts/check_drive_usage.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import gspread
    from google.oauth2.service_account import Credentials
    from service_account_path import resolve_service_account_file
except ImportError:
    print("[에러] gspread / google-auth 패키지가 필요합니다.")
    sys.exit(1)


def main():
    sa_path = resolve_service_account_file()
    if not os.path.exists(sa_path):
        print(f"[에러] 서비스 계정 파일을 찾을 수 없습니다: {sa_path}")
        return 1

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(sa_path, scopes=scopes)
    gc = gspread.authorize(creds)

    # 서비스 계정 이메일 확인
    print(f"서비스 계정: {creds.service_account_email}")
    print()

    # Drive API로 모든 파일 목록 조회
    drive_service = gc.http_client
    
    # gspread의 내부 http_client를 사용하여 Drive API 호출
    url = "https://www.googleapis.com/drive/v3/files"
    params = {
        "pageSize": 100,
        "fields": "nextPageToken, files(id, name, mimeType, size, createdTime, modifiedTime, trashed)",
        "orderBy": "createdTime desc",
        "q": "trashed = false",
    }
    
    all_files = []
    page_token = None
    
    while True:
        if page_token:
            params["pageToken"] = page_token
        
        response = gc.http_client.request("get", url, params=params)
        data = response.json()
        
        files = data.get("files", [])
        all_files.extend(files)
        
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    # 휴지통 파일도 확인
    params_trashed = {
        "pageSize": 100,
        "fields": "nextPageToken, files(id, name, mimeType, size, createdTime, trashed)",
        "q": "trashed = true",
    }
    trashed_files = []
    page_token = None
    
    while True:
        if page_token:
            params_trashed["pageToken"] = page_token
        
        response = gc.http_client.request("get", url, params=params_trashed)
        data = response.json()
        
        files = data.get("files", [])
        trashed_files.extend(files)
        
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    # 용량 확인 (About API)
    about_url = "https://www.googleapis.com/drive/v3/about"
    about_params = {"fields": "storageQuota, user"}
    try:
        about_resp = gc.http_client.request("get", about_url, params=about_params)
        about_data = about_resp.json()
        quota = about_data.get("storageQuota", {})
        
        limit_bytes = int(quota.get("limit", 0))
        usage_bytes = int(quota.get("usage", 0))
        usage_drive = int(quota.get("usageInDrive", 0))
        usage_trash = int(quota.get("usageInDriveTrash", 0))
        
        def fmt(b):
            if b >= 1e9:
                return f"{b/1e9:.2f} GB"
            elif b >= 1e6:
                return f"{b/1e6:.2f} MB"
            elif b >= 1e3:
                return f"{b/1e3:.2f} KB"
            return f"{b} B"
        
        print("=" * 60)
        print("  Google Drive 용량 현황")
        print("=" * 60)
        print(f"  총 용량 한도:     {fmt(limit_bytes)}")
        print(f"  현재 사용량:      {fmt(usage_bytes)}")
        print(f"  Drive 사용:       {fmt(usage_drive)}")
        print(f"  휴지통 사용:      {fmt(usage_trash)}")
        print(f"  남은 용량:        {fmt(max(0, limit_bytes - usage_bytes))}")
        print(f"  사용률:           {usage_bytes/limit_bytes*100:.1f}%" if limit_bytes else "  사용률:           N/A")
        print("=" * 60)
        print()
    except Exception as e:
        print(f"[경고] Drive 용량 조회 실패: {e}")
        print()

    # 활성 파일 출력
    print(f"활성 파일 ({len(all_files)}개):")
    print("-" * 90)
    print(f"{'No':>3}  {'생성일':12s}  {'타입':20s}  {'이름'}")
    print("-" * 90)
    
    spreadsheet_count = 0
    for i, f in enumerate(all_files, 1):
        name = f.get("name", "(이름없음)")
        mime = f.get("mimeType", "")
        created = f.get("createdTime", "")[:10]
        size = f.get("size", "")
        
        # 타입 한글화
        if "spreadsheet" in mime:
            type_str = "📊 스프레드시트"
            spreadsheet_count += 1
        elif "folder" in mime:
            type_str = "📁 폴더"
        elif "document" in mime:
            type_str = "📄 문서"
        else:
            type_str = mime.split(".")[-1][:20] if mime else "unknown"
        
        size_str = f" ({int(size):,}B)" if size else ""
        print(f"{i:>3}  {created}  {type_str:20s}  {name}{size_str}")

    print("-" * 90)
    print(f"총 {len(all_files)}개 (스프레드시트 {spreadsheet_count}개)")
    print()

    # 휴지통 파일 출력
    if trashed_files:
        print(f"🗑️ 휴지통 파일 ({len(trashed_files)}개):")
        print("-" * 90)
        for i, f in enumerate(trashed_files, 1):
            name = f.get("name", "(이름없음)")
            created = f.get("createdTime", "")[:10]
            print(f"{i:>3}  {created}  {name}")
        print("-" * 90)
        print()
        print("💡 휴지통을 비우면 용량이 확보됩니다.")
        print("   비우려면: python scripts/check_drive_usage.py --empty-trash")
    else:
        print("🗑️ 휴지통: 비어있음")

    # --empty-trash 옵션
    if "--empty-trash" in sys.argv:
        print()
        print("🗑️ 휴지통 비우는 중...")
        try:
            empty_url = "https://www.googleapis.com/drive/v3/files/trash"
            gc.http_client.request("delete", empty_url)
            print("✅ 휴지통 비우기 완료!")
        except Exception as e:
            print(f"❌ 휴지통 비우기 실패: {e}")

    # --delete-file 옵션
    if "--delete-file" in sys.argv:
        idx = sys.argv.index("--delete-file")
        if idx + 1 < len(sys.argv):
            file_id = sys.argv[idx + 1]
            print(f"\n🗑️ 파일 삭제 중 (ID: {file_id})...")
            try:
                del_url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
                gc.http_client.request("delete", del_url)
                print("✅ 삭제 완료!")
            except Exception as e:
                print(f"❌ 삭제 실패: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
