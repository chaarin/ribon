# 최종 검증 기록

검증일: 2026-10-05

## 1. 새 환경에서 처음부터 설치

저장소에 커밋된 파일만 꺼내(zip과 같은 내용) 빈 폴더에서 설치·실행했다.

| 환경 | 설치 | 테스트 | 데모 |
|---|---|---|---|
| macOS, Python 3.13.2 | `pip install -r requirements.txt` 성공 | **62 passed** | 정삭 프리셋: Cycle 13 교체, 검사 3회 |
| 학교 GPU 서버 (Linux), Python 3.11.16 | 성공 | **62 passed** | 황삭 프리셋: Cycle 24 교체, 검사 0회 |

## 2. 정적 검사

- `pyflakes src scripts tests`: 지적 사항 없음 (사용하지 않는 import·변수 없음)

## 3. 테스트 구성 (62개)

| 파일 | 확인 내용 |
|---|---|
| `test_wear_report.py` | 날별 통계, 편마모 지수, 초기 마모 구간 노이즈 무시 |
| `test_agents.py` | 품질 등급(공구 용도별), 검사 가치 기준, MEDIUM 판단(윙 리브 위치·재고·납기), 재측정, 생산 압박 |
| `test_scenarios.py` | 팀 테스트 케이스 TC01~TC06 |
| `test_pipeline.py` | 검사 결과 반영·보정·재판단, 전체 수명 실행 |
| `test_loader.py` | 파일-Cycle 매칭, 절삭 구간 검출, 드리프트 제거, 손상·단위 다른 진동 파일 결측 처리 |
| `test_qit_evaluation.py` | 실제 68 Cycle 재생, 블록 교차검증(자기 라벨 미사용), 손실 계산식, 프리셋별 판단 차이 |
| `test_web.py` | 웹 API: 세션, Cycle 진행, 검사 입력(값 변경 포함), 조건 조정, 비교, 정답 |

## 4. 결과 재현

- `python -m src.models.train_wear_model`, `python -m scripts.evaluate_policies`를 새 환경에서 다시 실행 → 저장소의 `docs/track_b_results.md`, `docs/step3_results.md`와 **내용 동일**
- 터미널 데모 (`python -m src.main --preset ...`)

| 프리셋 | 결과 |
|---|---|
| finishing (정삭) | Cycle 13 즉시 교체, 검사 Cycle 1·7·13 |
| roughing (황삭) | Cycle 24 즉시 교체 (0.3 mm 한계), 검사 없음 |
| no_stock (여분 공구 없음) | Cycle 13 윙 리브 마친 뒤 교체 |
| due_tight (납기 임박) | Cycle 13 윙 리브 마친 뒤 교체 |
| no_inspection (검사 장비 없음) | Cycle 16 즉시 교체, 검사 없음 |
| `--data synthetic` | Cycle 10 즉시 교체 (합성 데이터) |

## 5. 웹 화면 (브라우저 자동 조작, Chrome)

| 시나리오 | 결과 |
|---|---|
| 기본 조건 (정삭, 교체 15분, 재고 2, 납기 여유 360분, Low, 검사 가능, 진행률 90%) | Cycle 13 즉시 교체, 검사 3회 |
| 황삭 + 검사 불가 | Cycle 24 즉시 교체 |
| 정삭 + 재고 0 | Cycle 13 윙 리브 마친 뒤 교체 |
| 정삭 + 납기 여유 5분 + 우선순위 High | Cycle 13 윙 리브 마친 뒤 교체 |
| 첫 검사에서 Edge 2를 0.35 mm로 바꿔 입력 | Cycle 1에서 즉시 교체 |
| 브라우저 콘솔 오류 | 없음 |
| 밝은 / 어두운 화면 | 둘 다 정상 표시 |

스크린샷: `docs/images/` (기본 조건 종료 화면, 납기 임박 조건 종료 화면, 검사 창, 어두운 화면)

## 평가하는 분이 직접 확인하는 방법

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest                          # 62 passed
.venv/bin/python -m src.web               # http://localhost:8000 에서 시연
```
