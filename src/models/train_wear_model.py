"""마모 모델 학습 스크립트. (Track B)

TODO(Track B):
- data/processed/ 의 Cycle별 특징과 Edge 1~4 VBmax 라벨로 4-output 회귀 모델 학습
- 검증은 공구 단위로 분리 (leave-one-tool-out). 같은 공구의 Cycle이 학습/검증에 섞이면 안 됨
- Edge별 MAE/RMSE 보고, 불확실성 추정(분위 회귀, 앙상블 등) 포함
- 학습된 모델은 models_out/ 에 저장하고 wear_model.load_wear_model 에서 로드
"""


def main() -> None:
    raise NotImplementedError("데이터 확인 후 구현 예정 (Track B)")


if __name__ == "__main__":
    main()
