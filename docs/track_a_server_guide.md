# Track A 작업 지시서: 학교 서버에서 QIT-CEMC 특징 추출

## 목표

40GB 원본 센서 데이터에서 **Cycle별 특징 + Edge 1~4 VBmax 라벨**을 뽑아 작은 CSV 하나(`data/features/qit_cemc_features.csv`)로 만든다.
이 CSV는 수백 KB라 git에 올릴 수 있고, 이후 모델 학습(Track B)은 원본 없이 어느 컴퓨터에서든 진행한다.

```
학교 서버 (원본 40GB)                       GitHub                      누구나
  ① 구조 조사 → docs/qit_cemc_structure.md ──► push ──► 로더 설계 검토
  ② loader.py 구현
  ③ 특징 추출 → data/features/*.csv       ──► push ──► 모델 학습 (Track B)
```

**원본 데이터(`data/raw/`)는 절대 git에 올리지 않는다.** (`.gitignore`로 막혀 있음)

---

## 0. 준비 (처음 한 번)

1. GitHub 저장소 초대를 수락한다 (저장소 관리자에게 GitHub 아이디 전달).
2. 서버에서 코드를 받고 환경을 만든다.

```bash
git clone https://github.com/chaarin/ribon
cd ribon
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install scipy h5py openpyxl npTDMS   # 데이터 형식 조사용 (필요한 것만 설치돼도 됨)
.venv/bin/pytest -q                                # 32 passed 나오면 정상
```

비공개 저장소라 `git clone`할 때 비밀번호 대신 GitHub Personal Access Token이 필요할 수 있다.
(GitHub → Settings → Developer settings → Personal access tokens → `repo` 권한)

3. 원본 데이터를 `data/raw/` 아래에 두거나 링크를 건다. 이미 다른 곳에 풀어 놨다면 옮기지 말고 링크만 건다.

```bash
ln -s /서버의/QIT-CEMC/경로 data/raw/QIT-CEMC
```

---

## 1. 데이터 구조 조사 (10분)

```bash
.venv/bin/python -m scripts.inspect_dataset data/raw/QIT-CEMC
git checkout -b track-a-data
git add docs/qit_cemc_structure.md
git commit -m "Add QIT-CEMC structure report"
git push -u origin track-a-data
```

보고서에는 폴더 구조, 확장자별 개수·용량, 파일 이름 예시, 각 형식의 앞부분 샘플이 들어간다.
원본은 읽기만 하고 수정하지 않는다. **이 단계까지만 해도 나머지 팀원이 로더 설계를 검토할 수 있다.**

보고서를 보고 아래 질문에 답을 적어 둔다 (`docs/qit_cemc_structure.md` 맨 아래에 추가).

- [ ] 공구는 몇 개인가? (공구 1개의 연속 Cycle인지, 여러 공구인지 → 학습/평가 분할 방식이 달라짐)
- [ ] Cycle 하나가 파일 하나인가, 파일 하나에 여러 Cycle이 들어 있는가?
- [ ] 센서 채널 8개(Fx, Fy, Fz, Mz, Vibration X/Y/Z, Sound)의 실제 열 이름은?
- [ ] 샘플링 주파수는? (힘/진동/소리가 서로 다를 수 있음)
- [ ] VBmax 라벨은 어느 파일에 있고 열 이름은 정확히 무엇인가? (`Edg1_VBmax` / `Edge2_VBmax` 처럼 표기가 섞여 있는지)
- [ ] 라벨이 비어 있는 Cycle이 있는가?
- [ ] 실험 조건(절삭속도, 이송, 절입, 공구 사양, 소재)이 문서에 있는가? Ti-6Al-4V, 4날 코팅 카바이드 엔드밀이 맞는가?

---

## 2. 로더 구현

`src/data/loader.py`의 `load_qit_cemc()`를 구현한다. 1번 결과를 AI(Claude Code 등)에게 주고 아래 프롬프트로 맡기면 된다.

```
프로젝트: Ti-6Al-4V 밀링 4날 엔드밀의 절삭날별 마모 예측 Multi-Agent 시스템 (저장소 ribon)
담당: Track A - QIT-CEMC 데이터 로더

데이터 구조는 docs/qit_cemc_structure.md 에 있다.

해야 할 일:
- src/data/loader.py 의 load_qit_cemc(root) 를 구현한다.
  Cycle마다 src/schemas/sensor.py 의 SensorWindow 하나를 yield 한다.
- signals 키는 src/config/settings.py 의 SENSOR_CHANNELS
  ("Fx","Fy","Fz","Mz","vib_x","vib_y","vib_z","sound") 로 매핑한다.
- vb_label_mm 에 Edge 1~4 VBmax를 mm 단위, Edge 순서대로 넣는다.
- cumulative_cut_time_min 은 데이터에 있으면 사용하고, 없으면 Cycle 번호 기반으로 채우고 주석으로 남긴다.
- 메모리를 아끼기 위해 Cycle을 하나씩 읽어서 yield 한다 (전체를 한 번에 올리지 않는다).
- tests/test_loader.py 를 추가한다: 실제 데이터가 없으면 skip, 있으면 첫 Cycle의 채널 8개와 라벨 4개를 확인.

수정 가능: src/data/loader.py, tests/test_loader.py, requirements.txt (필요한 패키지 추가)
수정 금지: src/schemas/, src/agents/, 그 외 파일
완료 조건: .venv/bin/pytest -q 전체 통과
```

---

## 3. 특징 추출

```bash
.venv/bin/python -m scripts.extract_features --root data/raw/QIT-CEMC
git add src/data/loader.py tests/test_loader.py data/features/qit_cemc_features.csv requirements.txt
git commit -m "Implement QIT-CEMC loader and extract cycle features"
git push
```

GitHub에서 `track-a-data` → `main` Pull Request를 만든다.

결과 CSV는 1행 = 1 Cycle이고 열은 `tool_id, cycle, cut_time_min, (채널별 rms/std/peak/crest/kurtosis), signal_quality, edge1~4_vbmax_mm` 이다.
현재 특징은 기본 시간 영역 통계뿐이다. 확장(주파수 대역 에너지, 날 통과 주파수 성분 등)은 `src/data/features.py`에서 하고, 같은 명령으로 CSV를 다시 만든다.

---

## 지킬 것

- `data/raw/`, 압축 파일, 중간 산출물(`data/processed/`)은 커밋하지 않는다. 커밋 전 `git status`로 확인한다.
- `src/schemas/`는 수정하지 않는다. 형식이 맞지 않으면 팀에 먼저 이야기한다.
- 라벨이 68개뿐이므로 Cycle 하나도 버리지 말고, 문제가 있는 Cycle은 버리는 대신 `signal_quality`나 메모로 표시한다.
