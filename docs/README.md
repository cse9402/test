# 민원서비스 찾기 (정적 웹페이지)

민원서비스 목록 22건을 서비스명 키워드·민원분야로 검색·필터하는 정적 페이지입니다.

- `index.html` : 페이지 본체(데이터 22건 내장, 외부 의존성 없음 — 파일을 더블클릭해도 동작)
- `data/services.csv`, `data/services.json` : 원본 데이터
- `.nojekyll` : GitHub Pages의 Jekyll 처리 비활성화

## 배포(GitHub Pages)
저장소 Settings → Pages → Build and deployment
- Source: **Deploy from a branch**
- Branch: 이 파일이 있는 브랜치 / 폴더 **`/docs`** → Save

배포 주소: `https://<계정>.github.io/<저장소>/`
