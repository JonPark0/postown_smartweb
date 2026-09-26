# Postown SmartWeb Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

한국 포스타운 스마트웹 시스템을 Home Assistant에서 제어할 수 있는 통합구성요소입니다.

## 요구 사항

- Home Assistant **2024.2.0** 이상
- SmartWeb 로그인 계정 (웹 브라우저로 SmartWeb에 로그인할 수 있어야 합니다)

## 지원 기기

| 기기 | Home Assistant 엔티티 | 기능 |
|------|----------------------|------|
| 조명 | 스위치 (`switch`) | 켜기 / 끄기 |
| 난방 | 온도 조절기 (`climate`) | 켜기 / 끄기, 재실 / 외출, 희망 온도 설정 (18~41℃, 1℃ 단위), 현재 온도 표시 |
| 난방 | 센서 (`sensor`) 2개 | 현재 온도, 희망 온도 (그래프 기록용) |

난방 기기를 추가하면 온도 조절기 1개와 온도 센서 2개가 함께 만들어집니다.

### 참고 사항

- **난방이 꺼져 있을 때는 외출 모드나 희망 온도를 바꿀 수 없습니다.** SmartWeb 자체가 꺼진 난방에서는 이 기능을 막아 두었기 때문입니다. 시도하면 "먼저 난방을 켜세요"라는 오류가 표시되고 기기에는 아무 명령도 보내지 않습니다.
- 상태는 주기적으로 가져옵니다. 조명과 센서는 30초, 온도 조절기는 60초마다 갱신합니다(Home Assistant 기본값). 월패드에서 바꾼 내용은 다음 갱신 때 반영됩니다.
- SmartWeb 서버에 연결할 수 없으면 기기가 "사용 불가"로 표시됩니다. Home Assistant를 시작할 때 서버에 연결하지 못하면 자동으로 다시 시도합니다.

## 설치 방법

### HACS를 통한 설치 (권장)

1. HACS > Integrations > 우측 상단 메뉴 (⋮) > **Custom repositories** 클릭
2. Repository URL 입력: `https://github.com/JonPark0/postown_smartweb`
3. Category: **Integration** 선택
4. **ADD** 클릭
5. HACS에서 "Postown SmartWeb" 검색 후 **Download** 클릭
6. Home Assistant 재시작

### 수동 설치

1. `custom_components/postown_smartweb` 폴더를 Home Assistant의 `config/custom_components/` 디렉토리에 복사
2. Home Assistant 재시작

## 설정 방법

### UI를 통한 설정

1. Home Assistant > 설정 > 기기 및 서비스 > **통합구성요소 추가**
2. "Postown SmartWeb" 검색
3. 연결 정보 입력:
   - **호스트 URL**: SmartWeb 서버 주소. `http://` 또는 `https://`로 시작해야 합니다 (예: `http://sdexpo9.postown.net`)
   - **사용자 이름**: 로그인 ID
   - **비밀번호**: 로그인 비밀번호
4. 기기 추가 (여러 개를 추가하려면 "다른 기기 추가하기"를 체크):
   - **기기 이름**: 표시할 이름 (예: "거실 LED")
   - **기기 종류**: 조명 또는 난방
   - **기기 ID**: SmartWeb의 `device_no` 값 (숫자). 같은 종류에 같은 ID는 한 번만 등록할 수 있습니다.

> **보안 참고**: `http://` 주소를 쓰면 로그인 정보가 암호화되지 않은 채 인터넷으로 전송됩니다. 서버가 `https://`를 지원하면 `https://` 주소를 쓰세요.

### 기기 ID 확인 방법

웹 브라우저로 SmartWeb에 로그인한 뒤 아래 목록 페이지를 열면 기기 이름과 번호를 한눈에 볼 수 있습니다. `호스트`는 설정에 입력한 주소입니다.

- 조명 목록: `호스트/SmartWeb/My_Home/Detail_HomeControlList.aspx?devType=edtLight`
- 난방 목록: `호스트/SmartWeb/My_Home/Detail_HomeControlList.aspx?devType=edtHeater`

목록에서 기기 이름을 누르면 상세 페이지로 이동하는데, 그 주소 끝의 `device_no` 값이 기기 ID입니다.

- 조명: `Detail_Control_Light.aspx?device_no=1` → 기기 ID `1`
- 난방: `Detail_Control_Heater.aspx?device_no=31` → 기기 ID `31`

## 설정 변경

통합구성요소 설정 후에도 기기를 추가/삭제하거나 연결 정보를 수정할 수 있습니다:

1. 설정 > 기기 및 서비스
2. Postown SmartWeb 카드의 **구성** 클릭
3. 원하는 작업 선택:
   - 기기 추가
   - 기기 삭제
   - 연결 정보 수정 (비밀번호를 바꾼 경우 여기서 새 비밀번호를 입력하세요)

변경 내용은 저장하면 바로 적용됩니다.

## 예시 기기 설정

| 기기 이름 | 기기 종류 | 기기 ID |
|----------|----------|---------|
| 주방 LED | 조명 | 1 |
| 거실 LED | 조명 | 5 |
| 복도등 | 조명 | 9 |
| 난방1(거실) | 난방 | 31 |
| 난방2(부부침실) | 난방 | 34 |

## 문제 해결

### 설정 화면의 오류 메시지

| 메시지 | 원인과 해결 |
|--------|-------------|
| 서버에 연결할 수 없습니다 | 호스트 URL이 맞는지, SmartWeb 서버가 응답하는지 확인하세요. |
| 인증 실패 | 사용자 이름과 비밀번호를 확인하세요. |
| 호스트 URL은 http:// 또는 https://로 시작해야 합니다 | 주소 앞에 `http://`를 붙이세요. |
| 기기 ID는 숫자여야 합니다 | `device_no` 값(숫자)만 입력하세요. |
| 같은 종류와 ID의 기기가 이미 등록되어 있습니다 | 이미 추가된 기기입니다. |

### 통합구성요소가 시작되지 않음

- 로그에 "rejected the credentials"가 보이면 비밀번호가 바뀐 것입니다. **구성 > 연결 정보 수정**에서 새 비밀번호를 입력하세요.
- 서버에 연결할 수 없는 경우에는 Home Assistant가 자동으로 다시 시도합니다.

### 기기가 "사용 불가"로 표시되거나 응답하지 않음

- 기기 ID가 올바른지 확인하세요.
- SmartWeb 웹 페이지에서 같은 기기를 제어할 수 있는지 확인하세요.
- 자세한 로그가 필요하면 `configuration.yaml`에 아래 내용을 추가하고 재시작하세요.

  ```yaml
  logger:
    logs:
      custom_components.postown_smartweb: debug
  ```

## 개발

테스트 실행:

```bash
pip install -r requirements_test.txt
pytest tests
```

## 라이선스

[MIT License](LICENSE)
