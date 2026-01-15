# Postown SmartWeb Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

한국 포스타운 스마트웹 시스템을 Home Assistant에서 제어할 수 있는 통합구성요소입니다.

## 지원 기기

- **조명 (Light/Switch)**: 조명 ON/OFF 제어
- **난방 (Climate)**: 난방 ON/OFF 및 온도 설정

## 설치 방법

### HACS를 통한 설치 (권장)

1. HACS > Integrations > 우측 상단 메뉴 (⋮) > **Custom repositories** 클릭
2. Repository URL 입력: `https://github.com/yourusername/postown_smartweb`
3. Category: **Integration** 선택
4. **ADD** 클릭
5. HACS에서 "Postown SmartWeb" 검색 후 **Download** 클릭
6. Home Assistant 재시작

### 수동 설치

1. `custom_components/postown_smartweb` 폴더를 Home Assistant의 `config/custom_components/` 디렉토리에 복사
2. Home Assistant 재시작

## 설정 방법

### UI를 통한 설정 (권장)

1. Home Assistant > 설정 > 기기 및 서비스 > **통합구성요소 추가**
2. "Postown SmartWeb" 검색
3. 연결 정보 입력:
   - **호스트 URL**: SmartWeb 서버 주소 (예: `http://sdexpo9.postown.net`)
   - **사용자 이름**: 로그인 ID
   - **비밀번호**: 로그인 비밀번호
4. 기기 추가:
   - **기기 이름**: 표시할 이름 (예: "거실 LED")
   - **기기 종류**: 조명 또는 난방 선택
   - **기기 ID**: SmartWeb의 device_no 값

### 기기 ID 확인 방법

SmartWeb에서 기기를 제어할 때 URL을 확인하세요:
- 조명: `Detail_Control_Light.aspx?device_no=1` → device_id: `1`
- 난방: `Detail_Control_Heater.aspx?device_no=31` → device_id: `31`

## 설정 변경

통합구성요소 설정 후에도 기기를 추가/삭제하거나 연결 정보를 수정할 수 있습니다:

1. 설정 > 기기 및 서비스
2. Postown SmartWeb 카드의 **구성** 클릭
3. 원하는 작업 선택:
   - 기기 추가
   - 기기 삭제
   - 연결 정보 수정

## 예시 기기 설정

| 기기 이름 | 기기 종류 | 기기 ID |
|----------|----------|---------|
| 주방 LED | 조명 | 1 |
| 거실 LED | 조명 | 5 |
| 복도등 | 조명 | 9 |
| 난방1(거실) | 난방 | 31 |
| 난방2(부부침실) | 난방 | 34 |

## 문제 해결

### 연결 오류
- 호스트 URL이 올바른지 확인 (`http://` 또는 `https://` 포함)
- 사용자 이름과 비밀번호가 정확한지 확인
- SmartWeb 서버가 네트워크에서 접근 가능한지 확인

### 기기가 응답하지 않음
- 기기 ID가 올바른지 확인
- Home Assistant 로그에서 오류 메시지 확인

## 라이선스

MIT License
