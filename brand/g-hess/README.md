# G-HeSS AI Agent 로고 시안

`index.html`을 브라우저로 열면 세 방향을 비교하고 배경을 전환할 수 있습니다. `preview.png`는 공유용 비교 이미지입니다.

| 시안 | 의미 | 용도 제안 |
| --- | --- | --- |
| 01-g-link | G 모노그램과 연결점 | 기본 추천, 앱 및 서비스 헤더 |
| 02-doc-dialogue | 문서와 말풍선 | 문서 기반 대화 기능 강조 |
| 03-knowledge-grid | 연결된 지식 구조 | 검색·지식 통합 기능 강조 |

텍스트 로고는 세 시안이 공유합니다. 표기는 **G-HeSS AI Agent**이며 대소문자와 하이픈을 유지합니다. 이름의 약어 풀이는 별도로 가정하지 않았습니다.

각 폴더의 `icon.svg`는 아이콘, `wordmark.svg`는 텍스트 단독, `logo-horizontal.svg`는 가로 조합입니다. 접미사 `-white`는 어두운 배경용, `-mono`는 #4747B3 단색입니다. 기본 SVG와 PNG 배경은 투명하며 `app-icon`만 #4747B3 배경을 포함합니다. PNG는 아이콘 1024px, 텍스트 및 가로 조합 2배 크기로 제공합니다.

로고의 모든 문자는 직접 구성한 SVG 경로입니다. 외부 글꼴이나 이미지 의존성이 없으며 색상과 크기를 편집할 수 있습니다. SVG 접근성 제목에 서비스명을 포함했습니다. 비교 보드의 설명 문구는 로고에 포함되지 않습니다.

사용자 지정 기본 색상: Indigo `#4747B3`. 같은 색상 계열의 보조색 `#6262C4`와 어두운 배경용 밝은 포인트 `#C9C9FF`를 적용했습니다. 밝은 배경에는 기본형, 어두운 배경에는 white형을 사용합니다.

사용 크기 권장: 기본 아이콘 24px 이상, 문서형 아이콘 32px 이상, 텍스트 로고 180px 이상, 조합형 260px 이상. 16px 환경에서는 01-g-link 아이콘을 우선 검토합니다. 로고 둘레에는 아이콘 높이의 1/4 이상 여백을 두고 비율을 유지합니다.

## 사이드바용 가로 텍스트 로고

`sidebar/`에는 아이콘 없이 **G-HeSS AI Agent**를 한 줄로 배치한 공통 워드마크가 있습니다. [미리보기](sidebar/preview.png)에서 밝은 배경과 어두운 배경을 비교할 수 있습니다.

| 파일 | 표시 크기 | 용도 |
|---|---|---|
| `sidebar/wordmark.svg` | 224 × 40px | 전체 이름, 기본형 |
| `sidebar/wordmark-white.svg` | 224 × 40px | 어두운 사이드바 |
| `sidebar/wordmark-mono.svg` | 224 × 40px | Indigo 단색 |
| `sidebar/wordmark-compact.svg` | 128 × 40px | 좁은 영역용 G-HeSS 축약 표기 |
| `sidebar/wordmark-compact-white.svg` | 128 × 40px | 축약 표기, 어두운 배경 |
| `sidebar/wordmark-compact-mono.svg` | 128 × 40px | 축약 표기, 단색 |

각 SVG와 같은 이름의 투명 PNG를 1배·2배(`@2x`)·3배(`@3x`)로 제공합니다. 전체형은 사이드바 폭 256px·좌우 여백 16px에 맞습니다. 224px보다 좁은 로고 영역에는 축약형을 사용합니다. 축약형의 접근성 이름은 앱에서 전체 서비스명으로 지정합니다. 높이 40px인 에셋 내부의 글자 높이는 약 26px이며, 비율을 유지합니다.

```html
<img src="/brand/g-hess/sidebar/wordmark.svg"
     width="224" height="40" alt="G-HeSS AI Agent">
```

재생성: `node brand/g-hess/generate.mjs` (또는 `bun brand/g-hess/generate.mjs`). SVG 원본을 생성하며 PNG는 `rsvg-convert`로 내보냅니다. 사이드바 PNG와 전체 키트 ZIP 갱신은 `python3 brand/g-hess/package.py`를 실행합니다. Python 표준 라이브러리와 `rsvg-convert`가 필요합니다.
