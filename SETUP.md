# 인스타그램 자동 게시 — 사전 설정 가이드

이 문서는 GitHub Actions로 인스타그램에 자동 게시하기 위해 **딱 한 번** 해야 하는 설정입니다.

## 0. 전제 조건

- 게시할 인스타그램 계정이 **비즈니스(Business) 또는 크리에이터(Creator) 계정**이어야 합니다.
  (개인 계정이라면 인스타그램 앱 > 설정 > 계정 전환에서 무료로 전환 가능)
- 그 인스타그램 계정이 **페이스북 페이지(Facebook Page)와 연결**되어 있어야 합니다.
  (인스타그램 앱 > 설정 > 계정 센터 > 계정 연결 에서 확인/연결)
- **이 GitHub 레포는 Public이어야 합니다.** (raw.githubusercontent.com URL을 인스타그램 서버가 접근할 수 있어야 하기 때문)
  → 레포를 비공개로 유지하고 싶으시면 알려주세요. 이미지를 GitHub Pages나 별도 스토리지에 올리는 방식으로 바꿔드릴 수 있습니다.

## 1. Meta 개발자 앱 만들기

1. https://developers.facebook.com/apps 접속 후 로그인 (페이스북 계정)
2. "앱 만들기" → 유형은 **"비즈니스(Business)"** 선택
3. 앱 이름 입력 후 생성 (예: "reunion-auto-post")
4. 생성된 앱 대시보드에서 **"제품 추가"** → **Instagram Graph API** 추가

## 2. 권한 있는 액세스 토큰 발급

Graph API Explorer를 이용하는 게 가장 쉽습니다.

1. https://developers.facebook.com/tools/explorer/ 접속
2. 우측 상단에서 방금 만든 앱 선택
3. "사용자 또는 페이지" → 본인 계정으로 로그인
4. 권한(Permissions) 목록에서 아래 항목 체크:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_show_list`
   - `pages_read_engagement`
5. "액세스 토큰 생성" 클릭 → 단기 토큰(Short-lived) 발급됨

이 토큰은 1시간짜리라 바로 **장기 토큰(60일)** 으로 교환해야 합니다.

```bash
curl -i -X GET "https://graph.facebook.com/v22.0/oauth/access_token?
  grant_type=fb_exchange_token&
  client_id={앱ID}&
  client_secret={앱시크릿}&
  fb_exchange_token={방금 발급받은 단기 토큰}"
```

- `{앱ID}`, `{앱시크릿}`은 Meta 개발자 앱 대시보드 > 설정 > 기본 설정에서 확인
- 응답으로 받은 `access_token`이 60일짜리 장기 토큰입니다. 이 값을 GitHub Secret에 넣으세요.

> ⚠️ 60일마다 만료됩니다. 만료 전에 갱신이 필요합니다 (아래 "토큰 자동 갱신" 참고).

## 3. Instagram User ID 확인하기

```bash
curl -i -X GET "https://graph.facebook.com/v22.0/me/accounts?access_token={장기 토큰}"
```

- 응답에서 연결된 페이스북 페이지의 `id`를 확인 → 이를 `{PAGE_ID}`로 사용

```bash
curl -i -X GET "https://graph.facebook.com/v22.0/{PAGE_ID}?fields=instagram_business_account&access_token={장기 토큰}"
```

- 응답의 `instagram_business_account.id` 값이 여러분의 `IG_USER_ID`입니다.

## 4. GitHub Secrets 등록

레포 > Settings > Secrets and variables > Actions > "New repository secret"

| Secret 이름 | 값 |
|---|---|
| `IG_USER_ID` | 위에서 확인한 Instagram User ID |
| `IG_ACCESS_TOKEN` | 장기 액세스 토큰 |

## 5. 사용 방법

1. `instagram-posts/pending/<원하는-폴더명>/` 아래에 이미지 파일들(`card_01.png`, `card_02.png`, ...)과 `caption.txt`를 넣고 커밋 & 푸시
2. 자동으로 게시되게 하려면 그대로 push (워크플로우가 `instagram-posts/pending/**` 변경을 감지해서 자동 실행)
   또는 수동으로: 레포 Actions 탭 > "Post to Instagram" > "Run workflow" > 폴더명 입력
3. 먼저 안전하게 테스트하고 싶으면 `dry_run: true`로 실행 — 실제 게시 없이 어떤 이미지/캡션이 사용될지만 출력합니다
4. 게시 성공 시 해당 폴더는 자동으로 `instagram-posts/posted/`로 이동되고 커밋됩니다

예시로 `instagram-posts/pending/example-post/`에 업로드해주신 동창회 포스터 이미지와 캡션 초안을 넣어뒀습니다. 그대로 테스트해보실 수 있어요.

## 6. 토큰 자동 갱신 (선택, 권장)

60일마다 수동 갱신이 번거로우면, 아래 커맨드로 만료되기 전 토큰을 재교환하는 워크플로우를 스케줄로 돌릴 수 있습니다. 필요하시면 별도로 만들어드릴게요.

```bash
curl -i -X GET "https://graph.facebook.com/v22.0/oauth/access_token?
  grant_type=fb_exchange_token&
  client_id={앱ID}&
  client_secret={앱시크릿}&
  fb_exchange_token={현재 토큰}"
```

## 참고

- Graph API 버전은 분기마다 바뀝니다. 이 가이드와 스크립트는 `v22.0` 기준으로 작성했지만,
  실제 사용 시점에 https://developers.facebook.com/docs/graph-api/changelog 에서 최신 버전을 확인하고
  `scripts/post_to_instagram.py`의 `GRAPH_API_VERSION` 값을 갱신하는 걸 권장합니다.
- 캐러셀은 최대 10장까지 지원됩니다. (기존 9장짜리 카드뉴스 프로젝트에도 그대로 사용 가능합니다)
