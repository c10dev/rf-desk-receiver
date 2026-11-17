# deskrx

교탁에 고정해 두는 노트북 수신 프로그램이다. 빈 교실의 와이파이·BLE 전파를 기록한 뒤, 새로 잡히는 전파와 사라진 새 전파의 이력을 터미널에 보여 주고 파일로 남긴다.

## 하는 일

- 빈 교실 기록: 시작 후 정해진 시간(기본 120초) 동안 잡히는 전파를 모아 `baseline.json`으로 저장한다.
- 감시: 빈 교실 기록에 없던 전파와 같은 종류가 늘어난 것을 "새 전파"로 보여 준다.
- 이력: 새 전파가 사라져도 시작·끝 시각과 가장 센 신호를 남긴다. 화면에는 같은 전파를 한 줄로 묶어 보여 주고, −85 dBm보다 약한 것은 종류 수와 횟수만 따로 보여 준다.
- 경고: 수신이 멈추면 화면 맨 위에 "감시가 완전하지 않습니다"와 이유를 보여 준다.

## 못 하는 일

- 전파의 주인이 누구인지, 무엇을 하는 기기인지 알 수 없다. 기기가 스스로 알린 이름과 종류 단서만 쓴다.
- 전원을 끈 기기, 와이파이와 BLE를 쓰지 않는 기기, 이 노트북이 받지 못하는 거리의 전파는 잡지 못한다.
- 와이파이 목록은 OS 도구가 주는 값만 읽는다. 갱신이 느릴 수 있다(30초마다 읽는다).
- 탐지율을 보장하지 않는다. 이 프로그램은 탐지율을 측정하지 않았다.
- 네트워크로 아무것도 보내지 않는다.

## 설치와 실행

Python 3.10 이상이 필요하다. 블루투스 어댑터가 있어야 BLE를 받는다.

### Windows

1. [uv](https://docs.astral.sh/uv/)를 설치한다.
2. 이 폴더에서 `uv sync`를 실행한다.
3. `uv run python -m deskrx`를 실행한다.
4. 와이파이는 `netsh wlan show networks mode=bssid`로 읽는다. 와이파이 어댑터를 켜 둔다.

### Linux

1. uv를 설치한다.
2. NetworkManager(`nmcli`)와 BlueZ를 설치하고 서비스를 켠다.
3. 이 폴더에서 `uv sync`를 실행한다.
4. `uv run python -m deskrx`를 실행한다.

### 흐름

1. 수집: 빈 교실에서 시작한다. 남은 시간이 0이 되면 "Enter를 눌러 감시를 시작하세요"가 나온다.
2. 준비: 교실이 비어 있는지 확인하고 Enter를 누른다. 이 순간의 기록이 빈 교실 기록이 된다.
3. 감시: 화면이 1초마다 갱신된다. Ctrl+C로 끝낸다.

### 옵션

| 옵션 | 뜻 |
| --- | --- |
| `--collect-seconds N` | 수집 시간(기본 120) |
| `--records DIR` | 기록 폴더(기본 `./records`) |
| `--no-ble`, `--no-wifi` | 해당 수신을 끈다 |
| `--use-saved` | 저장된 `baseline.json`으로 수집 없이 바로 감시한다 |
| `--auto-baseline` | 수집이 끝나면 Enter 없이 바로 감시한다 |
| `--raw-log` | 모든 관측을 CSV로 남긴다 |
| `--sim` | 가상 전파 시나리오로 돌린다(실제 수신 없음) |
| `--duration N` | 감시를 N초 한 뒤 종료 코드 0으로 끝낸다 |

## 저장하는 데이터

모두 `--records` 폴더에 쓴다. 이 폴더는 `.gitignore`에 들어 있다.

- `baseline.json`: 빈 교실 기록. 묶음별 개수와 와이파이 주소.
- `events-YYYYMMDD-HHMMSS.jsonl`: 새 전파의 시작·끝 이력. 한 줄에 JSON 하나. 필드는 `type, key, label, source, started, last_seen, ended, peak`.
- `obs-YYYYMMDD-HHMMSS.csv`: `--raw-log`일 때만. 열은 `time,source,address,name,rssi,group`.

BLE와 와이파이 주소가 파일에 남으므로 개인정보 규정에 맞게 보관한다.

## 판정 규칙의 출처

Android 앱 KoriyoSCAN(`exam-rf-guard`)의 규칙을 옮겼다: `SignalGroups.kt`(묶음 키, 같은 공유기 판정, 감시 판정), `DeviceTracker.kt`, `ObservationPeriods.kt`, `RssiFilter.kt`(EMA 0.25), `SignalHints.kt`. 앱과 다른 점은 둘이다. 새 전파가 사라져도 이력에 남고, 수신이 멈추면 화면이 경고한다. 앱의 "확인함" 기능은 옮기지 않았다.

## 테스트

```
uv run --with pytest pytest -q
```

## 라이선스

[Apache License 2.0](LICENSE)으로 공개한다. 판정 규칙은 [KoriyoSCAN](https://github.com/reform-dev-team/exam-rf-guard)(Apache License 2.0)에서 옮겼다. 옮긴 범위와 바꾼 점은 [NOTICE](NOTICE)에 있다. 이 프로그램은 KoriyoSCAN의 일부가 아니며 KoriyoSCAN 기여자가 보증하지 않는다.
