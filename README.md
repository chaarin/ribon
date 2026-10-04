# ribon

Ti-6Al-4V 밀링 공정에서 4날 코팅 카바이드 엔드밀의 절삭날별 마모를 예측하고,
표면 품질 위험·생산 상황·공구 비용을 전문 Agent들이 분석하여
최적의 공구 유지·검사·교체 행동을 결정하는 Multi-Agent 공구 유지보수 의사결정 시스템

## 실행

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m src.main   # 합성 데이터 데모
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
| `src/models/ra_reference.py` | VB–Ra 참조 데이터 | C | 임시값 (논문 데이터로 교체 필요) |
| `src/agents/quality_agent.py` | Quality Agent | C | 구현 |
| `src/simulation/production_sim.py` | 생산·비용 시나리오 | D | 가정값 |
| `src/agents/economics_agent.py` | Economics/Production Agent | D | 구현 |
| `src/agents/master_agent.py` | Master Agent | E | 규칙 기반 구현 |
| `src/orchestrator/`, `src/memory/`, `src/feedback/` | 재판단 루프, 상태, 이력 | E | 구현 |
| `src/data/synthetic.py` | 데모용 합성 데이터 | - | 학습·평가에 사용 금지 |

## 데이터

QIT-CEMC 밀링 데이터셋(Force/Torque, Vibration, Sound, Cycle별 Edge 1~4 VBmax)을 사용합니다.
용량 문제로 저장소에는 포함하지 않으며, 받은 파일을 `data/raw/`에 풀어서 사용합니다.
학습/검증은 공구 단위로 분리합니다 (같은 공구의 Cycle이 섞이지 않게).
