import argparse
import os
import sys
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

def check_status(video_id):
    if not os.path.exists("token.json"):
        print("[check] ERROR: token.json not found")
        return False

    creds = Credentials.from_authorized_user_file(
        "token.json",
        ["https://www.googleapis.com/auth/youtube.readonly"]
    )

    youtube = build("youtube", "v3", credentials=creds)

    try:
        response = youtube.videos().list(
            part="processingDetails,status",
            id=video_id
        ).execute()
    except Exception as e:
        print(f"[check] ERROR: {e}")
        return False

    items = response.get("items", [])
    if not items:
        print("[check] NOT_LIVE")
        return False

    item = items[0]

    # Check processing state
    processing = item.get("processingDetails", {})
    state = processing.get("processingStatus")

    # Check upload status
    status = item.get("status", {})
    upload_status = status.get("uploadStatus")

    # YouTube considers the video "live" when:
    # - processingStatus == "succeeded"
    # - uploadStatus == "processed"
    if state == "succeeded" and upload_status == "processed":
        print("LIVE")
        return True

    print("NOT_LIVE")
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    args = parser.parse_args()

    ok = check_status(args.id)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
