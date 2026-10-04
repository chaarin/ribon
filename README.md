# ribon

Ti-6Al-4V 밀링 공정에서 4날 코팅 카바이드 엔드밀의 절삭날별 마모를 예측하고,
표면 품질 위험·생산 상황·공구 비용을 전문 Agent들이 분석하여
최적의 공구 유지·검사·교체 행동을 결정하는 Multi-Agent 공구 유지보수 의사결정 시스템

## 실행

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m src.main --scenario S15   # 합성 센서 데이터 + 시나리오 데모
.venv/bin/pytest               # 테스트
```

## 흐름

```
센서 데이터 → Wear Agent → Quality Agent → Economics/Production Agent → Master Agent → 행동
                  ▲                                                                   │
                  └──────── 상태 갱신 ◄── Feedback Handler ◄── 검사 결과 ◄──────────────┘
```

| 행동 | 의미 |
|---|---|
| `CONTINUE` | 계속 가공 |
| `REMEASURE` | 센서 재측정 |
| `INSPECT_EDGE` | 특정 날 검사 |
| `REPLACE_AFTER_JOB` | 현재 공정 후 교체 |
| `REPLACE_NOW` | 즉시 교체 |

## 구조와 담당 트랙

| 경로 | 내용 | 트랙 | 상태 |
|---|---|---|---|
| `src/schemas/` | Agent 간 데이터 형식 | 공통 (수정 시 팀 합의) | 완료 |
| `src/config/thresholds.yaml` | 모든 판단 기준값 | 공통 | 초기 가정값 |
| `src/data/loader.py` | QIT-CEMC 로더 | A | TODO |
| `src/data/preprocess.py`, `features.py` | 전처리, 특징 추출 | A | 기본 구현 |
| `src/models/wear_model.py`, `train_wear_model.py` | 날별 VBmax 예측 모델 | B | 더미 모델 |
| `src/agents/wear_agent.py` | Wear Agent | B | 구현 |
| `src/models/quality_reference.py` | 논문 VB–Ra 참조 데이터 로딩 | C | 구현 (참고 근거용) |
| `src/agents/quality_agent.py` | Quality Agent | C | 구현 |
| `src/simulation/production_sim.py` | 시나리오 S01~S24 로딩 | D | 구현 |
| `src/agents/economics_agent.py` | Economics/Production Agent | D | 구현 |
| `src/agents/master_agent.py` | Master Agent | E | 규칙 기반 구현 |
| `src/orchestrator/`, `src/memory/`, `src/feedback/` | 재판단 루프, 상태, 이력 | E | 구현 |
| `src/data/synthetic.py` | 데모용 합성 센서 데이터 | - | 학습·평가에 사용 금지 |
| `data/reference/` | 논문 참조 데이터, 경제·생산 시나리오, Agent 테스트 케이스 | - | 저장소에 포함 |

## 데이터

| 데이터 | 위치 | 성격 | 사용 원칙 |
|---|---|---|---|
| QIT-CEMC 센서·마모 (약 68 Cycle, 원본 11GB) | 학교 서버 `data/raw/` (git 제외) | 실제 실험 데이터 | Wear Agent 학습·평가 |
| Quality_Reference_Data (27개 실험) | `data/reference/quality_reference.csv` | 논문 데이터 (Nguyen et al. 2024) | Quality Agent의 **참고 근거**로만 사용. QIT-CEMC와 병합·학습 금지 |
| Economic / Production Context (S01~S24) | `data/reference/*_context_sim.csv` | MVP용 합성 값 | 발표 시 'MVP 시뮬레이션 입력'으로 표기. 실제 산업 평균이라고 하면 안 됨 |
| Agent 테스트 케이스 (TC01~TC06) | `data/reference/agent_test_cases.csv` | 팀 정의 | `tests/test_scenarios.py`에서 자동 검증 |

원본 엑셀(`Ti6Al4V_MultiAgent_통합데이터.xlsx`)도 `data/reference/`에 함께 보관합니다.

### 데이터 확인 결과와 반영한 내용

- **VB–Ra 상관이 거의 없음:** 참조 데이터 27개 실험 전체에서 Pearson r = 0.06이에요. 실험마다 냉각 방식, 속도, 이송, 절입이 달라서 VB 하나로 Ra를 설명할 수 없어요.
  그래서 Quality Agent는 VB로 Ra를 추정하지 않아요. 대신 최대 VBmax 구간(0.2 mm: Li et al. 2018, 0.3 mm: ISO 8688-2), 편마모, 급속 마모로 위험 등급을 정하고, VB가 비슷한 참조 실험의 Ra 범위는 근거로만 함께 보여줘요.
- **테스트 케이스 시나리오 수정 (2건):** TC03 "고가 부품"이 부품가치가 가장 낮은 S13(300만원)을 가리키고 있어서 S08(2,500만원)로 바꿨어요.
  TC04 "재고 없음"은 재고가 2개인 S18을 가리키고 있어서 S10(재고 0)으로 바꿨어요. 원본은 엑셀에 그대로 있어요.
- **`Remaining_Production_Value_KRW` 열이 `Remaining_Parts`와 맞지 않음:** 예를 들어 S02는 부품가치 2,500만원 × 남은 수량 2개 = 5,000만원이어야 하는데 3억 7,500만원으로 적혀 있어요.
  두 CSV의 행 순환 주기(6행과 8행)가 달라서 생긴 것으로 보여요. 코드에서는 이 열을 쓰지 않고 `부품가치 × Remaining_Parts`로 직접 계산해요.
- **경제성 시트의 행 값은 6행 주기로 반복돼요** (S01=S07=S13=S19). 시나리오는 24개지만 비용 조건의 조합은 6가지예요.

## 다음 단계

1. **Track A (학교 서버):** QIT-CEMC 폴더 구조와 채널·라벨 열 이름 확인 → `loader.py` 구현 → Cycle별 특징 추출.
   결과물 `data/features/qit_cemc_features.csv`(68행 × 특징 + Edge 1~4 VBmax)는 수백 KB 수준이라 git에 올릴 수 있어요.
   그러면 40GB 원본 없이 어느 컴퓨터에서든 모델을 학습할 수 있어요.
2. **Track B:** 라벨이 68개뿐이라 딥러닝보다 특징 기반의 가벼운 모델(Ridge, 랜덤포레스트, LightGBM)이 적합해요.
   공구가 여러 개면 공구 단위로, 한 개면 앞쪽 Cycle로 학습하고 뒤쪽 Cycle로 평가해야 해요 (무작위 분할 금지).
   평가할 때는 같은 데이터로 평균 마모 기준 판단과 날별 판단을 비교해서 차별점의 근거로 삼아요.
3. **Streamlit 앱:** 공구가격, 부품가치, 재고, 남은 수량을 사용자가 입력하게 하고, 시나리오 S01~S24는 기본값으로 사용해요.
