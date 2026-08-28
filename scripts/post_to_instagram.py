#!/usr/bin/env python3
"""
GitHub Actions에서 실행되는 인스타그램 자동 게시 스크립트.

동작 방식:
  instagram-posts/pending/<POST_NAME>/ 폴더 안에
    - caption.txt        (게시글 본문. 해시태그 포함)
    - card_01.png, card_02.png, ... (이미지, 파일명 오름차순으로 게시됨)
  이 있으면, 이 폴더를 읽어서
    - 이미지가 1장이면 단일 이미지 게시
    - 2장 이상이면 캐러셀(최대 10장) 게시
  로 인스타그램에 업로드합니다.

필요한 환경변수:
  IG_USER_ID       - 인스타그램 비즈니스 계정의 Instagram User ID
  IG_ACCESS_TOKEN  - 장기(long-lived) 액세스 토큰
  GITHUB_REPOSITORY - "owner/repo" (GitHub Actions에서 자동으로 세팅됨)
  GITHUB_REF_NAME   - 브랜치 이름 (GitHub Actions에서 자동으로 세팅됨, 없으면 main으로 간주)

사용 예:
  python post_to_instagram.py --post-name example-post
"""

import argparse
import os
import sys
import time
import urllib.parse
import urllib.request
import json

# Meta Graph API 버전은 분기마다 바뀝니다.
# 최신 버전은 https://developers.facebook.com/docs/graph-api/changelog 에서 확인 후
# 필요시 아래 값을 갱신하세요.
GRAPH_API_VERSION = os.environ.get("GRAPH_API_VERSION", "v22.0")
GRAPH_API_BASE = f"https://graph.instagram.com/{GRAPH_API_VERSION}"

POLL_INTERVAL_SECONDS = 3
POLL_MAX_ATTEMPTS = 20


def api_post(path, params):
    url = f"{GRAPH_API_BASE}/{path}"
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_get(path, params):
    query = urllib.parse.urlencode(params)
    url = f"{GRAPH_API_BASE}/{path}?{query}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_raw_url(repo, ref, relative_path):
    """레포가 public일 때, raw.githubusercontent.com URL을 만든다."""
    encoded_path = "/".join(urllib.parse.quote(part) for part in relative_path.split("/"))
    return f"https://raw.githubusercontent.com/{repo}/{ref}/{encoded_path}"


def wait_until_finished(container_id, access_token):
    """미디어 컨테이너가 FINISHED 상태가 될 때까지 대기."""
    for attempt in range(POLL_MAX_ATTEMPTS):
        result = api_get(container_id, {
            "fields": "status_code",
            "access_token": access_token,
        })
        status = result.get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"미디어 처리 실패: {result}")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"미디어 처리 시간 초과: {container_id}")


def create_image_container(ig_user_id, access_token, image_url, is_carousel_item=False):
    params = {
        "image_url": image_url,
        "access_token": access_token,
    }
    if is_carousel_item:
        params["is_carousel_item"] = "true"
    result = api_post(f"{ig_user_id}/media", params)
    if "id" not in result:
        raise RuntimeError(f"이미지 컨테이너 생성 실패: {result}")
    return result["id"]


def create_carousel_container(ig_user_id, access_token, children_ids, caption):
    params = {
        "media_type": "CAROUSEL",
        "children": ",".join(children_ids),
        "caption": caption,
        "access_token": access_token,
    }
    result = api_post(f"{ig_user_id}/media", params)
    if "id" not in result:
        raise RuntimeError(f"캐러셀 컨테이너 생성 실패: {result}")
    return result["id"]


def publish_container(ig_user_id, access_token, creation_id):
    result = api_post(f"{ig_user_id}/media_publish", {
        "creation_id": creation_id,
        "access_token": access_token,
    })
    if "id" not in result:
        raise RuntimeError(f"게시 실패: {result}")
    return result["id"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--post-name", required=True, help="instagram-posts/pending/ 아래 폴더 이름")
    parser.add_argument("--base-dir", default="instagram-posts/pending", help="게시 대기 폴더 루트")
    parser.add_argument("--dry-run", action="store_true", help="실제 게시 없이 계획만 출력")
    args = parser.parse_args()

    ig_user_id = os.environ.get("IG_USER_ID")
    access_token = os.environ.get("IG_ACCESS_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    ref = os.environ.get("GITHUB_REF_NAME", "main")

    if not ig_user_id or not access_token:
        sys.exit("오류: IG_USER_ID / IG_ACCESS_TOKEN 환경변수가 설정되어 있지 않습니다.")
    if not repo:
        sys.exit("오류: GITHUB_REPOSITORY 환경변수가 없습니다. (GitHub Actions 환경에서 실행하세요)")

    post_dir = os.path.join(args.base_dir, args.post_name)
    if not os.path.isdir(post_dir):
        sys.exit(f"오류: 폴더를 찾을 수 없습니다: {post_dir}")

    caption_path = os.path.join(post_dir, "caption.txt")
    caption = ""
    if os.path.isfile(caption_path):
        with open(caption_path, "r", encoding="utf-8") as f:
            caption = f.read().strip()

    image_files = sorted(
        f for f in os.listdir(post_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    )
    if not image_files:
        sys.exit(f"오류: {post_dir} 안에 이미지 파일이 없습니다.")
    if len(image_files) > 10:
        sys.exit("오류: 인스타그램 캐러셀은 최대 10장까지만 지원합니다.")

    image_urls = [
        build_raw_url(repo, ref, os.path.join(post_dir, f).replace(os.sep, "/"))
        for f in image_files
    ]

    print(f"게시 대상: {args.post_name}")
    print(f"이미지 {len(image_urls)}장:")
    for u in image_urls:
        print(f"  - {u}")
    print(f"캡션: {caption[:60]}{'...' if len(caption) > 60 else ''}")

    if args.dry_run:
        print("\n[dry-run] 실제로 게시하지 않았습니다.")
        return

    if len(image_urls) == 1:
        # 단일 이미지 게시
        container_id = create_image_container(ig_user_id, access_token, image_urls[0])
        wait_until_finished(container_id, access_token)
        # 단일 이미지는 caption을 media 생성 시 같이 넣어야 하므로 재생성
        container_id = api_post(f"{ig_user_id}/media", {
            "image_url": image_urls[0],
            "caption": caption,
            "access_token": access_token,
        })["id"]
        wait_until_finished(container_id, access_token)
        media_id = publish_container(ig_user_id, access_token, container_id)
    else:
        # 캐러셀 게시
        children_ids = []
        for url in image_urls:
            child_id = create_image_container(ig_user_id, access_token, url, is_carousel_item=True)
            wait_until_finished(child_id, access_token)
            children_ids.append(child_id)
        carousel_id = create_carousel_container(ig_user_id, access_token, children_ids, caption)
        wait_until_finished(carousel_id, access_token)
        media_id = publish_container(ig_user_id, access_token, carousel_id)

    print(f"\n게시 완료! media_id = {media_id}")


if __name__ == "__main__":
    main()
